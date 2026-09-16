"""Platform detection and adaptation.

Cross-platform differences:
- File locking: fcntl.flock on Linux/macOS, file existence check on Windows
- Shell scripts: bin/specpowers (bash) vs bin/specpowers.bat
- Python command: "python" vs "python3"
- Atomic writes: os.rename (same-fs) vs os.replace (cross-platform)
"""

import os
import shutil
import sys
from pathlib import Path
import platform as _platform


def _safe_which(name: str) -> str | None:
    """仅在 PATH 的绝对路径条目中查找可执行文件，返回绝对路径或 None。

    Windows 下 shutil.which / CreateProcess 默认先把当前目录加入搜索路径
    （与 cmd 语义一致），仓库内放置的恶意 git.bat / openspec.cmd 会被命中执行。
    显式传入过滤后的绝对路径列表可绕开该插入逻辑，封死当前目录劫持面。
    作者：005819 | 协作：GLM-5.3
    """
    env_path = os.environ.get("PATH", "")
    abs_entries = [p for p in env_path.split(os.pathsep) if p and Path(p).is_absolute()]
    return shutil.which(name, path=os.pathsep.join(abs_entries))


def is_windows() -> bool:
    """Return True if running on Windows."""
    return sys.platform == "win32"


def is_linux() -> bool:
    """Return True if running on Linux."""
    return sys.platform.startswith("linux")


def is_macos() -> bool:
    """Return True if running on macOS."""
    return sys.platform == "darwin"


def system_name() -> str:
    """Return human-readable OS name."""
    return _platform.system()


def python_command() -> str:
    """Return the appropriate python command for the current platform.

    On macOS, some systems have 'python' pointing to Python 2,
    so we prefer 'python3'. On Windows and Linux, 'python' is fine.
    """
    if is_macos():
        return "python3"
    return "python"


def supports_fcntl_lock() -> bool:
    """Return True if fcntl-based file locking is available."""
    return not is_windows()


def atomic_replace() -> bool:
    """Return True if os.replace provides atomic same-volume rename."""
    # Python 3.3+ on all platforms supports os.replace
    return sys.version_info >= (3, 3)


def check_python_version(min_version: tuple = (3, 11)) -> bool:
    """Check if current Python version meets minimum requirement."""
    return sys.version_info >= min_version


def get_shell_path() -> str | None:
    """Return path to bash on Linux/macOS, or git-bash on Windows."""
    if is_macos():
        for p in ["/opt/homebrew/bin/bash", "/bin/bash"]:
            if os.path.isfile(p):
                return p
        return "/bin/bash"
    elif is_linux():
        return "/bin/bash"
    else:
        # Windows: prefer Git Bash
        candidates = [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
        return None


def ensure_python_version():
    """Raise FatalError if Python version is too old."""
    from specpowers_cli.bridge.core.errors import FatalError
    if not check_python_version():
        raise FatalError(
            f"Python {'.'.join(map(str, sys.version_info[:3]))} detected. "
            f"SpecPowers requires Python 3.11+."
        )
