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

from bridge.core.platform import supports_fcntl_lock, is_windows


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

    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    deadline = time.time() + timeout if timeout > 0 else time.time()

    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Write PID to lock file for deadlock detection
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, str(os.getpid()).encode())
            os.ftruncate(fd, os.lseek(fd, 0, os.SEEK_CUR))
            return True
        except BlockingIOError:
            if time.time() >= deadline:
                # Check if holder is alive
                if not _check_lock_holder_alive(lock_path):
                    # Deadlock detected — recover
                    fcntl.flock(fd, fcntl.LOCK_EX)
                    os.lseek(fd, 0, os.SEEK_SET)
                    os.write(fd, str(os.getpid()).encode())
                    os.ftruncate(fd, os.lseek(fd, 0, os.SEEK_CUR))
                    return True
                from bridge.core.errors import LockAcquireError
                os.close(fd)
                raise LockAcquireError(
                    "Another SpecPowers instance is running. "
                    "Wait for it to finish or run /specpowers.reset to force-clear."
                )
            time.sleep(0.1)

    os.close(fd)
    return False


def _acquire_windows(lock_path: Path, timeout: float) -> bool:
    """Acquire lock using file existence check (Windows)."""
    deadline = time.time() + timeout if timeout > 0 else time.time()

    while True:
        if not lock_path.exists():
            try:
                # Create lock file with PID
                with open(lock_path, "w") as f:
                    f.write(str(os.getpid()))
                return True
            except OSError:
                pass

        if _check_lock_holder_alive(lock_path):
            if time.time() >= deadline:
                from bridge.core.errors import LockAcquireError
                raise LockAcquireError(
                    "Another SpecPowers instance is running (PID in .lock). "
                    "Wait for it to finish or run /specpowers.reset to force-clear."
                )
        else:
            # Stale lock — holder dead, recover
            lock_path.unlink(missing_ok=True)
            with open(lock_path, "w") as f:
                f.write(str(os.getpid()))
            return True

        time.sleep(0.1)

    return False


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
    """Release fcntl lock."""
    import fcntl

    if not lock_path.exists():
        return
    try:
        fd = os.open(str(lock_path), os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        lock_path.unlink(missing_ok=True)
    except OSError:
        pass


def _release_windows(lock_path: Path) -> None:
    """Release Windows lock (remove file)."""
    lock_path.unlink(missing_ok=True)


def _check_lock_holder_alive(lock_path: Path) -> bool:
    """Check if the process that owns the lock is still alive."""
    if not lock_path.exists():
        return False

    try:
        with open(lock_path, "r") as f:
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
    if lock_path.exists():
        lock_path.unlink(missing_ok=True)
