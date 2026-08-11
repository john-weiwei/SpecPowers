"""Dispatcher — stage routing, lock management, auto-read enforcement.

Routes each stage command through:
1) Acquire lock
2) Validate state machine transition
3) Enforce required artifact reads
4) Execute stage logic
5) Release lock
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

from specpowers_cli.bridge.core.errors import (
    FatalError, StateError, ArtifactMissingError,
    ArchiveDuplicateError, RecoverableError,
)
from specpowers_cli.bridge.core.fs_state import load_state, save_state, init_state, reset_state, delete_state
from specpowers_cli.bridge.core.lock import acquire_lock, release_lock, force_unlock
from specpowers_cli.bridge.core.git_util import is_git_repo, has_commits, is_detached_head, git_ref_of
from specpowers_cli.bridge.modules.artifact_registry import required_for


# ---- State machine validation ----

VALID_TRANSITIONS: dict[str, list[str | None]] = {
    "constitution": ["constitution"],  # initial or force
    "ready": ["constitution", "archive"],
    "brainstorm": ["ready"],
    "specify": ["brainstorm", "ready", "build"],
    "plan": ["specify"],
    "build": ["plan", "ready"],
    "archive": ["build"],
}

STAGE_NAMES = ["constitution", "ready", "brainstorm", "specify", "plan", "build", "archive"]


def _validate_transition(from_stage: str, to_stage: str):
    """Validate state machine transition."""
    valid_from = VALID_TRANSITIONS.get(to_stage, [])
    if from_stage not in valid_from and None not in valid_from:
        raise StateError(
            f"Cannot transition from '{from_stage}' to '{to_stage}'. "
            f"Valid from stages: {', '.join(str(v) for v in valid_from)}"
        )


def normalize_feature(raw: str) -> str:
    """Normalize a requirement string into a safe feature slug.

    Rules:
    - Take first 40 characters
    - Remove special characters (keep alphanumeric, spaces, Chinese chars, hyphens)
    - Replace spaces with hyphens
    - Empty input → 'unnamed'
    - Pure Chinese → truncate without replacing
    """
    if not raw or not raw.strip():
        return "unnamed"

    raw = raw.strip()
    # Take first 40 chars (supports Chinese)
    raw = raw[:40]

    # Check if predominantly Chinese (no replacement needed for spaces→hyphens)
    chinese_count = sum(1 for c in raw if '\u4e00' <= c <= '\u9fff')
    if chinese_count > len(raw) * 0.3:
        # Keep Chinese, only replace ASCII spaces and remove truly special chars
        result = re.sub(r'[^\w\u4e00-\u9fff\s-]', '', raw)
        result = re.sub(r'\s+', '-', result)
        result = result.strip('-')
        return result or "unnamed"

    # Non-Chinese: normalize
    result = re.sub(r'[^\w\s-]', '', raw)
    result = re.sub(r'\s+', '-', result)
    result = result.strip('-').lower()
    return result or "unnamed"


def _check_prerequisites(root: Path):
    """Verify git prerequisites before any operation."""
    if not is_git_repo(root):
        raise FatalError(f"'{root}' is not a git repository.")
    if not has_commits(root):
        raise FatalError("Git repository has no commits yet.")
    if is_detached_head(root):
        raise FatalError("Git HEAD is detached. Please checkout a branch first.")


def _run_pre_stage_checks(root: Path, stage: str, mode: str, feature: str = "", from_stage: str = ""):
    """Run checks before entering a stage.

    Args:
        feature: 当前 feature slug。动态路径产物（brief/spec/plan）需用它解析路径。
        from_stage: 调用方来源阶段，用于生成语境友好的错误提示。
    """
    # Enforce auto-read: check required artifacts exist
    artifacts = required_for(stage, mode, feature=feature)
    for art in artifacts:
        # 动态路径产物（brief/spec/plan）的 path 已由 required_for 解析为相对路径
        art_path = root / art["path"]
        if not art_path.exists():
            raise ArtifactMissingError(
                f"Required artifact '{art['path']}' not found. "
                f"Run the previous stage ({art['producer']}) first."
            )

    # proposal 内容校验：倒逼 brainstorm 必须完成探索（防止 brainstorming 被架空）。
    # 进入 specify 时，proposal 除存在外，还必须含「数据流契约」段头或「无跨链路字段」声明。
    # 仅查段头存在性（确定性可判），不评判内容质量（认知层职责）。
    if stage == "specify" and mode == "full":
        _check_proposal_data_flow_contract(root, feature, artifacts, from_stage=from_stage)

    # For fast mode build: check code changes exist
    if stage == "build" and mode == "fast":
        from specpowers_cli.bridge.core.git_util import diff_stat, run_git
        diff = diff_stat(root)  # working tree vs HEAD
        if not diff.strip():
            # Check if there's a recent commit
            try:
                diff2 = run_git(["diff", "--stat", "HEAD~1..HEAD"], cwd=root)
                if not diff2.strip():
                    raise FatalError(
                        "No code changes detected. "
                        "Complete your coding before running /specpowers.build"
                    )
            except Exception:
                raise FatalError(
                    "No code changes detected. "
                    "Complete your coding before running /specpowers.build"
                )


def _check_proposal_data_flow_contract(root: Path, feature: str, artifacts: list, from_stage: str = "") -> None:
    """校验 proposal.md 含「数据流契约」小节（specify 阶段硬依赖）。

    防止 brainstorming 被架空：agent 若跳过探索直接收口，proposal 不会含数据流契约，
    本校验将其拦在 specify 之外，强制回 brainstorm 补全探索。

    Args:
        root: 项目根路径。
        feature: feature slug，用于定位 proposal 路径。
        artifacts: required_for 返回的 artifact 列表（含已解析路径）。
        from_stage: 调用方来源阶段（如 build），用于生成语境友好的错误提示。

    Raises:
        ArtifactMissingError: proposal 缺「数据流契约」段头且无「无跨链路字段」声明时。
    """
    # 从 artifacts 中找 proposal 的已解析路径（动态产物 path 已被 required_for 解析）
    proposal_path = None
    for art in artifacts:
        # proposal 是动态产物，解析后含 openspec/changes/<feature>/proposal.md
        if art["path"].endswith("proposal.md"):
            proposal_path = root / art["path"]
            break

    # 调用点（_run_pre_stage_checks）限定 stage="specify" + mode="full"，
    # 此条件下 required_for 必返回 proposal，且文件存在性已由上层循环校验。
    # 此处保留防御：proposal_path 为 None 属上游逻辑错误，应显式暴露而非静默跳过。
    if proposal_path is None:
        raise ArtifactMissingError(
            "proposal 路径解析失败：artifacts 中未找到 proposal.md，"
            "这通常是上游逻辑错误（required_for 未按 full 模式返回 proposal），请排查。"
        )

    content = proposal_path.read_text(encoding="utf-8")
    # 校验：含「## 数据流契约」二级段头，或显式声明「本特性无跨链路字段」。
    # 必须为二级段头（##），与 brainstorm.md 模板一致；三级或无井号不匹配。
    has_contract = re.search(r"^##\s*数据流契约", content, re.MULTILINE)
    has_skip_decl = "本特性无跨链路字段" in content
    if not has_contract and not has_skip_decl:
        # 区分 fallback 语境生成友好提示
        fallback_hint = ""
        if from_stage == "build":
            fallback_hint = (
                "（你正在从 build 回退并升级为完整流程，需先补跑 brainstorm 完成探索，"
                "再继续后续阶段）"
            )
        raise ArtifactMissingError(
            f"proposal.md 缺少「## 数据流契约」小节。"
            f"这是 specify 阶段的硬依赖——说明 brainstorm 探索未完成（brainstorming 可能被跳过）。"
            f"{fallback_hint}"
            f"请回到 /specpowers.brainstorm 调用 superpowers brainstorming 完成需求探索，"
            f"并在 proposal.md 补全「数据流契约」小节"
            f"（涉及跨链路字段则按字段卡片逐个详述，纯本地特性则声明「本特性无跨链路字段」）。"
        )


def _check_constitution_conflict(root: Path):
    """Check if constitution command would discard an in-progress feature."""
    state = load_state(root)
    if state.get("stage") != "constitution":
        # Interactive confirmation needed — in CI mode, auto-confirm
        if is_ci_mode():
            print("[CI] Auto-confirming constitution re-generation (would discard feature "
                  f"'{state.get('feature', '')}')", file=sys.stderr)
        else:
            feature = state.get("feature", "")
            raise StateError(
                f"Current feature '{feature}' is in progress (stage: {state.get('stage')}). "
                f"Use --force to discard and rebuild constitution, "
                f"or /specpowers.reset to start fresh."
            )


def is_ci_mode() -> bool:
    """Check if running in CI mode."""
    import os
    return os.environ.get("SPECPOWERS_CI", "").strip() == "1"


def is_verbose() -> bool:
    """Check if verbose logging is enabled."""
    import os
    return os.environ.get("SPECPOWERS_VERBOSE", "").strip() == "1"


def _log_verbose(msg: str):
    """Log verbose message to stderr."""
    if is_verbose():
        print(f"[specpowers] {msg}", file=sys.stderr)


# ---- Stage handlers ----

def _handle_constitution(root: Path, extra: dict) -> int:
    """Handle constitution stage."""
    force = extra.get("force", False)
    state = load_state(root)

    if not force and state.get("stage") != "constitution":
        _check_constitution_conflict(root)

    _log_verbose("Running baseline scanner...")
    from specpowers_cli.bridge.modules.baseline_scanner import scan, load_baseline

    baseline_path = root / ".specpowers" / "baseline.json"
    if baseline_path.exists() and not force:
        _log_verbose(".specpowers/constitution.md and baseline.json exist, skipping.")
    else:
        if force and baseline_path.exists():
            baseline_path.unlink()
        scan(root)

    # Transition: constitution → ready
    new_state = load_state(root)
    new_state["stage"] = "ready"
    new_state["mode"] = "full"
    new_state["feature"] = ""
    save_state(root, new_state)

    print("Constitution + baseline ready. Stage: ready")
    return 0


def _handle_brainstorm(root: Path, extra: dict) -> int:
    """Handle brainstorm stage."""
    req = extra.get("requirement", "")
    feature = normalize_feature(req)
    state = load_state(root)

    _validate_transition(state["stage"], "brainstorm")

    _check_prerequisites(root)
    _run_pre_stage_checks(root, "brainstorm", "full", feature)

    # Update state
    state["stage"] = "brainstorm"
    state["mode"] = "full"
    state["feature"] = feature
    save_state(root, state)

    print(f"Brainstorm started for feature: {feature}")
    print("Agent should now: call superpowers `brainstorming` skill to explore the requirement, "
          f"write openspec/changes/{feature}/proposal.md (must include 「## 数据流契约」 section), "
          "then continue to /specpowers.specify")
    return 0


def _handle_specify(root: Path, extra: dict) -> int:
    """Handle specify stage."""
    req = extra.get("requirement", "")
    state = load_state(root)
    from_stage = state["stage"]

    _validate_transition(from_stage, "specify")

    # Feature 锁定：优先复用 state 中已有 feature（保证同一流程文件名前缀一致），
    # 仅当 feature 为空时才 normalize 当前 requirement
    existing_feature = state.get("feature", "")
    if existing_feature and existing_feature.strip():
        feature = existing_feature
    else:
        feature = normalize_feature(req)

    _check_prerequisites(root)
    _run_pre_stage_checks(root, "specify", "full", feature, from_stage=from_stage)

    state["stage"] = "specify"
    state["mode"] = "full"
    state["feature"] = feature
    save_state(root, state)

    print(f"Specify started for feature: {feature}")
    return 0


def _handle_fast(root: Path, extra: dict) -> int:
    """Handle fast mode entry."""
    req = extra.get("requirement", "")
    state = load_state(root)

    # fast 不是状态机的真实目标 stage（它把状态设为 ready+mode=fast），
    # 因此不能用 _validate_transition(state["stage"], "fast")——VALID_TRANSITIONS
    # 里没有 "fast" 键，会误拒绝所有合法调用。fast 的合法入口与 brainstorm 一致，
    # 仅允许从 ready 进入。
    # 作者：005819 | 协作：GLM-5.2
    valid_fast_from = ["ready"]
    if state["stage"] not in valid_fast_from:
        raise StateError(
            f"Cannot start fast mode from '{state['stage']}'. "
            f"Valid from stages: {', '.join(valid_fast_from)}"
        )

    _check_prerequisites(root)

    # Check constitution/baseline exist (hard gate for fast mode)
    baseline_path = root / ".specpowers" / "baseline.json"
    if not baseline_path.exists():
        raise FatalError(
            "Baseline not found. Run /specpowers.constitution first."
        )

    # Feature 锁定：优先复用已有 feature，仅空时才 normalize
    existing_feature = state.get("feature", "")
    if existing_feature and existing_feature.strip():
        feature = existing_feature
    else:
        feature = normalize_feature(req)

    state["stage"] = "ready"
    state["mode"] = "fast"
    state["feature"] = feature
    save_state(root, state)

    print(f"Fast mode activated for feature: {feature}")
    print("Agent will now: run small-judgment → confirmation → user codes → /specpowers.build")
    return 0


def _handle_plan(root: Path, extra: dict) -> int:
    """Handle plan stage."""
    state = load_state(root)
    feature = state.get("feature", "")
    _validate_transition(state["stage"], "plan")

    _check_prerequisites(root)
    _run_pre_stage_checks(root, "plan", "full", feature)

    state["stage"] = "plan"
    save_state(root, state)
    print("Plan stage ready.")
    return 0


def _handle_build(root: Path, extra: dict) -> int:
    """Handle build stage."""
    state = load_state(root)
    mode = state.get("mode", "full")
    from_stage = state["stage"]
    feature = state.get("feature", "")

    _validate_transition(from_stage, "build")

    _check_prerequisites(root)
    _run_pre_stage_checks(root, "build", mode, feature)

    state["stage"] = "build"
    save_state(root, state)

    if mode == "fast":
        print("Build stage (fast mode). Agent will run: code extraction → structure gate → execute → verify.")
    else:
        print("Build stage (full mode). Agent will run: structure gate → ability pool → execute → verify.")
    return 0


def _handle_archive(root: Path, extra: dict) -> int:
    """Handle archive stage — 确定性执行归档（委托 OpenSpec）。

    full 和 fast 统一：调 openspec archive 合并主规格 + change 移到 archive 快照。
    产物（proposal/specs/tasks）由前面阶段增量写入 change 目录，archive 零转换。
    """
    state = load_state(root)
    force_merge = extra.get("force_merge_check", False)
    mode = state.get("mode", "full")
    feature = state.get("feature", "")

    _validate_transition(state["stage"], "archive")

    # Duplicate check: has this feature already been archived?
    from specpowers_cli.bridge.modules.archive_auditor import is_feature_archived
    if feature and is_feature_archived(root, feature):
        raise ArchiveDuplicateError(
            f"Feature '{feature}' already has an archive commit. "
            f"Run: git pull && /specpowers.reset to sync."
        )

    _check_prerequisites(root)
    _run_pre_stage_checks(root, "archive", mode, feature)

    # Merge check（仅检测并提示，归档本身不依赖它）
    from specpowers_cli.bridge.modules.archive_auditor import merge_check_detect
    should_merge_check = force_merge or merge_check_detect(
        root, state.get("last_archive_ref", "")
    )
    if should_merge_check and mode != "fast":
        print("⚠ Merge check triggered — multi-branch or forced. Agent will run post-merge verification.")

    # full + fast 统一：调 openspec archive 归档（产物已是 OpenSpec 格式，无转换）
    if feature:
        from specpowers_cli.bridge.modules.archive_auditor import prepare_openspec_archive
        archive_result = prepare_openspec_archive(root, feature, state)
        archived_as = archive_result.get("archivedAs", feature)
        specs_updated = archive_result.get("specsUpdated", False)

        # 归档成功：刷新 state，stage 跃迁到 ready
        # 清空 execution_mode：本 feature 的执行模式不应被下一轮 feature 继承
        state["last_archive_ref"] = git_ref_of(root)
        state["stage"] = "ready"
        state["feature"] = ""
        state["mode"] = "full"
        state["execution_mode"] = ""
        save_state(root, state)

        print(f"Archive 完成。Feature '{feature}' 已归档为 '{archived_as}'。")
        if specs_updated:
            print(f"  - 主规格合并：✓ delta 已合并到 openspec/specs/<capability>/spec.md")
        else:
            print(f"  - 主规格合并：（无 delta 需合并）")
        print(f"  - change 快照：openspec/changes/archive/{archived_as}/")
        print(f"准备下一轮开发：/specpowers.brainstorm | .specify | .fast")
        return 0

    # feature 为空：不应发生（archive 要求 state 有 feature），兜底报错
    raise FatalError("Cannot archive: no active feature in state. Run a stage that sets feature first.")


def _handle_baseline(root: Path, extra: dict) -> int:
    """Handle baseline refresh."""
    _check_prerequisites(root)
    from specpowers_cli.bridge.modules.baseline_scanner import scan
    scan(root)
    print("Baseline refreshed. Please review and commit .specpowers/baseline.json.")
    return 0


def _handle_reset(root: Path, extra: dict) -> int:
    """Handle reset — 委托 fs_state.reset_state 保证 state 结构与 DEFAULT_STATE 一致。

    reset 跳过 route 的锁获取（见 route），但需主动清理可能残留的锁文件。
    原实现硬编码 state 字典，与 DEFAULT_STATE 脱钩：若 DEFAULT_STATE 演进新增 key，
    这里不会同步，导致 reset 后的 state 缺 key。改委托 reset_state 避免重复实现。
    作者：005819 | 协作：GLM-5.2
    """
    # 清理可能残留的锁文件（reset 跳过 route 的 acquire_lock，直接 force_unlock）
    force_unlock(root)

    # 委托 fs_state：load→保留 fallback_count→save，结构与 DEFAULT_STATE 始终一致
    reset_state(root)

    print("State reset to ready. (fallback_count preserved)")
    return 0


# ---- Route table ----

STAGE_HANDLERS = {
    "constitution": _handle_constitution,
    "brainstorm": _handle_brainstorm,
    "specify": _handle_specify,
    "fast": _handle_fast,
    "plan": _handle_plan,
    "build": _handle_build,
    "archive": _handle_archive,
    "baseline": _handle_baseline,
    "reset": _handle_reset,
}


def route(stage: str, mode: str, root: Path, extra: dict | None = None) -> int:
    """Route a stage command to its handler.

    This is the main entry point for all stage operations.
    Called by facade.py command handlers.

    Args:
        stage: Stage name (constitution, brainstorm, specify, fast, plan, build, archive, baseline, reset)
        mode: Operation mode (full or fast)
        root: Project root path
        extra: Additional parameters (requirement, force, force_merge_check, etc.)

    Returns:
        Exit code (0 = success)
    """
    if extra is None:
        extra = {}

    handler = STAGE_HANDLERS.get(stage)
    if handler is None:
        raise ValueError(f"Unknown stage: {stage}")

    # Ensure .specpowers directory exists
    specpowers_dir = root / ".specpowers"
    specpowers_dir.mkdir(parents=True, exist_ok=True)

    # Ensure state.json exists
    state_path = specpowers_dir / "state.json"
    if not state_path.exists():
        init_state(root)

    # Acquire lock (except for reset which bypasses lock)
    # acquire_lock 成功返回 True，失败抛 LockAcquireError(FatalError 子类)
    if stage != "reset":
        acquire_lock(root, timeout=0)

    try:
        _register_signal_handlers(root)

        result = handler(root, extra)
        release_lock(root)
        return result

    except Exception:
        release_lock(root)
        raise


# 信号处理：进程级只注册一次，避免每次 route() 覆盖宿主程序的信号处理
_signal_registered = False
_current_root: Path | None = None


def _register_signal_handlers(root: Path):
    """注册 SIGINT/SIGTERM 处理器（仅首次注册）。

    信号处理是进程级全局副作用：若每次 route() 都重复注册，会覆盖宿主程序
    （如 agent 框架）自己管理的信号处理。因此用模块级标志保证只注册一次，
    并通过 _current_root 让 handler 能找到正确的项目根来释放锁。
    Windows 下 SIGTERM 行为与 Unix 不同且不常用，跳过以避免副作用。
    """
    import signal
    from specpowers_cli.bridge.core.platform import is_windows

    global _signal_registered, _current_root
    _current_root = root
    if _signal_registered:
        return

    def _signal_handler(signum, frame):
        """SIGINT/SIGTERM：保存状态并释放锁后退出。"""
        print("\n[specpowers] Interrupted. Saving state and releasing lock...", file=sys.stderr)
        if _current_root is not None:
            release_lock(_current_root)
        sys.exit(130)

    signal.signal(signal.SIGINT, _signal_handler)
    if not is_windows():
        # Windows 上 SIGTERM 存在但语义不同（非实时信号），跳过
        signal.signal(signal.SIGTERM, _signal_handler)
    _signal_registered = True
