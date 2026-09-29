"""Platform detection and adaptation.

Cross-platform differences:
- File locking: fcntl.flock on Linux/macOS, file existence check on Windows
- Shell scripts: bin/specpowers (bash) vs bin/specpowers.bat
"""

import os
import shutil
import sys
from pathlib import Path


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


def supports_fcntl_lock() -> bool:
    """Return True if fcntl-based file locking is available."""
    return not is_windows()
