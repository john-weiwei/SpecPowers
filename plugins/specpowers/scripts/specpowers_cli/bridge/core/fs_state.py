"""Atomic file state operations for state.json.

Uses temp-file + rename pattern for atomic writes.
state.json structure:
{
    "stage": str,            # constitution|ready|brainstorm|specify|plan|build|archive
    "mode": str,             # full|fast
    "fallback_used": bool,
    "fallback_count": int,
    "feature": str,
    "last_archive_ref": str,
    "execution_mode": str    # build 阶段选择的执行方式：conductor|worktree|subagent|tdd（空=未选择）
}
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path


def _atomic_replace(src: str, dst: str, retries: int = 5, delay: float = 0.05) -> None:
    """跨平台原子替换，Windows 下对 PermissionError 短暂重试。

    Windows 上 os.replace 目标文件若被杀毒软件/索引器短暂打开，会抛
    [WinError 5] PermissionError。这是高频 IO 场景（如测试连续创建临时仓库）
    的已知痛点。重试几次即可通过，避免在真实工作流中误报。
    作者：005819 | 协作：GLM-5.2
    """
    for attempt in range(retries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            # 仅 Windows 下 PermissionError 值得重试（文件被外部短暂占用）
            if sys.platform != "win32" or attempt == retries - 1:
                raise
            time.sleep(delay)


DEFAULT_STATE = {
    "stage": "constitution",
    "mode": "full",
    "fallback_used": False,
    "fallback_count": 0,
    "feature": "",
    "last_archive_ref": "",
    # build 阶段用户选择的执行方式（conductor/worktree/subagent/tdd）。
    # build.md 第二步声明记录到 state.json，这里落地该承诺。
    # 空串=未选择；reset/archive 时清空，避免新 feature 继承旧执行模式。
    "execution_mode": "",
}


def _get_state_path(root: Path) -> Path:
    """Return path to state.json."""
    return root / ".specpowers" / "state.json"


def load_state(root: Path) -> dict:
    """Load state.json. Returns default if not found. Raises FatalError if corrupt."""
    state_path = _get_state_path(root)
    if not state_path.exists():
        return dict(DEFAULT_STATE)

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        from specpowers_cli.bridge.core.errors import FatalError
        raise FatalError(
            f"state.json is corrupted: {e}. "
            f"Run /specpowers.reset to recover."
        )

    # 顶层类型校验：合法 JSON 但非对象（数组/字符串/数字）时 dict.update
    # 会抛意外异常或静默混入错误结构，显式拒绝并引导 reset
    if not isinstance(data, dict):
        from specpowers_cli.bridge.core.errors import FatalError
        raise FatalError(
            f"state.json is corrupted: top level must be a JSON object, "
            f"got {type(data).__name__}. "
            f"Run /specpowers.reset to recover."
        )

    # Merge with defaults to handle missing keys
    result = dict(DEFAULT_STATE)
    result.update(data)
    return result


def save_state(root: Path, state: dict) -> None:
    """Atomically write state.json using temp file + rename.

    Prevents half-written corruption on crash.
    """
    state_path = _get_state_path(root)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in same directory (ensures same filesystem for atomic rename)
    fd, tmp_path = tempfile.mkstemp(
        suffix=".json",
        prefix=".state-",
        dir=str(state_path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        # 原子替换：Windows 下对 PermissionError 重试（见 _atomic_replace）
        _atomic_replace(tmp_path, state_path)
    except Exception:
        # Clean up temp file on failure
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def init_state(root: Path) -> dict:
    """Initialize state.json with defaults and persist."""
    state = dict(DEFAULT_STATE)
    save_state(root, state)
    return state


def reset_state(root: Path) -> dict:
    """Reset state to ready (preserves fallback_count)."""
    old_state = load_state(root)
    new_state = dict(DEFAULT_STATE)
    new_state["stage"] = "ready"
    new_state["fallback_count"] = old_state.get("fallback_count", 0)
    save_state(root, new_state)
    return new_state


def delete_state(root: Path) -> None:
    """Delete state.json (for full reset)."""
    state_path = _get_state_path(root)
    if state_path.exists():
        state_path.unlink()
