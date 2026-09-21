"""Dispatcher — stage routing, lock management, auto-read enforcement.

Routes each stage command through:
1) Acquire lock
2) Validate state machine transition
3) Enforce required artifact reads
4) Execute stage logic
5) Release lock
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from specpowers_cli.bridge.core.errors import (
    FatalError, StateError, ArtifactMissingError,
    ArchiveDuplicateError, RecoverableError,
)
from specpowers_cli.bridge.core.fs_state import (
    load_state, save_state, init_state, reset_state, delete_state, atomic_write_json,
)
from specpowers_cli.bridge.core.lock import acquire_lock, release_lock, force_unlock
from specpowers_cli.bridge.core.git_util import is_git_repo, has_commits, is_detached_head, git_ref_of
from specpowers_cli.bridge.modules.artifact_registry import required_for


# ---- State machine validation ----

VALID_TRANSITIONS: dict[str, list[str | None]] = {
    "init": ["init"],  # initial or force
    "ready": ["init", "archive"],
    "explore": ["ready"],
    # propose 自环（from propose）：迭代轮已由 iterate/auto new-round 把 stage 置回 propose，
    # 用户重跑 /specpowers-propose 属续作修订（iteration_count 不变、不消耗 fallback 额度），应放行
    "propose": ["explore", "ready", "apply", "propose"],
    "apply": ["propose", "ready"],
    "archive": ["apply"],
}

STAGE_NAMES = ["init", "ready", "explore", "propose", "apply", "archive"]


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
    - 保留字（archive / Windows 设备名）追加后缀消歧（见 path_resolver.sanitize_feature_slug）
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
        return _finalize_feature_slug(result)

    # Non-Chinese: normalize
    result = re.sub(r'[^\w\s-]', '', raw)
    result = re.sub(r'\s+', '-', result)
    result = result.strip('-').lower()
    return _finalize_feature_slug(result)


def _finalize_feature_slug(slug: str) -> str:
    """slug 出口统一处理：空值兜底 + 保留字消歧。

    Args:
        slug: normalize_feature 各分支产出的候选 slug。

    Returns:
        可安全用作 change 目录名的最终 slug。
    """
    from specpowers_cli.bridge.modules.path_resolver import sanitize_feature_slug

    if not slug:
        return "unnamed"
    return sanitize_feature_slug(slug)


# ---- auto 模式多轮迭代（方案 docs/auto-iteration-plan.md） ----

def _auto_base_path(root: Path) -> Path:
    """Return path to .specpowers/auto_base.json."""
    return root / ".specpowers" / "auto_base.json"


def _load_auto_base(root: Path) -> dict | None:
    """读取 auto_base.json；不存在返回 None，损坏抛 FatalError 引导人工处理。

    作者：005819 | 协作：GLM-5.3
    """
    path = _auto_base_path(root)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise FatalError(
            f"auto_base.json 解析失败: {e}。"
            "请人工检查或删除该文件后重试 /specpowers-auto。"
        )


def _write_auto_base(root: Path, data: dict) -> None:
    """原子写 auto_base.json（复用 fs_state.atomic_write_json，与 state.json 同一保障）。"""
    atomic_write_json(_auto_base_path(root), data)


def _design_doc_hash(design_doc: str) -> str | None:
    """计算设计文档内容的 sha256；文件不存在返回 None。

    Args:
        design_doc: 设计文档路径（绝对或相对 cwd）。

    Returns:
        十六进制 hash 字符串，文件不存在时 None。
    """
    path = Path(design_doc)
    if not design_doc or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _same_path(left: str, right: str) -> bool:
    """跨平台路径等价比较（Windows 大小写不敏感、分隔符归一）。"""
    return os.path.normcase(os.path.normpath(left)) == os.path.normcase(os.path.normpath(right))


def _utc_now_iso() -> str:
    """当前 UTC 时间的 ISO 格式字符串（rounds 记录用）。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _migrate_legacy_auto_base(base: dict) -> list[dict]:
    """旧格式 auto_base.json（无 rounds 字段）按 round 1 兼容迁移。

    Args:
        base: 已读取的 auto_base.json 内容。

    Returns:
        迁移后的 rounds 列表（含首轮一条记录，标注迁移来源）。
    """
    return [{
        "round": 1,
        "input": {"type": "doc", "doc": base.get("design_doc", ""), "instruction": ""},
        "started_at": base.get("created_at", ""),
        "note": "旧格式 auto_base.json 自动迁移（原文件无 rounds 字段）",
    }]


def _clarification_view(base: dict | None, has_new_input: bool) -> dict | None:
    """从 auto_base.json 提取需求澄清结论视图（方案 docs/auto-clarification-plan.md）。

    pending_input 语义：上一轮澄清 ceiling=explore（停靠 explore 等待方案结论）
    且本次重入无新输入 → 契约层不得从断点盲目续跑 propose，需提示用户带结论重入。

    Args:
        base: 已读取的 auto_base.json 内容（None 或旧格式无 clarification 字段 → 返回 None，
              契约层据 null 补做澄清）。
        has_new_input: 本次重入是否携带新输入（文档变更 / 口头指令）。

    Returns:
        澄清结论视图字典，无澄清记录时 None。

    作者：005819 | 协作：GLM-5.3
    """
    if base is None:
        return None
    clar = base.get("clarification")
    if not isinstance(clar, dict) or not clar.get("ceiling"):
        return None
    # 旧值兼容：v1.x 登记 ceiling=brainstorm（停靠在原 brainstorm 阶段），
    # 读出归一为 explore（v2.0.0 同一停靠语义的新阶段名）
    ceiling = "explore" if str(clar["ceiling"]) == "brainstorm" else str(clar["ceiling"])
    return {
        "ceiling": ceiling,
        "report_path": clar.get("report_path", ""),
        "checked_at": clar.get("checked_at", ""),
        "pending_input": ceiling == "explore" and not has_new_input,
    }


def auto_status(root: Path, design_doc: str = "", instruction: str = "") -> dict:
    """auto 模式重入三分判定：fresh / resume / iterate（facade auto-status 子命令入口）。

    需求身份由归档状态唯一决定，与设计文档解耦：
    - fresh：无活跃 feature（已归档或从未开始）；发现 auto_base.json 残留则顺带清理
    - resume：活跃需求 + 无任何新输入（文档 hash 未变、无指令）→ 断点续跑
    - iterate：活跃需求 + 任一新输入（文档实质变更 / 口头指令）→ 同需求新迭代轮

    判定只读 state 与产物，不做状态跃迁；轮次切换必须走 auto new-round。
    响应携带 clarification 视图（上一轮澄清结论 + pending_input），供契约层
    做 resume 停靠保护与迭代轮增量澄清。

    作者：005819 | 协作：GLM-5.3
    """
    state = load_state(root)
    feature = (state.get("feature") or "").strip()
    base = _load_auto_base(root)

    # fresh：无活跃 feature（archive 后 stage=ready 且 feature 空，或从未开始）
    if not feature and state["stage"] in ("ready", "init"):
        removed = False
        if base is not None:
            # 上一需求的 auto_base.json 残留（旧版本归档清理缺失所遗留）→ 清理后按全新执行
            _auto_base_path(root).unlink()
            removed = True
        return {
            "mode": "fresh",
            "feature": "",
            "round": 0,
            "iteration_count": 0,
            "stage": state["stage"],
            "scope_hint": "",
            "reason": "无活跃 feature，按全新需求执行（设计文档必填）",
            "design_doc_exists": None,
            "auto_base_removed": removed,
            "clarification": None,
        }

    # 活跃需求（full 流水线中 / fast 待编码）：base 缺失 = 人工流程被 auto 接管
    if base is None:
        return {
            "mode": "iterate",
            "feature": feature,
            "round": state.get("iteration_count", 0) + 1,
            "iteration_count": state.get("iteration_count", 0),
            "stage": state["stage"],
            "scope_hint": "full",
            "reason": "存在未归档的活跃 feature 但缺 auto_base.json（人工流程接管），保守按全量迭代执行并补建基线",
            "design_doc_exists": None,
            "auto_base_missing": True,
            "clarification": None,
        }

    # 新输入判定：口头指令非空，或文档内容 hash 相对基线发生变化
    doc_changed = False
    design_doc_exists: bool | None = None
    if design_doc.strip():
        new_hash = _design_doc_hash(design_doc)
        design_doc_exists = new_hash is not None
        if new_hash is None:
            # 文档不存在：保守按有新输入处理，存在性标记交契约层做参数校验
            doc_changed = True
        else:
            old_hash = base.get("design_doc_hash", "")
            if old_hash:
                doc_changed = new_hash != old_hash
            else:
                # 旧格式无 hash 基准：同路径视为未变（信任续跑），异路径视为新输入
                old_doc = (base.get("design_doc") or "").strip()
                doc_changed = (not old_doc) or (not _same_path(old_doc, design_doc))
    has_new_input = bool(instruction.strip()) or doc_changed

    round_now = state.get("iteration_count", 0)
    if not has_new_input:
        return {
            "mode": "resume",
            "feature": feature,
            "round": round_now,
            "iteration_count": round_now,
            "stage": state["stage"],
            "scope_hint": "",
            "reason": "无新输入（文档未变且无指令），按断点续跑：读 state stage + 产物存在性定位断点，已完成阶段不重做",
            "design_doc_exists": design_doc_exists,
            "clarification": _clarification_view(base, has_new_input=False),
        }

    # 迭代深度建议：文档实质变更 → full；仅口头指令 → light（最终由契约层按裁决规则表定夺）
    if doc_changed:
        scope_hint = "full"
        reason = "设计文档相对上一轮已变更，重新解析八要素后按迭代轮推进"
    else:
        scope_hint = "light"
        reason = "仅提供口头调整指令，若无歧义映射到现有 scenario 修订可走轻量路径（spec 必改底线不变）"
    return {
        "mode": "iterate",
        "feature": feature,
        "round": round_now + 1,
        "iteration_count": round_now,
        "stage": state["stage"],
        "scope_hint": scope_hint,
        "reason": reason,
        "design_doc_exists": design_doc_exists,
        "clarification": _clarification_view(base, has_new_input=True),
    }


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

    # 设计文档登记校验：倒逼 explore 必须完成探索并登记（防止探索被架空）。
    # 仅从 explore 进入 propose 时校验（跳过探索直入 propose 的 ready 路径、
    # apply fallback 路径、迭代续作自环路径均不要求）。
    if stage == "propose" and mode == "full" and from_stage == "explore":
        _check_design_doc_registered(root)

    # proposal 内容校验：倒逼 propose 必须承接 explore 探索结论（防架空）。
    # 进入 apply 时，proposal 除存在外，还必须含「数据流契约」段头或「无跨链路字段」声明。
    # 仅查段头存在性（确定性可判），不评判内容质量（认知层职责）。
    # fast 模式无 proposal（跳过 explore/propose），不校验。
    if stage == "apply" and mode == "full":
        _check_proposal_data_flow_contract(root, feature, artifacts, from_stage=from_stage)

    # For fast mode apply: check code changes exist
    if stage == "apply" and mode == "fast":
        from specpowers_cli.bridge.core.git_util import diff_stat, run_git
        diff = diff_stat(root)  # working tree vs HEAD
        if not diff.strip():
            # 工作区无变更：检查最近一次提交
            try:
                diff2 = run_git(["diff", "--stat", "HEAD~1..HEAD"], cwd=root)
            except Exception:
                # HEAD~1 不存在（仓库仅有单个提交）：回退对比首个提交与空树（--root）
                try:
                    diff2 = run_git(["diff", "--stat", "--root", "HEAD"], cwd=root)
                except Exception:
                    diff2 = ""
            if not diff2.strip():
                raise FatalError(
                    "No code changes detected. "
                    "Complete your coding before running /specpowers.apply"
                )


def _check_design_doc_registered(root: Path) -> None:
    """校验 explore 阶段的设计文档已登记（propose 从 explore 进入时的硬依赖）。

    防止探索被架空：explore 落盘设计文档后经 `facade record-design-doc` 登记路径到
    state.design_doc。agent 若跳过 specpowers-explore 探索直接收口，不会产生设计文档，
    本校验将其拦在 propose 之外，强制回 explore 完成探索。

    Args:
        root: 项目根路径。

    Raises:
        ArtifactMissingError: state.design_doc 为空，或登记的文件不存在。

    作者：005819 | 协作：GLM-5.3
    """
    state = load_state(root)
    design_doc = (state.get("design_doc") or "").strip()

    if not design_doc:
        raise ArtifactMissingError(
            "explore 阶段的设计文档未登记（state.design_doc 为空）。"
            "这是 propose 从 explore 进入的硬依赖——说明 explore 探索未完成"
            "（specpowers-explore 可能被跳过）。"
            "请回到 /specpowers.explore 调用内置 specpowers-explore 技能完成需求探索，"
            "设计文档落盘 docs/specpowers/design/ 后调 "
            "`facade record-design-doc <设计文档路径>` 登记，再进入 /specpowers.propose"
        )

    if not Path(design_doc).is_file():
        raise ArtifactMissingError(
            f"登记的设计文档 '{design_doc}' 不存在。"
            "请确认文件未被移动/删除，或回 /specpowers.explore 重新探索并登记"
        )


def _check_proposal_data_flow_contract(root: Path, feature: str, artifacts: list, from_stage: str = "") -> None:
    """校验 proposal.md 含「数据流契约」小节（apply 阶段硬依赖）。

    防止探索结论被架空：agent 若跳过 explore/propose 直写 proposal，proposal 不会含
    数据流契约，本校验将其拦在 apply 之外，强制回 propose 补全（propose 生成 proposal
    时必须承接 explore 设计文档的数据流结论）。

    Args:
        root: 项目根路径。
        feature: feature slug，用于定位 proposal 路径。
        artifacts: required_for 返回的 artifact 列表（含已解析路径）。
        from_stage: 调用方来源阶段（如 propose），用于生成语境友好的错误提示。

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

    # 调用点（_run_pre_stage_checks）限定 stage="apply" + mode="full"，
    # 此条件下 required_for 必返回 proposal，且文件存在性已由上层循环校验。
    # 此处保留防御：proposal_path 为 None 属上游逻辑错误，应显式暴露而非静默跳过。
    if proposal_path is None:
        raise ArtifactMissingError(
            "proposal 路径解析失败：artifacts 中未找到 proposal.md，"
            "这通常是上游逻辑错误（required_for 未按 full 模式返回 proposal），请排查。"
        )

    content = proposal_path.read_text(encoding="utf-8")
    # 校验：含「## 数据流契约」二级段头，或显式声明「本特性无跨链路字段」。
    # 必须为二级段头（##），与 propose.md 模板一致；三级或无井号不匹配。
    has_contract = re.search(r"^##\s*数据流契约", content, re.MULTILINE)
    has_skip_decl = "本特性无跨链路字段" in content
    if not has_contract and not has_skip_decl:
        # 区分回退语境生成友好提示
        fallback_hint = ""
        if from_stage == "propose":
            fallback_hint = (
                "（你正在从 propose 刚进入 apply，说明上一轮 propose 未承接 explore "
                "设计文档的数据流结论，需回 /specpowers.propose 补全 proposal 后再继续）"
            )
        raise ArtifactMissingError(
            f"proposal.md 缺少「## 数据流契约」小节。"
            f"这是 apply 阶段的硬依赖——说明 explore 探索结论未被 propose 承接"
            f"（探索可能被跳过或 proposal 凭空生成）。"
            f"{fallback_hint}"
            f"请回到 /specpowers.propose 基于 explore 设计文档重新生成 proposal.md"
            f"并补全「## 数据流契约」小节"
            f"（涉及跨链路字段则按字段卡片逐个详述，纯本地特性则声明「本特性无跨链路字段」）。"
        )


def _check_init_conflict(root: Path):
    """Check if init command would discard an in-progress feature."""
    state = load_state(root)
    if state.get("stage") != "init":
        # Interactive confirmation needed — in CI mode, auto-confirm
        if is_ci_mode():
            print("[CI] Auto-confirming init re-generation (would discard feature "
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

def _handle_init(root: Path, extra: dict) -> int:
    """Handle init stage."""
    force = extra.get("force", False)
    state = load_state(root)

    if not force and state.get("stage") != "init":
        _check_init_conflict(root)

    _log_verbose("Running baseline scanner...")
    from specpowers_cli.bridge.modules.baseline_scanner import scan, load_baseline

    baseline_path = root / ".specpowers" / "baseline.json"
    if baseline_path.exists() and not force:
        _log_verbose(".specpowers/constitution.md and baseline.json exist, skipping.")
    else:
        if force and baseline_path.exists():
            baseline_path.unlink()
        scan(root)

    # Transition: init → ready
    # design_doc 一并清空：init 重置意味着放弃当前 feature 流水线，
    # 探索指针不应泄给下一需求（下一需求的 explore 会重新登记）
    new_state = load_state(root)
    new_state["stage"] = "ready"
    new_state["mode"] = "full"
    new_state["feature"] = ""
    new_state["design_doc"] = ""
    save_state(root, new_state)

    print("Constitution + baseline ready. Stage: ready")
    return 0


def _handle_explore(root: Path, extra: dict) -> int:
    """Handle explore stage."""
    req = extra.get("requirement", "")
    state = load_state(root)

    _validate_transition(state["stage"], "explore")

    # feature 锁定：--feature 显式指定优先（auto 模式多轮迭代用首轮 slug 锁定 change 目录，
    # 防止 requirement 措辞变化导致 slug 漂移、调整脱离当前 spec 文件），
    # 其次 normalize requirement 兜底。
    # 作者：005819 | 协作：GLM-5.3
    explicit_feature = (extra.get("feature") or "").strip()
    if explicit_feature:
        feature = _finalize_feature_slug(explicit_feature)
    else:
        feature = normalize_feature(req)

    _check_prerequisites(root)
    _run_pre_stage_checks(root, "explore", "full", feature)

    # Update state
    state["stage"] = "explore"
    state["mode"] = "full"
    state["feature"] = feature
    save_state(root, state)

    print(f"Explore started for feature: {feature}")
    print("Agent should now: invoke the built-in specpowers-explore skill to explore the requirement, "
          "write the design doc under docs/specpowers/design/ "
          "(incl. data-flow conclusions), register it via "
          f"`facade record-design-doc <path>`, then continue to /specpowers.propose")
    return 0


def _handle_propose(root: Path, extra: dict) -> int:
    """Handle propose stage — 一站式生成 OpenSpec change 三件套。

    合并原 specify + plan：从 explore 设计文档（或跳过探索的清晰需求）出发，
    依次落盘 proposal.md → spec.md → tasks.md（认知层按 prompts/propose.md 执行，
    确定性层只做状态机与前置校验）。
    """
    req = extra.get("requirement", "")
    state = load_state(root)
    from_stage = state["stage"]

    _validate_transition(from_stage, "propose")

    # 回退上限（fast_mode.md/propose.md 承诺「fallback_count += 1、整个 state
    # 生命周期最多 1 次 apply→propose 回退」）：原实现不计数也不拦截，
    # 流程可无限次往返抖动。此处把承诺落地为确定性层硬校验
    # 作者：005819 | 协作：GLM-5.3
    if from_stage == "apply":
        fallback_count = state.get("fallback_count", 0)
        if fallback_count >= 1:
            raise StateError(
                "回退次数已达上限：整个 state 生命周期最多 1 次 apply→propose 回退。"
                "请先完成当前流程（archive）或重置（reset 不清除计次），"
                "再开启新的 feature。"
            )
        state["fallback_count"] = fallback_count + 1

    # Feature 锁定：--feature 显式指定 > state 已有 feature（同一流程文件名前缀一致）>
    # normalize 当前 requirement 兜底。
    # 作者：005819 | 协作：GLM-5.3
    explicit_feature = (extra.get("feature") or "").strip()
    existing_feature = state.get("feature", "")
    if explicit_feature:
        feature = _finalize_feature_slug(explicit_feature)
    elif existing_feature and existing_feature.strip():
        feature = existing_feature
    else:
        feature = normalize_feature(req)

    _check_prerequisites(root)
    _run_pre_stage_checks(root, "propose", "full", feature, from_stage=from_stage)

    state["stage"] = "propose"
    state["mode"] = "full"
    state["feature"] = feature
    save_state(root, state)

    print(f"Propose started for feature: {feature}")
    return 0


def _handle_fast(root: Path, extra: dict) -> int:
    """Handle fast mode entry."""
    req = extra.get("requirement", "")
    state = load_state(root)

    # fast 不是状态机的真实目标 stage（它把状态设为 ready+mode=fast），
    # 因此不能用 _validate_transition(state["stage"], "fast")——VALID_TRANSITIONS
    # 里没有 "fast" 键，会误拒绝所有合法调用。fast 的合法入口与 explore 一致，
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
            "Baseline not found. Run /specpowers.init first."
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
    print("Agent will now: run small-judgment → confirmation → user codes → /specpowers.apply")
    return 0


def _handle_apply(root: Path, extra: dict) -> int:
    """Handle apply stage."""
    state = load_state(root)
    mode = state.get("mode", "full")
    from_stage = state["stage"]
    feature = state.get("feature", "")

    _validate_transition(from_stage, "apply")

    _check_prerequisites(root)
    _run_pre_stage_checks(root, "apply", mode, feature)

    state["stage"] = "apply"
    save_state(root, state)

    if mode == "fast":
        print("Apply stage (fast mode). Agent will run: code extraction → structure gate → execute → verify.")
    else:
        print("Apply stage (full mode). Agent will run: structure gate → ability pool → execute → verify.")
    return 0


def _handle_archive(root: Path, extra: dict) -> int:
    """Handle archive stage — 确定性执行归档（委托 OpenSpec）。

    full 和 fast 统一：调 openspec archive 合并主规格 + change 移到 archive 快照。
    产物（proposal/specs/tasks）由 propose 阶段一次性写入 change 目录，archive 零转换。
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
        # iteration_count 清零：归档即新需求，下一轮从首轮开始（方案第 5 节）
        # design_doc 清空：设计文档指针随需求生命周期终结，不泄给下一轮
        # 作者：005819 | 协作：GLM-5.3
        state["last_archive_ref"] = git_ref_of(root)
        state["stage"] = "ready"
        state["feature"] = ""
        state["mode"] = "full"
        state["execution_mode"] = ""
        state["iteration_count"] = 0
        state["design_doc"] = ""
        save_state(root, state)

        # 归档即需求生命周期终结：清理 auto_base.json（手动 archive 与 auto --archive
        # 双通道统一生效），保证下一轮 /specpowers-auto 必然判定为 fresh，不被残留基线误判为续跑
        auto_base_removed = _cleanup_auto_base(root)

        print(f"Archive 完成。Feature '{feature}' 已归档为 '{archived_as}'。")
        if specs_updated:
            print(f"  - 主规格合并：✓ delta 已合并到 openspec/specs/<capability>/spec.md")
        else:
            print(f"  - 主规格合并：（无 delta 需合并）")
        print(f"  - change 快照：openspec/changes/archive/{archived_as}/")
        if auto_base_removed:
            print(f"  - auto 基线：.specpowers/auto_base.json 已清理（归档即新需求）")
        print(f"准备下一轮开发：/specpowers.explore | .propose | .fast")
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
    # reset 强制清锁：若此刻有并发实例在运行，其锁已被清除，需提示避免双写
    print("Note: reset force-clears the lock; avoid running it while another specpowers instance is active.")
    return 0


def _cleanup_auto_base(root: Path) -> bool:
    """归档成功后清理 auto_base.json（auto_base 缺失时 _load_auto_base 返回 None，无需重复清理）。

    Returns:
        是否实际删除了文件。

    作者：005819 | 协作：GLM-5.3
    """
    path = _auto_base_path(root)
    if path.exists():
        path.unlink()
        return True
    return False


def _handle_auto_new_round(root: Path, extra: dict) -> int:
    """auto new-round — auto 模式同需求新迭代轮（要求 auto_base.json 存在）。

    作者：005819 | 协作：GLM-5.3
    """
    return _enter_new_round(root, extra, require_auto_base=True, entry="auto")


def _handle_iterate(root: Path, extra: dict) -> int:
    """iterate — 人工模式同需求新迭代轮的轮次切换原语（不要求 auto_base.json；存在则同样落盘 rounds）。

    由 /specpowers-propose、/specpowers-explore 重入识别并经用户确认后调用（无独立入口命令）。
    与 auto 多轮迭代同一套语义：归档状态决定需求身份，feature 锁定不变，
    stage 受控置回 propose。不占用 fallback_count（人工 apply→propose 回退限额独立）。

    作者：005819 | 协作：GLM-5.3
    """
    return _enter_new_round(root, extra, require_auto_base=False, entry="manual")


def _enter_new_round(root: Path, extra: dict, require_auto_base: bool, entry: str) -> int:
    """同需求新迭代轮的受控轮次切换（auto new-round / iterate 共用实现）。

    受控跃迁：不走 VALID_TRANSITIONS 常规校验，本处理器自身即受控重置入口。
    前置：活跃 feature 未归档（auto 入口额外要求 auto_base.json 存在）；
    动作：stage → propose、feature 锁定不变、iteration_count += 1、execution_mode 清空
    （新轮执行方式在 apply 阶段重新确认，不继承上一轮）；
    落盘：auto_base.json 存在时追加本轮 rounds 记录（旧格式按 round 1 兼容迁移）并刷新文档指针。

    作者：005819 | 协作：GLM-5.3
    """
    state = load_state(root)
    feature = (state.get("feature") or "").strip()

    base = _load_auto_base(root)
    if require_auto_base and base is None:
        raise StateError(
            "auto new-round 需要 .specpowers/auto_base.json（auto 模式需求基线）。"
            "该文件不存在说明本次不是 auto 模式需求，请走全新 /specpowers-auto。"
        )
    if not feature:
        raise StateError(
            "当前 state 无活跃 feature，无法开启迭代轮。"
            "若要开始新需求：无人值守用 /specpowers-auto，人工模式用 /specpowers-explore 或 /specpowers-propose。"
        )
    from specpowers_cli.bridge.modules.archive_auditor import is_feature_archived
    if is_feature_archived(root, feature):
        raise StateError(
            f"feature '{feature}' 已归档，归档即新需求，"
            "请直接开启新需求（无人值守 /specpowers-auto，人工 /specpowers-explore）。"
        )

    design_doc = (extra.get("design_doc") or "").strip()
    instruction = (extra.get("instruction") or "").strip()

    # 旧格式兼容：无 rounds 字段 → 首轮记录按 round 1 迁移，
    # 并把轮次基线校正为 1（迁移记录代表历史已跑过一轮），保证新轮号不与迁移记录冲突
    if base is not None and not isinstance(base.get("rounds"), list):
        if state.get("iteration_count", 0) < 1:
            state["iteration_count"] = 1

    # 受控跃迁：stage 置回 propose（propose 起全量/轻量重跑），feature 身份锁定不变
    new_round = state.get("iteration_count", 0) + 1
    state["iteration_count"] = new_round
    state["stage"] = "propose"
    state["mode"] = "full"
    state["execution_mode"] = ""
    save_state(root, state)

    _append_round_record(root, base, feature, new_round, design_doc, instruction)

    label = "auto 模式" if entry == "auto" else "人工模式"
    print(f"迭代轮已开启（{label}）：Round {new_round}，feature '{feature}' 锁定不变，stage → propose")
    if entry == "auto":
        print("Agent 应按 prompts/auto.md 迭代轮编排继续：深度判定（full/light）→ propose → apply → specpowers-review")
    else:
        print("迭代轮已开启（人工模式重入）：按 prompts/propose.md 迭代轮小节增量修订三件套"
              "（方案变更时先按 explore.md 迭代轮小节更新设计文档与 proposal）；"
              "完成后 /specpowers-apply → 随时可 /specpowers-archive 收口")
    return 0


def _append_round_record(root: Path, base: dict | None, feature: str,
                         new_round: int, design_doc: str, instruction: str) -> None:
    """auto_base.json 存在时追加本轮 rounds 记录并刷新文档指针（含旧格式迁移）。

    base 为 None（人工模式无 auto 基线）时跳过落盘，仅 state.iteration_count 已承载轮次。

    作者：005819 | 协作：GLM-5.3
    """
    if base is None:
        return
    rounds = base.get("rounds")
    if not isinstance(rounds, list):
        rounds = _migrate_legacy_auto_base(base)
    if design_doc:
        digest = _design_doc_hash(design_doc)
        if digest:
            base["design_doc"] = design_doc
            base["design_doc_hash"] = digest
    if design_doc and instruction:
        input_type = "doc+instruction"
    elif design_doc:
        input_type = "doc"
    elif instruction:
        input_type = "instruction"
    else:
        input_type = "resume"
    entry_input: dict = {"type": input_type}
    if design_doc:
        entry_input["doc"] = design_doc
    if instruction:
        entry_input["instruction"] = instruction
    rounds.append({
        "round": new_round,
        "input": entry_input,
        "started_at": _utc_now_iso(),
    })
    base["feature"] = base.get("feature") or feature
    base["rounds"] = rounds
    _write_auto_base(root, base)


def _handle_auto_clarify(root: Path, extra: dict) -> int:
    """auto clarify — 需求澄清结论登记（写/刷新 auto_base.json 的 clarification 字段）。

    需求澄清步骤（auto 契约第 1 步）的收尾登记原语：契约层完成五维检查后调用，
    把推进深度上限（ceiling）落盘为断点续跑凭据——resume 凭此不重做澄清，
    ceiling=explore 时 auto-status 输出 pending_input 阻止盲目续跑。
    要求 auto_base.json 已存在（第 0 步基点记录已完成），防「声称澄清但无基线」；
    确定性层只兜「结论已登记、结构可读」的形式底线，五维检查实质质量由契约层保证。

    作者：005819 | 协作：GLM-5.3
    """
    ceiling = (extra.get("ceiling") or "").strip()
    # 旧值兼容：v1.x 登记 brainstorm（停靠在原 brainstorm 阶段）读入归一为 explore
    if ceiling == "brainstorm":
        ceiling = "explore"
    if ceiling not in ("full", "explore"):
        raise FatalError(
            f"clarification ceiling 非法：'{ceiling}'（仅允许 full | explore）。"
            "用法：facade auto clarify --ceiling <full|explore> [--report <澄清报告路径>]"
        )
    base = _load_auto_base(root)
    if base is None:
        raise StateError(
            "auto clarify 需要 .specpowers/auto_base.json（第 0 步基点记录的产物）。"
            "该文件不存在说明澄清先于基点记录执行，请按 prompts/auto.md 顺序先跑第 0 步。"
        )
    base["clarification"] = {
        "ceiling": ceiling,
        "report_path": (extra.get("report") or "").strip(),
        "checked_at": _utc_now_iso(),
    }
    _write_auto_base(root, base)
    print(f"澄清结论已登记：ceiling={ceiling}")
    if ceiling == "explore":
        print("推进上限为 explore：跑完 init → explore 产出未收敛草案后停靠，"
              "等待用户带方案结论（--instruction）或补充文档重入")
    return 0


def _handle_record_design_doc(root: Path, extra: dict) -> int:
    """record-design-doc — 登记探索设计文档路径到 state.json（propose 前置校验凭据）。

    explore 阶段认知层落盘设计文档（docs/specpowers/design/）后调用，
    把路径写入 state.design_doc。propose 从 explore 进入时确定性层校验非空且文件存在，
    形成防架空链：explore 必须真实探索 → propose 必须承接设计文档。
    只登记不校验内容质量（认知层职责），但校验文件存在（防登记空指针）。

    作者：005819 | 协作：GLM-5.3
    """
    design_doc = (extra.get("design_doc") or "").strip()
    if not design_doc:
        raise FatalError(
            "record-design-doc 需要设计文档路径参数。"
            "用法：facade record-design-doc <设计文档路径> --root ."
        )
    path = Path(design_doc)
    if not path.is_file():
        raise FatalError(
            f"设计文档 '{design_doc}' 不存在，拒绝登记。"
            "请先由 specpowers-explore 技能落盘设计文档后再登记"
        )

    state = load_state(root)
    state["design_doc"] = design_doc
    save_state(root, state)
    print(f"探索设计文档已登记：{design_doc}")
    print("propose 阶段将以此为探索凭据（缺失会被前置校验拦回 explore）")
    return 0


# ---- Route table ----

STAGE_HANDLERS = {
    "init": _handle_init,
    "explore": _handle_explore,
    "propose": _handle_propose,
    "fast": _handle_fast,
    "apply": _handle_apply,
    "archive": _handle_archive,
    "baseline": _handle_baseline,
    "reset": _handle_reset,
    "auto-new-round": _handle_auto_new_round,
    "auto-clarify": _handle_auto_clarify,
    "iterate": _handle_iterate,
    "record-design-doc": _handle_record_design_doc,
}


def route(stage: str, mode: str, root: Path, extra: dict | None = None) -> int:
    """Route a stage command to its handler.

    This is the main entry point for all stage operations.
    Called by facade.py command handlers.

    Args:
        stage: Stage name (init, explore, propose, fast, apply, archive, baseline, reset,
               auto-new-round, auto-clarify, iterate, record-design-doc)
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

    # try/finally 覆盖 BaseException：Ctrl+C（KeyboardInterrupt/SystemExit）
    # 不属于 Exception，原 except Exception 捕获不到会导致锁残留
    try:
        _register_signal_handlers(root)

        return handler(root, extra)
    finally:
        if stage != "reset":
            release_lock(root)


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
