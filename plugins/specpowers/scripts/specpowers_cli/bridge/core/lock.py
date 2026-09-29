"""File locking for preventing concurrent SpecPowers instances.

- Linux/macOS: fcntl.flock (kernel-level mutual exclusion).
- Windows: file existence check with PID validation (best-effort).

Deadlock detection: if a stale lock file is found (process dead),
automatically recover by removing the lock.
"""

import os
import sys
import time
from pathlib import Path

from specpowers_cli.bridge.core.errors import LockAcquireError
from specpowers_cli.bridge.core.platform import supports_fcntl_lock, is_windows


# 死锁恢复窗口（秒）：判定持有者已死后，非阻塞抢锁的最长等待时间。
# 并发多实例同时恢复时，未抢到的实例在此窗口内明确失败而非无限阻塞。
STALE_RECOVERY_TIMEOUT = 5.0

# 进程内 fcntl 持有锁的 fd 注册表：root 路径 → fd。
# acquire 成功后登记，release 时取出关闭并解锁。
# 原实现 _release_fcntl 重新开一个新 fd 来 LOCK_UN，只解锁了新 fd 自身，
# acquire 持有的那个 fd 从未关闭（靠进程退出由 OS 回收），逻辑错误。
# 作者：005819 | 协作：GLM-5.2
_held_lock_fds: dict[str, int] = {}


def _get_lock_path(root: Path) -> Path:
    """Return path to .lock file."""
    return root / ".specpowers" / ".lock"


def _read_lock_pid(lock_path: Path) -> int | None:
    """读取锁文件中记录的 PID；文件缺失/内容非数字/不可读返回 None。"""
    try:
        content = lock_path.read_text(encoding="utf-8").strip()
        if content.isdigit():
            return int(content)
    except OSError:
        pass
    return None


def acquire_lock(root: Path, timeout: float = 0) -> bool:
    """Acquire a file lock.

    Args:
        root: Project root directory.
        timeout: Maximum seconds to wait (0 = fail immediately).

    Returns:
        True if lock acquired.

    Raises:
        LockAcquireError: if lock is held by another process.
    """
    lock_path = _get_lock_path(root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if supports_fcntl_lock():
        return _acquire_fcntl(lock_path, timeout)
    else:
        return _acquire_windows(lock_path, timeout)


def _flock_write_pid(fd: int) -> None:
    """非阻塞加锁并向锁文件写入本进程 PID（锁被占用时抛 BlockingIOError）。"""
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, str(os.getpid()).encode())
    os.ftruncate(fd, os.lseek(fd, 0, os.SEEK_CUR))


def _fd_matches_path(fd: int, lock_path: Path) -> bool:
    """校验已加锁的 fd 仍指向目录下当前的锁文件（dev+inode 等价）。"""
    try:
        fst = os.fstat(fd)
        pst = os.stat(str(lock_path))
    except OSError:
        return False
    return (fst.st_dev, fst.st_ino) == (pst.st_dev, pst.st_ino)


def _flock_try_once(lock_path: Path) -> int | None:
    """尝试一次「open → flock → 写 PID → inode 校验」。

    Returns:
        成功持有的 fd（由 release_lock 关闭）；失败返回 None（被占用，
        或拿到孤儿 inode 的锁——此时 fd 已在内部关闭）。

    inode 校验的必要性：release 侧 unlock 与 unlink 之间存在窗口，等待在
    旧 inode 上的进程会在 unlink 后 flock 成功、拿到已脱离目录项的孤儿锁，
    而他人可对重建的锁文件再获锁，形成双持有者。flock 成功后必须确认
    fd 指向的仍是目录下的锁文件，失配即丢弃重来。
    作者：005819 | 协作：GLM-5.3
    """
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    try:
        try:
            _flock_write_pid(fd)
        except BlockingIOError:
            os.close(fd)
            return None
        if not _fd_matches_path(fd, lock_path):
            os.close(fd)
            return None
        return fd
    except Exception:
        os.close(fd)
        raise


def _register_held_fd(lock_path: Path, fd: int) -> None:
    """把成功持有的 fd 登记到进程内注册表，供 release_lock 关闭。"""
    _held_lock_fds[str(lock_path.resolve())] = fd


def _acquire_fcntl(lock_path: Path, timeout: float) -> bool:
    """Acquire lock using fcntl.flock (Linux/macOS).

    每轮重试都重新按路径 open（而非复用首轮 fd）：保证锁住的始终是
    当前的目录项，配合 _flock_try_once 的 inode 校验封死双持有者窗口。
    """
    deadline = time.time() + timeout if timeout > 0 else time.time()

    while True:
        fd = _flock_try_once(lock_path)
        if fd is not None:
            _register_held_fd(lock_path, fd)
            return True
        # 锁被占用：持有者存活 → 等待或拒绝；已死 → 恢复流程接管
        if _check_lock_holder_alive(lock_path):
            if time.time() >= deadline:
                raise LockAcquireError(
                    "Another SpecPowers instance is running. "
                    "Wait for it to finish or run /specpowers-reset to force-clear."
                )
        else:
            return _recover_stale_fcntl(lock_path)
        time.sleep(0.1)


def _recover_stale_fcntl(lock_path: Path) -> bool:
    """死锁恢复：持有者已死（flock 已随进程退出释放），限时非阻塞抢锁。

    用非阻塞循环代替阻塞式 flock：并发实例同时恢复时，未抢到者在
    STALE_RECOVERY_TIMEOUT 窗口内明确失败，避免无限期挂起。
    作者：005819 | 协作：GLM-5.3
    """
    deadline = time.time() + STALE_RECOVERY_TIMEOUT
    while True:
        fd = _flock_try_once(lock_path)
        if fd is not None:
            _register_held_fd(lock_path, fd)
            return True
        # 抢锁失败说明并发恢复者已持有：其活着则明确拒绝；窗口耗尽同样拒绝
        if _check_lock_holder_alive(lock_path) or time.time() >= deadline:
            raise LockAcquireError(
                "Another SpecPowers instance is running. "
                "Wait for it to finish or run /specpowers-reset to force-clear."
            )
        time.sleep(0.1)


def _acquire_windows(lock_path: Path, timeout: float) -> bool:
    """Acquire lock using atomic file creation (Windows).

    用 O_CREAT|O_EXCL 原子创建消除 exists()+open() 之间的 TOCTOU 竞争：
    多个并发实例只有一个能成功创建，其余抛 FileExistsError。
    """
    deadline = time.time() + timeout if timeout > 0 else time.time()

    while True:
        # 原子创建：成功则说明锁未被持有
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(os.getpid()).encode())
            finally:
                os.close(fd)
            return True
        except FileExistsError:
            # 锁文件已存在，转去检查持有者是否存活
            pass

        if _check_lock_holder_alive(lock_path):
            if time.time() >= deadline:
                raise LockAcquireError(
                    "Another SpecPowers instance is running (PID in .lock). "
                    "Wait for it to finish or run /specpowers-reset to force-clear."
                )
        else:
            # 死锁恢复：持有者已死，删除旧锁后原子重建
            lock_path.unlink(missing_ok=True)
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, str(os.getpid()).encode())
                finally:
                    os.close(fd)
                return True
            except FileExistsError:
                # 极端情况：另一进程在 unlink 后抢先创建，继续循环重试
                pass

        time.sleep(0.1)


def release_lock(root: Path) -> None:
    """Release the file lock."""
    lock_path = _get_lock_path(root)
    if not lock_path.exists():
        return

    if supports_fcntl_lock():
        _release_fcntl(lock_path)
    else:
        _release_windows(lock_path)


def _release_fcntl(lock_path: Path) -> None:
    """Release fcntl lock — 关闭 acquire 时真正持有的 fd。

    锁文件清理带持有者校验：仅当本进程持有 fd（注册表在案）或锁文件
    PID 标记是本进程时才删除文件，避免竞态窗口内误删并发恢复者
    或其他持有者的锁（否则互斥彻底失效）。
    作者：005819 | 协作：GLM-5.3
    """
    import fcntl

    key = str(lock_path.resolve())
    fd = _held_lock_fds.pop(key, None)
    held = fd is not None
    if held:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
    if held or _read_lock_pid(lock_path) == os.getpid():
        # 仅清理属于本进程的 PID 标记文件
        lock_path.unlink(missing_ok=True)


def _release_windows(lock_path: Path) -> None:
    """Release Windows lock.

    仅删除能确认属于本进程的锁文件（PID 标记 == 本进程）。内容损坏（None）
    不得删除：acquire 的「O_EXCL 创建」与「写入 PID」是两步，创建后写 PID
    前存在空窗，此刻释放中的旧进程读到 None 会误删新持有者的锁，互斥失效；
    空锁/孤儿锁交由 acquire 侧的存活检查自愈（PID 读不出 → 判定已死 → 重建）。
    """
    if _read_lock_pid(lock_path) == os.getpid():
        lock_path.unlink(missing_ok=True)


def _check_lock_holder_alive(lock_path: Path) -> bool:
    """Check if the process that owns the lock is still alive."""
    if not lock_path.exists():
        return False

    pid = _read_lock_pid(lock_path)
    if pid is None:
        return False

    if is_windows():
        try:
            # mtime 供 Windows 分支做 PID 复用判定
            lock_mtime = lock_path.stat().st_mtime
        except OSError:
            return False
        return _check_pid_alive_windows(pid, lock_mtime)
    else:
        return _check_pid_alive_unix(pid)


def _check_pid_alive_unix(pid: int) -> bool:
    """Check if a process is alive on Unix (kill 0)."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kernel32_safe():
    """返回已显式声明函数签名的 kernel32 实例。

    64 位 Python 下 HANDLE 宽于 ctypes 默认 restype（c_int），不声明会把
    句柄截断/符号扩展，导致 CloseHandle 失败泄漏句柄、或 OpenProcess
    结果异常被误判为「进程已死」进而误删活进程的锁。
    作者：005819 | 协作：GLM-5.3
    """
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.GetProcessTimes.argtypes = (
        [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    )
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def _process_creation_time_windows(h_process: int) -> float | None:
    """读取进程创建时间（Unix epoch 秒）；失败返回 None。

    Args:
        h_process: OpenProcess 返回的有效句柄。
    """
    import ctypes
    from ctypes import wintypes

    kernel32 = _kernel32_safe()
    creation = wintypes.FILETIME()
    exit_ft = wintypes.FILETIME()
    kernel_ft = wintypes.FILETIME()
    user_ft = wintypes.FILETIME()
    if not kernel32.GetProcessTimes(
        h_process, ctypes.byref(creation), ctypes.byref(exit_ft),
        ctypes.byref(kernel_ft), ctypes.byref(user_ft),
    ):
        return None
    # FILETIME：自 1601-01-01 起的 100ns 计数 → Unix epoch 秒
    ft = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
    return ft / 10_000_000 - 11644473600


def _check_pid_alive_windows(pid: int, lock_mtime: float | None = None) -> bool:
    """Check if a process is alive on Windows.

    用 PROCESS_QUERY_LIMITED_INFORMATION 打开进程：对提权进程也可查询，
    避免原 PROCESS_QUERY_INFORMATION 因 ACCESS_DENIED 返回 0 被误判为
    已死、进而误删活进程的锁。另以锁文件 mtime 对比进程创建时间防御
    PID 复用：进程创建晚于锁文件最后修改时间 → 该 PID 已被无关进程
    复用，原持有者必已退出。
    作者：005819 | 协作：GLM-5.3
    """
    import ctypes
    from ctypes import wintypes

    kernel32 = _kernel32_safe()
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    h_process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h_process:
        return False
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(h_process, ctypes.byref(exit_code)):
            return False
        if exit_code.value != STILL_ACTIVE:
            return False
        if lock_mtime is None:
            return True
        # PID 复用防御：创建时间晚于锁文件修改时间（容差 2s，覆盖 FAT
        # 文件系统 mtime 精度与时钟源差异）→ 判定复用，原持有者已死
        created = _process_creation_time_windows(h_process)
        return created is None or created <= lock_mtime + 2.0
    finally:
        kernel32.CloseHandle(h_process)


def is_locked(root: Path) -> bool:
    """Check if lock is held (without acquiring)."""
    lock_path = _get_lock_path(root)
    if not lock_path.exists():
        return False
    return _check_lock_holder_alive(lock_path)


def force_unlock(root: Path) -> None:
    """Force-remove the lock file (for reset)."""
    lock_path = _get_lock_path(root)
    # 若当前进程持有 fcntl fd（极少见：reset 自身跳过 acquire），一并关闭并清理注册表
    key = str(lock_path.resolve())
    fd = _held_lock_fds.pop(key, None)
    if fd is not None:
        try:
            os.close(fd)
        except OSError:
            pass
    if lock_path.exists():
        lock_path.unlink(missing_ok=True)
