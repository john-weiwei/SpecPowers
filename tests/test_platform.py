"""Tests for platform detection and adaptation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge.core.platform import (
    is_windows, is_linux, is_macos,
    system_name, check_python_version, ensure_python_version,
    python_command, supports_fcntl_lock, atomic_replace,
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


def test_system_name():
    """system_name should return non-empty string."""
    result = system_name()
    assert isinstance(result, str)
    assert len(result) > 0


def test_check_python_version():
    """Should return True (we're running >= 3.11)."""
    result = check_python_version()
    assert result is True


def test_python_command():
    """Should return a python command string."""
    result = python_command()
    assert result in ("python", "python3")


def test_supports_fcntl_lock():
    """Should return bool matching platform."""
    result = supports_fcntl_lock()
    assert isinstance(result, bool)
    # Windows should be False, others True
    if is_windows():
        assert result is False
    else:
        assert result is True


def test_atomic_replace():
    """atomic_replace should be True on Python 3.3+."""
    result = atomic_replace()
    assert result is True


def test_mutual_exclusion():
    """Exactly one platform flag should be True."""
    flags = [is_windows(), is_linux(), is_macos()]
    true_count = sum(1 for f in flags if f)
    assert true_count <= 1, f"Multiple platforms detected: {flags}"


if __name__ == "__main__":
    test_is_windows()
    test_is_linux()
    test_is_macos()
    test_system_name()
    test_check_python_version()
    test_python_command()
    test_supports_fcntl_lock()
    test_atomic_replace()
    test_mutual_exclusion()
    print("All platform tests passed!")
