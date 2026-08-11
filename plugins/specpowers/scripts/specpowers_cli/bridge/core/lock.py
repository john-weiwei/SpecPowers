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

from specpowers_cli.bridge.core.platform import supports_fcntl_lock, is_windows


# 进程内 fcntl 持有锁的 fd 注册表：root 路径 → fd。
# acquire 成功后登记，release 时取出关闭并解锁。
# 原实现 _release_fcntl 重新开一个新 fd 来 LOCK_UN，只解锁了新 fd 自身，
# acquire 持有的那个 fd 从未关闭（靠进程退出由 OS 回收），逻辑错误。
# 作者：005819 | 协作：GLM-5.2
_held_lock_fds: dict[str, int] = {}


def _get_lock_path(root: Path) -> Path:
    """Return path to .lock file."""
    return root / ".specpowers" / ".lock"


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


def _acquire_fcntl(lock_path: Path, timeout: float) -> bool:
    """Acquire lock using fcntl.flock (Linux/macOS)."""
    import fcntl

    # 成功获取锁后，fd 由本进程持有直到 release_lock 时关闭；
    # 若抛异常则必须在此处关闭 fd，避免泄漏
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    try:
        deadline = time.time() + timeout if timeout > 0 else time.time()

        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                # 写入 PID，用于死锁检测
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, str(os.getpid()).encode())
                os.ftruncate(fd, os.lseek(fd, 0, os.SEEK_CUR))
                # 成功获取：fd 由进程持有，登记到注册表供 release_lock 关闭
                _held_lock_fds[str(lock_path.resolve())] = fd
                return True
            except BlockingIOError:
                if time.time() >= deadline:
                    # 检查持有者是否存活
                    if not _check_lock_holder_alive(lock_path):
                        # 死锁恢复：持有者已死，抢回锁
                        fcntl.flock(fd, fcntl.LOCK_EX)
                        os.lseek(fd, 0, os.SEEK_SET)
                        os.write(fd, str(os.getpid()).encode())
                        os.ftruncate(fd, os.lseek(fd, 0, os.SEEK_CUR))
                        _held_lock_fds[str(lock_path.resolve())] = fd
                        return True
                    from specpowers_cli.bridge.core.errors import LockAcquireError
                    raise LockAcquireError(
                        "Another SpecPowers instance is running. "
                        "Wait for it to finish or run /specpowers.reset to force-clear."
                    )
                time.sleep(0.1)
    except Exception:
        # 异常路径：关闭 fd 避免泄漏（成功路径不关闭，由 release_lock 处理）
        os.close(fd)
        raise


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
                from specpowers_cli.bridge.core.errors import LockAcquireError
                raise LockAcquireError(
                    "Another SpecPowers instance is running (PID in .lock). "
                    "Wait for it to finish or run /specpowers.reset to force-clear."
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

    原实现重新 os.open 一个新 fd 来 LOCK_UN，只解锁了新 fd 自身，acquire 持有的
    fd 从未关闭（靠进程退出回收）。改为从 _held_lock_fds 取出真实持有的 fd，
    解锁并关闭，确保锁在 release 时即释放而非延迟到进程退出。
    作者：005819 | 协作：GLM-5.2
    """
    import fcntl

    key = str(lock_path.resolve())
    fd = _held_lock_fds.pop(key, None)
    if fd is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
    # 兜底：清理锁文件（PID 标记）
    lock_path.unlink(missing_ok=True)


def _release_windows(lock_path: Path) -> None:
    """Release Windows lock (remove file)."""
    lock_path.unlink(missing_ok=True)


def _check_lock_holder_alive(lock_path: Path) -> bool:
    """Check if the process that owns the lock is still alive."""
    if not lock_path.exists():
        return False

    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content.isdigit():
            return False
        pid = int(content)
    except (OSError, ValueError):
        return False

    if is_windows():
        return _check_pid_alive_windows(pid)
    else:
        return _check_pid_alive_unix(pid)


def _check_pid_alive_unix(pid: int) -> bool:
    """Check if a process is alive on Unix (kill 0)."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _check_pid_alive_windows(pid: int) -> bool:
    """Check if a process is alive on Windows."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_INFORMATION = 0x0400
    h_process = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
    if h_process:
        exit_code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(h_process, ctypes.byref(exit_code))
        kernel32.CloseHandle(h_process)
        return exit_code.value == 259  # STILL_ACTIVE
    return False


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
