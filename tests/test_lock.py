"""Tests for lock module — file locking, mutual exclusion, stale recovery.

锁是并发安全的基石，本文件所有用例都给出确定性断言（禁止吞异常的假测试）：
- 互斥：同进程二次获取必须抛 LockAcquireError
- 死锁恢复：持有者已死（PID 不存在）→ acquire 自愈接管
- 归属保护：release 不得删除他进程/无主（PID 为空）的锁文件
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from specpowers_cli.bridge.core.errors import LockAcquireError
from specpowers_cli.bridge.core.lock import (
    acquire_lock, release_lock, is_locked, force_unlock,
)


def _make_root(tmpdir: str) -> Path:
    root = Path(tmpdir)
    (root / ".specpowers").mkdir(exist_ok=True)
    return root


def _dead_pid() -> int:
    """拿到一个确定已退出的 PID（启动即退出的子进程），用于构造孤儿锁。"""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def _alive_foreign_pid() -> tuple[int, subprocess.Popen]:
    """启动一个短暂存活的子进程，返回 (pid, proc)，调用方负责 kill+wait 收尾。"""
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(5)"],
    )
    return proc.pid, proc


def test_acquire_release_lock():
    """Basic acquire and release cycle."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = _make_root(tmpdir)

        result = acquire_lock(root)
        assert result is True
        assert is_locked(root) is True

        release_lock(root)
        assert is_locked(root) is False


def test_double_acquire_rejected():
    """同进程二次获取必须抛 LockAcquireError（原实现吞异常，互斥从未被断言）。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = _make_root(tmpdir)

        assert acquire_lock(root) is True
        with pytest.raises(LockAcquireError):
            acquire_lock(root, timeout=0)
        release_lock(root)


def test_force_unlock():
    """force_unlock clears the lock."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = _make_root(tmpdir)

        acquire_lock(root)
        assert is_locked(root) is True

        force_unlock(root)
        assert is_locked(root) is False


def test_is_locked_no_lock():
    """is_locked returns False when no lock file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = _make_root(tmpdir)
        assert is_locked(root) is False


def test_stale_lock_recovered_when_holder_dead():
    """回归：持有者已死的孤儿锁必须被 acquire 自愈接管（两种平台路径等价）。

    Windows 路径：存活检查失败 → unlink + O_EXCL 原子重建；
    fcntl 路径：持有进程退出时 flock 已随内核释放 → 直接获锁。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        root = _make_root(tmpdir)
        lock_path = root / ".specpowers" / ".lock"
        lock_path.write_text(str(_dead_pid()), encoding="utf-8")

        assert acquire_lock(root) is True
        # 接管后锁文件应记录本进程 PID
        assert lock_path.read_text(encoding="utf-8").strip() == str(__import__("os").getpid())
        release_lock(root)


def test_release_skips_foreign_lock():
    """release 不得删除他进程持有的锁文件（归属校验）。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = _make_root(tmpdir)
        lock_path = root / ".specpowers" / ".lock"
        foreign_pid, proc = _alive_foreign_pid()
        try:
            lock_path.write_text(str(foreign_pid), encoding="utf-8")
            release_lock(root)
            assert lock_path.exists()
        finally:
            proc.kill()
            proc.wait()


def test_release_skips_empty_lock():
    """回归：PID 为空的锁文件（他进程 O_EXCL 创建后、写 PID 前的空窗）不得删除。

    原实现对 None 采取「保守删除」，恰好删掉正在创建中的新持有者的锁，
    互斥失效；空锁交由 acquire 侧存活检查自愈。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        root = _make_root(tmpdir)
        lock_path = root / ".specpowers" / ".lock"
        lock_path.write_text("", encoding="utf-8")

        release_lock(root)
        assert lock_path.exists()
