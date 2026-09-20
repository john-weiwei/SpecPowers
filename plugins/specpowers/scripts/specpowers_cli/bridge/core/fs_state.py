"""Atomic file state operations for state.json.

Uses temp-file + rename pattern for atomic writes.
state.json structure:
{
    "stage": str,            # init|ready|explore|propose|apply|archive
    "mode": str,             # full|fast
    "fallback_used": bool,
    "fallback_count": int,
    "feature": str,
    "last_archive_ref": str,
    "execution_mode": str,   # apply 阶段选择的执行方式：conductor|worktree|subagent|tdd（空=未选择）
    "iteration_count": int,  # auto 模式需求迭代轮次（0=首轮，归档/reset 清零；与 fallback_count 互不占用）
    "design_doc": str        # explore 阶段登记的设计文档路径（propose 前置校验凭据；空=未登记）
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
    "stage": "init",
    "mode": "full",
    "fallback_used": False,
    "fallback_count": 0,
    "feature": "",
    "last_archive_ref": "",
    # apply 阶段用户选择的执行方式（conductor/worktree/subagent/tdd）。
    # apply.md 第二步声明记录到 state.json，这里落地该承诺。
    # 空串=未选择；reset/archive 时清空，避免新 feature 继承旧执行模式。
    "execution_mode": "",
    # auto 模式需求迭代轮次：0=首轮，每次 auto new-round 递增。
    # 归档即新需求 → archive 清零；reset 放弃当前 feature → 同样清零。
    # 与 fallback_count（人工回退限额）语义独立，互不占用。
    "iteration_count": 0,
    # explore 阶段认知层落盘设计文档后经 facade record-design-doc 登记的路径。
    # propose 从 explore 进入时校验非空且文件存在（防探索被架空）；
    # 归档/reset 清空；迭代轮保留（同需求指针仍有效，方案变更时 explore 重跑重新登记）。
    "design_doc": "",
}

# v2.0.0 阶段重命名的旧值映射（load_state 惰性迁移用，幂等：新名不在表内原样返回）
# constitution→init、brainstorm→explore、specify/plan→propose（plan 态映射后 propose 契约
# 按产物存在性增量续作：spec 已在只补 tasks）、build→apply；ready/archive 不变。
LEGACY_STAGE_MAP = {
    "constitution": "init",
    "brainstorm": "explore",
    "specify": "propose",
    "plan": "propose",
    "build": "apply",
}


def migrate_legacy_stage(stage: str) -> str:
    """旧版阶段名 → 新版阶段名（v2.0.0 重命名兼容）。

    Args:
        stage: state.json 中读出的 stage 值（可能为 v1.x 旧名）。

    Returns:
        新版阶段名；未知值原样返回（交由状态机校验拒绝）。

    作者：005819 | 协作：GLM-5.3
    """
    return LEGACY_STAGE_MAP.get(stage, stage)


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
    # 惰性迁移：v1.x 旧阶段名（constitution/brainstorm/specify/plan/build）读出即归一，
    # 不主动写回（下次 save_state 自然落盘新值），旧项目无需 reset 即可续跑
    result["stage"] = migrate_legacy_stage(str(result.get("stage", "")))
    return result


def atomic_write_json(path: Path, data: dict) -> None:
    """原子写 JSON 文件（临时文件 + rename），state.json 之外的 specpowers 状态文件（如 auto_base.json）也复用此入口。

    Prevents half-written corruption on crash.

    作者：005819 | 协作：GLM-5.3
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in same directory (ensures same filesystem for atomic rename)
    fd, tmp_path = tempfile.mkstemp(
        suffix=".json",
        prefix=".state-",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        # 原子替换：Windows 下对 PermissionError 重试（见 _atomic_replace）
        _atomic_replace(tmp_path, str(path))
    except Exception:
        # Clean up temp file on failure
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def save_state(root: Path, state: dict) -> None:
    """Atomically write state.json using temp file + rename.

    Prevents half-written corruption on crash.
    """
    save_state_path = _get_state_path(root)
    atomic_write_json(save_state_path, state)


def init_state(root: Path) -> dict:
    """Initialize state.json with defaults and persist."""
    state = dict(DEFAULT_STATE)
    save_state(root, state)
    return state


def reset_state(root: Path) -> dict:
    """Reset state to ready (preserves fallback_count).

    iteration_count 不保留：reset 意味着放弃当前 feature，新需求从首轮（0）开始。
    """
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
