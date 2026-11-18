"""Dispatcher — 工件推导路由、锁管理、auto-read enforcement（v3.0.0）。

Routes each stage command through:
1) Migrate legacy state.json（首次命令，幂等）
2) Acquire lock
3) Validate entry by artifact shape（derive_stage 工件判定，v3.0 起 VALID_TRANSITIONS 退役）
4) Enforce required artifact reads
5) Execute stage logic
6) Release lock

v3.0.0 状态机推导化：state.json 退役，流水线状态唯一权威是 openspec/changes/
工件目录——阶段（derive_stage）、活跃清单（active_slugs）、前台（foreground_slug）、
迭代轮次（iteration_count_of）全部推导；需求级登记（design_doc/mode/execution_mode/
last_touched）落 change 目录 meta；fallback_count/last_archive_ref 落 runtime.json。
"""

import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from specpowers_cli.bridge.core.errors import (
    FatalError, StateError, ArtifactMissingError, ArchiveDuplicateError,
)
from specpowers_cli.bridge.core.fs_state import (
    atomic_write_json, load_runtime, save_runtime,
    cleanup_auto_base, auto_base_path,
)
from specpowers_cli.bridge.core.lock import acquire_lock, release_lock, force_unlock
from specpowers_cli.bridge.core.git_util import is_git_repo, has_commits, is_detached_head, git_ref_of
from specpowers_cli.bridge.modules.artifact_registry import required_for
from specpowers_cli.bridge.modules.state_derivation import (
    STAGE_APPLY, STAGE_EXPLORE, STAGE_FAST,
    change_dir_of, derive_stage, active_slugs, foreground_slug,
    iteration_count_of, read_meta, update_meta, design_doc_of,
)


def _resolve_target_feature(root: Path, extra: dict, kind: str) -> str:
    """解析命令的目标需求 slug（v3.0 活跃权威 = 目录推导）。

    优先级：--feature 显式指定 > 前台（meta last_touched 最大）。
    - kind="advance"（推进/破坏性命令：apply/archive/auto 系列/record-*）：
      多活跃且未指名 → StateError 列出活跃需求与阶段，要求带 --feature 重试
    - kind="read"（只读命令：auto-status）：缺省作用于前台，不拒绝

    Args:
        root: 项目根目录。
        extra: 命令参数（取 "feature" 键）。
        kind: "advance" | "read"。

    Returns:
        目标需求 slug（advance 类必有活跃需求）。

    Raises:
        StateError: 显式指定了不活跃的 slug；多活跃未指名；无活跃需求。

    作者：005819 | 协作：GLM-5.3
    """
    explicit = (extra.get("feature") or "").strip()
    if explicit:
        from specpowers_cli.bridge.modules.path_resolver import sanitize_feature_slug
        feature = sanitize_feature_slug(explicit)
        if feature not in active_slugs(root):
            active = _describe_active(root)
            raise StateError(
                f"'{feature}' 不是活跃需求。当前活跃：{active}。"
                f"请从活跃需求中选择，或先经 explore/fast 开工新需求。"
            )
        return feature

    fg = foreground_slug(root)
    if not fg:
        raise StateError(
            "当前无活跃需求，无法执行该命令。"
            "开始新需求：人工模式 /specpowers-explore 或 /specpowers-fast，"
            "无人值守 /specpowers-auto。"
        )
    if kind == "advance":
        others = [slug for slug in active_slugs(root) if slug != fg]
        if others:
            raise StateError(
                f"存在多个活跃需求，推进类命令必须显式 --feature 指定目标。"
                f"当前活跃：{_describe_active(root)}。"
                f"请带 --feature <slug> 重试（前台为 '{fg}'，仅作参考不作默认）。"
            )
    return fg


def _describe_active(root: Path) -> str:
    """活跃需求清单的紧凑描述（slug(stage[,Round N]) 逗号分隔，全推导拼装）。"""
    parts = []
    for slug in active_slugs(root):
        cdir = change_dir_of(root, slug)
        stage = derive_stage(cdir)
        desc = f"{slug}({stage}"
        rounds = iteration_count_of(cdir)
        if rounds >= 1:
            desc += f", Round {rounds}"
        desc += ")"
        parts.append(desc)
    return ", ".join(parts) if parts else "（无）"


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


# ---- auto 模式基线（auto_base 按需求分片，v3.0 不变） ----

def _auto_base_path(root: Path, feature: str) -> Path:
    """Return path to auto_base/<feature>.json（v2.8.0 起按需求隔离）。"""
    return auto_base_path(root, feature)


def _load_auto_base(root: Path, feature: str) -> dict | None:
    """读取需求的 auto_base；不存在返回 None，损坏抛 FatalError 引导人工处理。

    作者：005819 | 协作：GLM-5.3
    """
    path = _auto_base_path(root, feature)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise FatalError(
            f"auto_base（feature '{feature}'）解析失败: {e}。"
            f"请人工检查或删除 {path} 后重试 /specpowers-auto。"
        )


def _write_auto_base(root: Path, feature: str, data: dict) -> None:
    """原子写需求的 auto_base（复用 fs_state.atomic_write_json，与 meta 同一保障）。"""
    atomic_write_json(_auto_base_path(root, feature), data)


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
    """当前 UTC 时间的 ISO 格式字符串（rounds/last_touched 记录用）。"""
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


def auto_status(root: Path, design_doc: str = "", instruction: str = "", feature: str = "") -> dict:
    """auto 模式重入三分判定：fresh / resume / iterate（facade auto-status 子命令入口）。

    需求身份由工件目录唯一决定（active_slugs 扫描），与设计文档解耦：
    - fresh：目标不在活跃清单（已归档或从未开始）；发现残留 auto_base 则顺带清理
    - resume：活跃需求 + 无任何新输入（文档 hash 未变、无指令）→ 断点续跑
    - iterate：活跃需求 + 任一新输入（文档实质变更 / 口头指令）→ 同需求新迭代轮

    判定只读工件与 auto_base，不做状态跃迁；轮次切换必须走 auto new-round
    （v3.0 起仅落 auto_base.rounds 记录，轮次本身由工件推导）。
    响应携带 clarification 视图（上一轮澄清结论 + pending_input），供契约层
    做 resume 停靠保护与迭代轮增量澄清。

    Args:
        root: 项目根目录。
        design_doc: 本次重入携带的设计文档路径（空 = 未携带）。
        instruction: 本次重入携带的口头指令（空 = 未携带）。
        feature: 目标需求 slug（空 = 前台；多活跃时输出标明作用对象）。

    作者：005819 | 协作：GLM-5.3
    """
    # 目标需求解析（read 类：缺省前台，多活跃不拒绝；显式指定不活跃 → 报错防误判）
    feature = (feature or "").strip()
    if feature:
        if feature not in active_slugs(root):
            raise StateError(
                f"'{feature}' 不是活跃需求。当前活跃：{_describe_active(root)}。"
                f"auto-status 只对活跃需求做三分判定。"
            )
    else:
        feature = foreground_slug(root) or ""
    change_dir = change_dir_of(root, feature) if feature else None
    base = _load_auto_base(root, feature) if feature else None

    # fresh：目标不在活跃清单（已归档或从未开始）
    if not feature or not change_dir.is_dir():
        # 无活跃需求时的残留清理：auto_base/ 目录全部 + 旧版（v2.7.0 及以前）
        # 顶层 auto_base.json 孤儿（迁移仅在 feature 非空时搬走，无活跃时无人认领）
        removed = cleanup_auto_base(root, keep=[]) > 0
        legacy_base = root / ".specpowers" / "auto_base.json"
        if legacy_base.exists():
            legacy_base.unlink()
            removed = True
        return {
            "mode": "fresh",
            "feature": "",
            "round": 0,
            "iteration_count": 0,
            "stage": "ready",
            "scope_hint": "",
            "reason": "无活跃 feature，按全新需求执行（设计文档必填）",
            "design_doc_exists": None,
            "auto_base_removed": removed,
            "clarification": None,
        }

    round_now = iteration_count_of(change_dir)
    stage_now = derive_stage(change_dir)

    # 活跃需求（full 流水线中 / fast 待编码）：base 缺失 = 人工流程被 auto 接管
    if base is None:
        return {
            "mode": "iterate",
            "feature": feature,
            "round": round_now + 1,
            "iteration_count": round_now,
            "stage": stage_now,
            "scope_hint": "full",
            "reason": "存在未归档的活跃 feature 但缺 auto_base（人工流程接管），保守按全量迭代执行并补建基线",
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

    if not has_new_input:
        return {
            "mode": "resume",
            "feature": feature,
            "round": round_now,
            "iteration_count": round_now,
            "stage": stage_now,
            "scope_hint": "",
            "reason": "无新输入（文档未变且无指令），按断点续跑：读需求 stage + 产物存在性定位断点，已完成阶段不重做",
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
        "stage": stage_now,
        "scope_hint": scope_hint,
        "reason": reason,
        "design_doc_exists": design_doc_exists,
        "clarification": _clarification_view(base, has_new_input=True),
    }


def _check_initialized(root: Path, stage: str):
    """未初始化项目兜底：流水线阶段要求 constitution.md 与 baseline.json 存在。

    任一缺失 = 项目从未执行过 /specpowers-init。阶段薄入口技能（SKILL.md
    第 0 步）已主动检测并自动补初始化，此处是确定性层兜底——防模型跳过
    第 0 步时给出可执行指引。init/baseline/reset/auto 不查：init 自身创建
    产物，baseline/reset 为维护动作，auto 编排已内置 init 步骤。
    作者：005819 | 协作：GLM-5.3
    """
    if stage not in ("explore", "propose", "fast", "apply", "archive"):
        return
    missing = [
        name for name in ("constitution.md", "baseline.json")
        if not (root / ".specpowers" / name).exists()
    ]
    if missing:
        raise FatalError(
            "Project not initialized (missing: " + ", ".join(missing) + "). "
            "Run /specpowers-init first — 模型读到本错误时自动转执行 specpowers-init，"
            "完成后重试原命令。"
        )


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
    # apply 回退路径、迭代续作自环路径均不要求）。v3.0 起登记读 change 目录 meta。
    if stage == "propose" and mode == "full" and from_stage == STAGE_EXPLORE:
        _check_design_doc_registered(root, feature)

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
                    "Complete your coding before running /specpowers-apply"
                )


def _check_design_doc_registered(root: Path, feature: str) -> None:
    """校验目标需求的设计文档已登记（propose 从 explore 进入时的硬依赖）。

    防止探索被架空：explore 落盘设计文档后经 `facade record-design-doc` 把路径
    写入 change 目录 meta。agent 若跳过 specpowers-explore 探索直接收口，不会产生
    设计文档与 meta 登记，本校验将其拦在 propose 之外，强制回 explore 完成探索。
    v3.0 起登记读 meta（design_doc_of），state.design_doc 随 state 退役删除。

    Args:
        root: 项目根路径。
        feature: 目标需求 slug（按需求查 meta 登记）。

    Raises:
        ArtifactMissingError: 需求的 meta 无 design_doc，或登记的文件不存在。

    作者：005819 | 协作：GLM-5.3
    """
    design_doc = design_doc_of(root, feature) or ""

    if not design_doc:
        # v3.0 语义收窄：目录形态「仅 meta」无法区分「explore 未收口」与
        # 「ready 直入 propose 后中断」两个来源——为空时放行（跳过探索路径
        # 的中断重入不再被误拦），防探索架空由 explore 契约 HARD-GATE 与
        # record-design-doc 登记纪律承担
        return

    # 相对路径按 --root 解析（meta 自包含登记是相对项目根的 posix 路径，
    # 进程 CWD 未必等于项目根——facade --root 支持任意 root，跨目录调用合法）
    doc_path = Path(design_doc)
    if not doc_path.is_absolute():
        doc_path = root / design_doc
    if not doc_path.is_file():
        raise ArtifactMissingError(
            f"登记的设计文档 '{design_doc}' 不存在。"
            "请确认文件未被移动/删除，或回 /specpowers-explore 重新探索并登记"
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
                "设计文档的数据流结论，需回 /specpowers-propose 补全 proposal 后再继续）"
            )
        raise ArtifactMissingError(
            f"proposal.md 缺少「## 数据流契约」小节。"
            f"这是 apply 阶段的硬依赖——说明 explore 探索结论未被 propose 承接"
            f"（探索可能被跳过或 proposal 凭空生成）。"
            f"{fallback_hint}"
            f"请回到 /specpowers-propose 基于 explore 设计文档重新生成 proposal.md"
            f"并补全「## 数据流契约」小节"
            f"（涉及跨链路字段则按字段卡片逐个详述，纯本地特性则声明「本特性无跨链路字段」）。"
        )


def _check_init_conflict(root: Path):
    """Check if init command would discard in-progress features."""
    active = active_slugs(root)
    if active:
        # Interactive confirmation needed — in CI mode, auto-confirm
        if is_ci_mode():
            print(f"[CI] Auto-confirming init re-generation (would discard active "
                  f"features: {', '.join(active)})", file=sys.stderr)
        else:
            raise StateError(
                f"Active features in progress: {_describe_active(root)}. "
                f"Use --force to discard all of them and rebuild constitution, "
                f"or /specpowers-maintain reset --feature <slug> to abandon a specific one."
            )


def is_ci_mode() -> bool:
    """Check if running in CI mode."""
    return os.environ.get("SPECPOWERS_CI", "").strip() == "1"


def is_verbose() -> bool:
    """Check if verbose logging is enabled."""
    import os
    return os.environ.get("SPECPOWERS_VERBOSE", "").strip() == "1"


def _log_verbose(msg: str):
    """Log verbose message to stderr."""
    if is_verbose():
        print(f"[specpowers] {msg}", file=sys.stderr)


def _discard_feature(root: Path, slug: str) -> None:
    """删除单个需求的全部工件（reset/init --force 的放弃原语，v3.0 语义重定义）。

    删 change 目录 + auto_base 分片——放弃即删工件（需留存走 archive），
    僵尸目录类漂移根源消灭；runtime.json 的 fallback_count/last_archive_ref
    不受影响（项目级字段，跨需求保留）。

    作者：005819 | 协作：GLM-5.3
    """
    cdir = change_dir_of(root, slug)
    if cdir.is_dir():
        shutil.rmtree(cdir)
    base = auto_base_path(root, slug)
    if base.exists():
        base.unlink()


# ---- Stage handlers ----

def _handle_init(root: Path, extra: dict) -> int:
    """Handle init stage."""
    force = extra.get("force", False)

    # 幂等放行：已归档的空转状态（无活跃需求）重复 init 不报错、不重建。
    # auto.md 第 2 步承诺 /specpowers-init 幂等执行，而 auto 判定 fresh
    # 的常见起点恰是无活跃需求——无幂等语义时无人值守流程必然撞
    # _check_init_conflict 的 StateError，或被迫 --force 重建团队已评审的 constitution
    if (
        not force
        and not active_slugs(root)
        and (root / ".specpowers" / "baseline.json").exists()
    ):
        print("Init skipped (idempotent): no active feature in progress and baseline already exists.")
        return 0

    if not force and active_slugs(root):
        _check_init_conflict(root)

    _log_verbose("Running baseline scanner...")
    from specpowers_cli.bridge.modules.baseline_scanner import scan

    baseline_path = root / ".specpowers" / "baseline.json"
    if baseline_path.exists() and not force:
        _log_verbose(".specpowers/constitution.md and baseline.json exist, skipping.")
    else:
        if force and baseline_path.exists():
            baseline_path.unlink()
        scan(root)

    # 走到这里：无活跃需求，或 --force / CI 自动确认（放弃全部活跃需求）。
    # v3.0 放弃语义 = 删除活跃 change 目录 + auto_base 分片（工件权威下的
    # 「无活跃」只能靠删目录达成）；runtime.json 项目级字段保留
    for slug in active_slugs(root):
        _discard_feature(root, slug)

    print("Constitution + baseline ready. Stage: ready")
    return 0


def _resolve_entry_feature(root: Path, extra: dict, req: str) -> tuple[str, bool]:
    """开新入口（explore/fast）的目标需求解析 + 续作命中规则。

    v3.0 多活跃规则（slug 即身份，权威 = 目录）：
    - --feature 显式指定优先（auto 多轮迭代用首轮 slug 锁定 change 目录，
      防止 requirement 措辞变化导致 slug 漂移）
    - normalize(requirement) 后命中活跃清单 = 该需求的续作请求
    - 未命中 = 新需求

    Returns:
        (feature slug, 是否命中活跃续作)。

    作者：005819 | 协作：GLM-5.3
    """
    explicit_feature = (extra.get("feature") or "").strip()
    if explicit_feature:
        feature = _finalize_feature_slug(explicit_feature)
    else:
        feature = normalize_feature(req)
    return feature, feature in active_slugs(root)


def _handle_explore(root: Path, extra: dict) -> int:
    """Handle explore stage（v3.0：无 state 写点，阶段由工件推导）。

    explore 进行中无 change 目录（设计文档收口时才经 record-design-doc 建立），
    该需求暂不在活跃清单——确定性动作仅入口校验 + 指引打印。
    """
    req = extra.get("requirement", "")

    # slug 命中活跃清单 = 续作请求：explore 仅对新需求执行，重入非法——
    # 错误信息给多需求语境的可执行指引
    feature, is_resume = _resolve_entry_feature(root, extra, req)
    if is_resume:
        raise StateError(
            f"feature '{feature}' 已在活跃清单中（当前 {_describe_active(root)}）。"
            "explore 仅对新需求执行；该需求续作请走 /specpowers-propose（propose 重入"
            "即迭代轮，目录推导自动识别）；若确为新需求，请调整需求描述"
            f"或显式 --feature <其他slug>。"
        )

    _check_prerequisites(root)
    _run_pre_stage_checks(root, "explore", "full", feature)

    print(f"Explore started for feature: {feature}")
    print("Agent should now: follow prompts/explore.md and complete the inline explore-engine "
          "procedure to explore the requirement, "
          "write the design doc under docs/specpowers/design/ "
          "(incl. data-flow conclusions), register it via "
          f"`facade record-design-doc <path> --feature {feature}`, then continue to /specpowers-propose")
    return 0


def _handle_propose(root: Path, extra: dict) -> int:
    """Handle propose stage — 一站式生成 OpenSpec change 三件套（v3.0 工件判定入口）。

    合并原 specify + plan：从 explore 设计文档（或跳过探索的清晰需求）出发，
    依次落盘 proposal.md → spec.md → tasks.md（认知层按 prompts/propose.md 执行，
    确定性层只做工件判定与前置校验 + touch meta）。
    """
    req = extra.get("requirement", "")

    # Feature 解析：--feature 显式 > slug 命中活跃（续作）> normalize 当前
    # requirement 兜底（新需求，from ready）
    explicit_feature = (extra.get("feature") or "").strip()
    if explicit_feature:
        feature = _finalize_feature_slug(explicit_feature)
    else:
        normalized = normalize_feature(req)
        if normalized in active_slugs(root):
            feature = normalized
        else:
            fg = foreground_slug(root) or ""
            feature = fg if fg else normalized
    in_active = feature in active_slugs(root)
    change_dir = change_dir_of(root, feature)
    from_stage = derive_stage(change_dir) if in_active else "ready"

    # 工件判定（取代 _validate_transition）：propose 可入自
    # explore（仅 meta）/ propose（续作自环）/ apply（回退）/ fast（转 full）/ ready（新需求）
    if in_active and from_stage == STAGE_FAST:
        _apply_fallback_and_switch_to_full(root, feature)
    elif in_active and from_stage == STAGE_APPLY:
        _apply_fallback_and_switch_to_full(root, feature)
    # explore / propose 自环 / 新需求（ready）：直接放行

    _check_prerequisites(root)
    _run_pre_stage_checks(root, "propose", "full", feature, from_stage=from_stage)

    # touch meta（操作即前台；新需求借此建目录 + meta，propose 进行中的
    # 目录形态 = 仅 meta → derive_stage=explore，重入校验自洽）
    now = _utc_now_iso()
    updates = {"last_touched": now}
    if not in_active:
        updates["mode"] = "full"
        updates["created_at"] = now
    update_meta(root, feature, updates)

    print(f"Propose started for feature: {feature}")
    return 0


def _apply_fallback_and_switch_to_full(root: Path, feature: str) -> None:
    """apply/fast → propose 回退原语：fallback 额度校验 + 计次 + mode 归 full。

    fast 态重入 propose = fast→full 转换；apply 态重入 propose = 回退修订。
    两者同走生命周期唯一 1 次额度（runtime.json 计次，归档/reset 均不清）。
    作者：005819 | 协作：GLM-5.3
    """
    runtime = load_runtime(root)
    if runtime["fallback_count"] >= 1:
        raise StateError(
            "回退次数已达上限：整个项目生命周期最多 1 次 apply/fast→propose 回退"
            "（归档/reset 均不清除计次，新需求不恢复额度）。"
            "如确需再次回退，请手动编辑 .specpowers/runtime.json 将 fallback_count 置 0。"
        )
    runtime["fallback_count"] += 1
    save_runtime(root, runtime)
    # fast→full / apply→propose：mode 归 full（新轮执行方式在 apply 重新确认）
    update_meta(root, feature, {"mode": "full"})


def _handle_fast(root: Path, extra: dict) -> int:
    """Handle fast mode entry（v3.0：建 change 目录 + meta(mode=fast) + checklist 骨架）。

    fast 合法入口：新需求（无目录），或 fast 态重入（meta.mode=fast）。
    目录已存在且非 fast 态 → 拒绝（该需求已在 full 流水线推进中）。
    """
    req = extra.get("requirement", "")

    feature, is_resume = _resolve_entry_feature(root, extra, req)
    if is_resume:
        change_dir = change_dir_of(root, feature)
        if derive_stage(change_dir) != STAGE_FAST:
            raise StateError(
                f"Cannot start fast mode for feature '{feature}' "
                f"(current stage: {derive_stage(change_dir)}). "
                f"Fast mode is only valid for new features or fast-mode re-entry; "
                f"该需求已在推进中，续作请走对应阶段命令。"
            )

    _check_prerequisites(root)

    # fast 自包含（v3.0）：建 change 目录 + meta(mode=fast) + checklist 骨架
    # （验收清单 3-5 条由认知层填充，确定性层落结构骨架保证 apply 门禁可校验）
    update_meta(root, feature, {
        "mode": "fast",
        "created_at": _utc_now_iso(),
        "last_touched": _utc_now_iso(),
    })
    checklist = change_dir_of(root, feature) / "checklist.md"
    if not checklist.exists():
        checklist.parent.mkdir(parents=True, exist_ok=True)
        checklist.write_text(
            "# 验收清单（fast 模式）\n\n"
            "<!-- 3-5 条可验证的验收标准，由 fast 契约在确认交互后填充 -->\n\n"
            "- [ ] （待填充）\n",
            encoding="utf-8",
        )

    print(f"Fast mode activated for feature: {feature}")
    print("Agent will now: run small-judgment → confirmation → fill checklist.md → user codes → /specpowers-apply")
    return 0


def _handle_apply(root: Path, extra: dict) -> int:
    """Handle apply stage（v3.0 工件判定入口）。"""
    # 推进类命令：显式 --feature > 前台；多活跃未指名 → 拒绝并列出活跃需求
    feature = _resolve_target_feature(root, extra, kind="advance")
    change_dir = change_dir_of(root, feature)
    stage = derive_stage(change_dir)
    meta = read_meta(change_dir) or {}
    mode = str(meta.get("mode") or "full")

    # 工件判定（取代 _validate_transition）：apply 可入自 propose（三件套齐，
    # required_for 另行校验）/ apply（续跑）/ fast；explore（三件套未齐）拒绝
    if stage == STAGE_EXPLORE:
        raise StateError(
            f"Cannot enter apply from '{stage}' for feature '{feature}'（三件套未齐）。"
            f"请先走 /specpowers-propose 生成三件套（fast 需求请确认 meta.mode=fast）。"
        )

    _check_prerequisites(root)
    _run_pre_stage_checks(root, "apply", mode, feature)

    # touch meta（操作即前台）
    update_meta(root, feature, {"last_touched": _utc_now_iso()})

    if mode == "fast":
        print(f"Apply stage (fast mode) for feature '{feature}'. Agent will run: code extraction → structure gate → execute → verify.")
    else:
        print(f"Apply stage (full mode) for feature '{feature}'. Agent will run: structure gate → ability pool → execute → verify.")
    return 0


def _handle_archive(root: Path, extra: dict) -> int:
    """Handle archive stage — 确定性执行归档（委托 OpenSpec，v3.0 工件判定入口）。

    full 和 fast 统一：调 openspec archive 合并主规格 + change 移到 archive 快照
    （目录移走后 active_slugs 自然不再包含该需求——归档的「需求终结」由工件
    承载，无需任何状态删除）。v2.8.0 起多活跃：--feature 指定归档目标。
    """
    # 推进类命令：显式 --feature > 前台；多活跃未指名 → 拒绝并列出活跃需求
    feature = _resolve_target_feature(root, extra, kind="advance")
    change_dir = change_dir_of(root, feature)
    stage = derive_stage(change_dir)
    meta = read_meta(change_dir) or {}
    mode = str(meta.get("mode") or "full")

    # 工件判定（取代 _validate_transition）：archive 可入自 apply（tasks 有执行
    # 进度）/ fast（验收清单路径）；propose（无进度）与 explore（三件套未齐）拒绝
    if stage not in (STAGE_APPLY, STAGE_FAST):
        raise StateError(
            f"Cannot transition from '{stage}' to 'archive'. "
            f"Valid from stages: apply, fast"
        )

    # Duplicate check: has this feature already been archived?
    from specpowers_cli.bridge.modules.archive_auditor import is_feature_archived
    if feature and is_feature_archived(root, feature):
        raise ArchiveDuplicateError(
            f"Feature '{feature}' already has an archive commit. "
            f"Run: git pull && /specpowers-maintain reset --feature {feature} to sync."
        )

    _check_prerequisites(root)
    _run_pre_stage_checks(root, "archive", mode, feature)

    runtime = load_runtime(root)
    force_merge = extra.get("force_merge_check", False)

    # Merge check（仅检测并提示，归档本身不依赖它）
    from specpowers_cli.bridge.modules.archive_auditor import merge_check_detect
    should_merge_check = force_merge or merge_check_detect(
        root, runtime.get("last_archive_ref", "")
    )
    if should_merge_check and mode != "fast":
        print("⚠ Merge check triggered — multi-branch or forced. Agent will run post-merge verification.")

    # 场景覆盖核查（确定性，提示不阻断——archive 只转人工不打回）：
    # delta spec 每个 Scenario 至少被一个任务引用（规范即验收标尺，OpenSpec 第三原则）
    from specpowers_cli.bridge.modules.archive_auditor import scenario_coverage
    coverage = scenario_coverage(root, feature)
    if coverage["status"] == "partial":
        # 未覆盖列表封顶（v3.1.0）：∝ 未覆盖场景数无理论上限，超 20 条截断附计数
        uncovered = coverage["uncovered"]
        print(
            f"⚠ 场景覆盖核查：{coverage['covered']}/{coverage['total']} 个 spec 场景被任务引用。"
            "未覆盖场景（建议回 /specpowers-propose 补任务，或确认场景已作废）："
        )
        for name in uncovered[:20]:
            print(f"  - {name}")
        if len(uncovered) > 20:
            print(f"  - …共 {len(uncovered)} 个未覆盖场景，仅列前 20 个（可回 /specpowers-propose 补齐任务后复查）")
    elif coverage["status"] == "no_tasks":
        print("⚠ tasks.md 缺失，场景覆盖核查跳过（正常产物不应出现，请检查 change 目录）。")

    # full + fast 统一：调 openspec archive 归档（产物已是 OpenSpec 格式，无转换）
    from specpowers_cli.bridge.modules.archive_auditor import prepare_openspec_archive
    archive_result = prepare_openspec_archive(root, feature, dict(runtime))
    archived_as = archive_result.get("archivedAs", feature)
    specs_updated = archive_result.get("specsUpdated", False)

    # 归档成功：刷新 runtime 的 last_archive_ref（merge check 基准，项目级）
    runtime["last_archive_ref"] = git_ref_of(root)
    save_runtime(root, runtime)
    # auto_base/<feature>.json 清理（归档即该需求生命周期终结，保证下一次
    # auto 判定必然 fresh）；change 目录已由 openspec archive 移入 archive/，
    # 活跃清单即时更新，无需任何状态删除
    base = auto_base_path(root, feature)
    if base.exists():
        base.unlink()

    print(f"Archive 完成。Feature '{feature}' 已归档为 '{archived_as}'。")
    if specs_updated:
        print(f"  - 主规格合并：✓ delta 已合并到 openspec/specs/<capability>/spec.md")
    else:
        print(f"  - 主规格合并：（无 delta 需合并）")
    print(f"  - change 快照：openspec/changes/archive/{archived_as}/")

    # 多活跃：归档一个不影响其余；前台自动切到剩余 last_touched 最大者
    remaining = active_slugs(root)
    if remaining:
        fg = foreground_slug(root)
        print(f"剩余活跃需求：{_describe_active(root)}（前台：{fg}）。")
        print(f"续推指定需求：阶段命令带 --feature {fg}（或其他 slug）。")
    else:
        print(f"准备下一轮开发：/specpowers-explore | /specpowers-propose | /specpowers-fast")
    return 0


def _handle_baseline(root: Path, extra: dict) -> int:
    """Handle baseline refresh."""
    _check_prerequisites(root)
    from specpowers_cli.bridge.modules.baseline_scanner import scan
    scan(root)
    print("Baseline refreshed. Please review and commit .specpowers/baseline.json.")
    return 0


def _handle_reset(root: Path, extra: dict) -> int:
    """Handle reset — 按需求粒度放弃流水线（v3.0 语义重定义：删除工件）。

    - reset --feature <slug>：删除 openspec/changes/<slug>/ + auto_base 分片
      （放弃即删工件，需留存走 archive）；破坏性确认：非 CI 模式必须 --force
    - 无 --feature 且活跃 >1：StateError 要求显式指名（防误删全部）
    - 无 --feature 且 0/1 个活跃：全删（fallback_count/last_archive_ref 保留——
      项目级字段跨需求生命周期）

    reset 跳过 route 的锁获取（见 route），但需主动清理可能残留的锁文件。
    作者：005819 | 协作：GLM-5.2（v2.8.0 多需求化：GLM-5.3；v3.0 删目录语义：GLM-5.3）
    """
    # 清理可能残留的锁文件（reset 跳过 route 的 acquire_lock，直接 force_unlock）
    force_unlock(root)

    feature_opt = (extra.get("feature") or "").strip()
    if feature_opt:
        from specpowers_cli.bridge.modules.path_resolver import sanitize_feature_slug
        feature = sanitize_feature_slug(feature_opt)
        if not change_dir_of(root, feature).is_dir():
            raise StateError(
                f"'{feature}' 不是活跃需求，无法 reset。"
                f"当前活跃：{_describe_active(root)}。"
            )
        # 破坏性确认（v3.0 删目录语义）：非 CI 必须显式 --force
        if not extra.get("force") and not is_ci_mode():
            raise StateError(
                f"reset --feature 将删除 '{feature}' 的全部工件"
                f"（openspec/changes/{feature}/ 含三件套与设计演进链 + auto_base 分片），"
                f"不可恢复（需留存请走 /specpowers-archive）。"
                f"确认请加 --force 重试。"
            )
        _discard_feature(root, feature)
        remaining = active_slugs(root)
        print(f"Feature '{feature}' 已放弃（change 目录与 auto 基线已删除）。")
        if remaining:
            print(f"剩余活跃需求：{_describe_active(root)}（前台：{foreground_slug(root)}）。")
        else:
            print("State reset to ready. (fallback_count preserved)")
        return 0

    active = active_slugs(root)
    if len(active) > 1:
        raise StateError(
            f"存在多个活跃需求，reset 必须显式指名目标（防误删全部）。"
            f"当前活跃：{_describe_active(root)}。"
            f"用法：facade reset --feature <slug> --force --root .；"
            f"确认放弃全部则逐个 reset。"
        )
    if active and not extra.get("force") and not is_ci_mode():
        raise StateError(
            f"reset 将删除活跃需求 '{active[0]}' 的全部工件"
            f"（openspec/changes/{active[0]}/ + auto_base 分片），"
            f"不可恢复（需留存请走 /specpowers-archive）。确认请加 --force 重试。"
        )
    for slug in active:
        _discard_feature(root, slug)

    print("State reset to ready. (fallback_count/last_archive_ref preserved)")
    # reset 强制清锁：若此刻有并发实例在运行，其锁已被清除，需提示避免双写
    print("Note: reset force-clears the lock; avoid running it while another specpowers instance is active.")
    return 0


def _handle_auto_new_round(root: Path, extra: dict) -> int:
    """auto new-round — auto 模式同需求新迭代轮（要求 auto_base.json 存在）。

    v3.0 起纯 auto_base.rounds 记录（无 state 写点）：轮次由工件推导
    （design-round-N / tasks Round 小节），本命令落本轮记录供 auto 断点
    与三分判定消费。

    作者：005819 | 协作：GLM-5.3
    """
    # 推进类命令：显式 --feature > 前台；多活跃未指名 → 拒绝并列出活跃需求
    feature = _resolve_target_feature(root, extra, kind="advance")
    change_dir = change_dir_of(root, feature)

    base = _load_auto_base(root, feature)
    if base is None:
        raise StateError(
            f"auto new-round 需要 feature '{feature}' 的 auto_base"
            f"（.specpowers/auto_base/{feature}.json，auto 模式需求基线）。"
            "该文件不存在说明本次不是 auto 模式需求，请走全新 /specpowers-auto。"
        )
    from specpowers_cli.bridge.modules.archive_auditor import is_feature_archived
    if is_feature_archived(root, feature):
        raise StateError(
            f"feature '{feature}' 已归档，归档即新需求，"
            "请直接开启新需求（无人值守 /specpowers-auto，人工 /specpowers-explore）。"
        )

    design_doc = (extra.get("design_doc") or "").strip()
    instruction = (extra.get("instruction") or "").strip()
    new_round = iteration_count_of(change_dir) + 1

    _append_round_record(root, feature, base, new_round, design_doc, instruction)

    print(f"迭代轮已开启（auto 模式）：feature '{feature}' Round {new_round}，锁定不变"
          f"（轮次由工件推导，落 design-round-{new_round}.md 或 tasks Round 小节即生效）")
    print("Agent 应按 prompts/auto.md 迭代轮编排继续：深度判定（full/light）→ propose → apply → specpowers-review")
    return 0


def _append_round_record(root: Path, feature: str, base: dict | None,
                         new_round: int, design_doc: str, instruction: str) -> None:
    """需求的 auto_base rounds 追加本轮记录并刷新文档指针（含旧格式迁移）。

    base 为 None（人工模式无 auto 基线）时跳过落盘——人工迭代轮的轮次
    由工件推导（design-round-N/tasks Round 小节），无需记录文件。

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
    _write_auto_base(root, feature, base)


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
            "用法：facade auto clarify --ceiling <full|explore> [--report <澄清报告路径>] [--feature <slug>]"
        )
    # 推进类命令：显式 --feature > 前台；多活跃未指名 → 拒绝并列出活跃需求
    feature = _resolve_target_feature(root, extra, kind="advance")
    base = _load_auto_base(root, feature)
    if base is None:
        raise StateError(
            f"auto clarify 需要 feature '{feature}' 的 auto_base"
            f"（.specpowers/auto_base/{feature}.json，第 0 步基点记录的产物）。"
            "该文件不存在说明澄清先于基点记录执行，请按 prompts/auto.md 顺序先跑第 0 步。"
        )
    base["clarification"] = {
        "ceiling": ceiling,
        "report_path": (extra.get("report") or "").strip(),
        "checked_at": _utc_now_iso(),
    }
    _write_auto_base(root, feature, base)
    print(f"澄清结论已登记（feature '{feature}'）：ceiling={ceiling}")
    if ceiling == "explore":
        print("推进上限为 explore：跑完 init → explore 产出未收敛草案后停靠，"
              "等待用户带方案结论（--instruction）或补充文档重入")
    return 0


def _handle_record_design_doc(root: Path, extra: dict) -> int:
    """record-design-doc — 登记探索设计文档到 change 目录 meta（propose 前置校验凭据）。

    explore 阶段认知层落盘设计文档（docs/specpowers/design/）后调用，路径写入
    change 目录 .specpowers-meta.json（v3.0 唯一登记处，state.design_doc 已退役）。
    propose 从 explore 进入时确定性层校验 meta 登记非空且文件存在，
    形成防架空链：explore 必须真实探索 → propose 必须承接设计文档。
    只登记不校验内容质量（认知层职责），但校验文件存在（防登记空指针）；
    v2.5.1 起附带 advisory 段头检查——缺「## 方案对比」/「## 详细设计」段头
    仅输出警告不阻断（项目自有设计文档约定可能不含这些章节，阻断会误伤）。

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
            "请先经 explore 契约（探索引擎细则）落盘设计文档后再登记"
        )

    # advisory 章节检查：模板必备段头缺失时警告，给"空壳/占位文档"留下可追溯信号
    required_sections = (
        ("方案对比", r"^##\s*方案对比"),
        ("详细设计", r"^##\s*详细设计"),
    )
    try:
        content = path.read_text(encoding="utf-8")
        missing = [name for name, pattern in required_sections if not re.search(pattern, content, re.MULTILINE)]
        if missing:
            missing_label = "、".join(f"「## {name}」" for name in missing)
            print(f"警告（advisory，登记已生效）：设计文档疑似缺章节 {missing_label}——"
                  "请按 prompts/explore.md 设计文档模板补全后再提交 propose")
    except OSError as e:
        print(f"警告（advisory）：设计文档内容读取失败，跳过章节检查：{e}")

    # 目标需求解析：显式 --feature 直接采用（登记本身即建目录动作，登记前
    # 目录尚不存在、无从校验活跃）；未指名才走 advance 规则（多活跃防错路由）
    explicit_feature = (extra.get("feature") or "").strip()
    if explicit_feature:
        feature = _finalize_feature_slug(explicit_feature)
    else:
        feature = _resolve_target_feature(root, extra, kind="advance")

    # v3.0 唯一登记处：change 目录 meta（建目录 + design_doc/created_at/last_touched）
    update_meta(root, feature, {
        "design_doc": _as_relative(root, design_doc),
        "last_touched": _utc_now_iso(),
    })
    print(f"探索设计文档已登记（feature '{feature}'）：{design_doc}")
    print(f"自包含登记已落 change 目录：openspec/changes/{feature}/.specpowers-meta.json")
    print("propose 阶段将以此为探索凭据（缺失会被前置校验拦回 explore）")
    return 0


def _as_relative(root: Path, design_doc: str) -> str:
    """设计文档路径归一为相对 root 的 posix 路径（meta 自包含跨机友好）。

    绝对路径在 root 内 → 相对化；不在 root 内（异常输入/跨盘符）原样保留。

    作者：005819 | 协作：GLM-5.3
    """
    path = Path(design_doc)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return design_doc


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
    "record-design-doc": _handle_record_design_doc,
}


def route(stage: str, root: Path, extra: dict | None = None) -> int:
    """Route a stage command to its handler.

    This is the main entry point for all stage operations.
    Called by facade.py command handlers.

    Args:
        stage: Stage name (init, explore, propose, fast, apply, archive, baseline, reset,
               auto-new-round, auto-clarify, record-design-doc)
        root: Project root path
        extra: Additional parameters (requirement, force, force_merge_check, etc.).

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

    # 未初始化兜底须在 lock 之前：报错即返回，不占锁不留锁残留
    # 作者：005819 | 协作：GLM-5.3
    _check_initialized(root, stage)

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
