"""Tests for platform detection and adaptation."""

from specpowers_cli.bridge.core.platform import (
    is_windows, is_linux, is_macos, supports_fcntl_lock,
)


def test_is_windows():
    """is_windows should return bool."""
    result = is_windows()
    assert isinstance(result, bool)


def test_is_linux():
    """is_linux should return bool."""
    result = is_linux()
    assert isinstance(result, bool)


def test_is_macos():
    """is_macos should return bool."""
    result = is_macos()
    assert isinstance(result, bool)


def test_supports_fcntl_lock():
    """Should return bool matching platform."""
    result = supports_fcntl_lock()
    assert isinstance(result, bool)
    # Windows should be False, others True
    if is_windows():
        assert result is False
    else:
        assert result is True


def test_mutual_exclusion():
    """恰好一个平台标志为 True（原断言 <= 1 对全 False 也放行，是弱断言）。"""
    flags = [is_windows(), is_linux(), is_macos()]
    true_count = sum(1 for f in flags if f)
    assert true_count == 1, f"平台标志应恰好命中一个，实际: {flags}"
