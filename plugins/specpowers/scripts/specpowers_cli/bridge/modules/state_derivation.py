"""工件推导纯函数集 — 流水线状态从 openspec/changes/ 工件推导（v2.12 落地 / v3.0 成为唯一权威）。

定位（v3.0.0）：state.json 退役，本模块是流水线状态的唯一权威信源——
- 活跃性：active_slugs 扫目录（change 目录含三件套或 .specpowers-meta.json 任一）
- 阶段：derive_stage 按工件形态判定（explore/propose/apply/fast），取代 VALID_TRANSITIONS
- 迭代轮次：iteration_count_of 从 design-round-<N>.md 与 tasks.md「## Round <N>」推导
- 前台：foreground_slug 取 meta last_touched 最大者（推导式，无全局指针）
- 设计文档指针：change 目录 .specpowers-meta.json 的 design_doc 字段
- 旧 state 迁移：migrate_legacy_state 首次命令触发（meta 齐全化 + runtime.json + .bak 留底）

唯一写动作是 meta（write_meta/update_meta，原子写复用 fs_state 范式，调用方持锁）；
migrate_legacy_state 是另一处写点（state.json.bak 留底 + runtime.json + meta 齐全化）。

作者：005819 | 协作：GLM-5.3 | 日期：2026-11-17
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

# change 目录内自包含登记文件名（OpenSpec 对该 dotfile 无感知，随目录归档）
META_FILENAME = ".specpowers-meta.json"

# 轮次痕迹的提取模式（受 OpenSpec validator 与 task-brief 切分硬约束，锚点不漂移）
_DESIGN_ROUND_RE = re.compile(r"^design-round-(\d+)\.md$", re.IGNORECASE)
_TASKS_ROUND_RE = re.compile(r"^##\s+Round\s+(\d+)", re.MULTILINE)

# tasks.md 勾选标记（apply 进度事实源）；「## 已作废」小节内的勾选非执行进度
_TASK_DONE_RE = re.compile(r"^\s*- \[x\]", re.MULTILINE)
_RETIRED_SECTION = "## 已作废"

# stage 判定值域（archived 由 is_archived 承担——archive 目录不在活跃扫描内）
STAGE_EXPLORE = "explore"
STAGE_PROPOSE = "propose"
STAGE_APPLY = "apply"
STAGE_FAST = "fast"


def change_dir_of(root: Path, slug: str) -> Path:
    """需求 change 目录路径（openspec/changes/<slug>/）。"""
    return root / "openspec" / "changes" / slug


def is_active_change(change_dir: Path) -> bool:
    """活跃判定：三件套（proposal/specs/tasks）与 meta 登记任一存在。

    v2.12 扩展 meta：explore 收口即落 meta（尚无三件套），该需求不被
    active_changes 遗漏；空目录与缺失目录不活跃。

    Args:
        change_dir: change 目录路径。

    Returns:
        是否视为活跃 change。
    """
    if not change_dir.is_dir():
        return False
    return (
        (change_dir / "proposal.md").exists()
        or (change_dir / "specs").is_dir()
        or (change_dir / "tasks.md").exists()
        or (change_dir / META_FILENAME).exists()
    )


def iteration_count_of(change_dir: Path) -> int:
    """迭代轮次推导：design-round-N.md 与 tasks.md Round 小节取最大值。

    Args:
        change_dir: change 目录路径。

    Returns:
        推导轮次（无任何痕迹返回 0 = 首轮）。
    """
    best = 0
    if not change_dir.is_dir():
        return 0
    # 来源一：design-round-<N>.md 文件名（方案变更轮落盘，v2.7.0 起）
    for item in change_dir.iterdir():
        match = _DESIGN_ROUND_RE.match(item.name)
        if match:
            best = max(best, int(match.group(1)))
    # 来源二：tasks.md 轮次小节标题（场景调整轮落盘，v2.11.0 骨架锚点）
    tasks = change_dir / "tasks.md"
    if tasks.is_file():
        text = tasks.read_text(encoding="utf-8", errors="replace")
        for match in _TASKS_ROUND_RE.finditer(text):
            best = max(best, int(match.group(1)))
    return best


def read_meta(change_dir: Path) -> dict | None:
    """读取 meta 登记；缺失或损坏（非法 JSON/非对象）降级返回 None 不阻断。

    Args:
        change_dir: change 目录路径。

    Returns:
        meta dict；无法读取时 None（视同缺失降级）。
    """
    meta_path = change_dir / META_FILENAME
    if not meta_path.is_file():
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        # 损坏降级：meta 是登记缓存不是事实源本体，坏登记不影响主流程
        return None
    if not isinstance(data, dict):
        return None
    return data


def write_meta(root: Path, slug: str, design_doc: str) -> Path:
    """写入自包含登记（确保 change 目录存在 + 原子写）。

    record-design-doc 收口调用：design_doc 相对路径落 change 目录，
    created_at 仅首次生成（目录创建时间语义，重复登记不刷新）。

    Args:
        root: 项目根目录。
        slug: feature slug。
        design_doc: 设计文档相对路径。

    Returns:
        meta 文件路径。
    """
    # 延迟导入防循环（fs_state 读后对账会反向导入本模块）
    from specpowers_cli.bridge.core.fs_state import atomic_write_json
    existing = read_meta(change_dir_of(root, slug)) or {}
    updates = {"design_doc": design_doc}
    if not existing.get("created_at"):
        updates["created_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return update_meta(root, slug, updates)


def update_meta(root: Path, slug: str, updates: dict) -> Path:
    """合并更新 meta（读现有 → 合并 → 原子写；目录不存在时创建）。

    v3.0 起是 mode/execution_mode/last_touched/design_doc 的统一写点
    （fast 入口、record-execution-mode、switch、record-design-doc 共用）。

    Args:
        root: 项目根目录。
        slug: feature slug。
        updates: 要合并的字段（浅合并，覆盖同名键）。

    Returns:
        meta 文件路径。
    """
    from specpowers_cli.bridge.core.fs_state import atomic_write_json
    existing = read_meta(change_dir_of(root, slug)) or {}
    meta_path = change_dir_of(root, slug) / META_FILENAME
    atomic_write_json(meta_path, {**existing, **updates})
    return meta_path


def design_doc_of(root: Path, slug: str) -> str | None:
    """设计文档指针推导：读 meta 的 design_doc 字段。

    Args:
        root: 项目根目录。
        slug: feature slug。

    Returns:
        登记的相对路径；meta 缺失/损坏/值为空时 None（工件无法证明）。
    """
    meta = read_meta(change_dir_of(root, slug))
    if meta is None:
        return None
    value = str(meta.get("design_doc") or "").strip()
    return value or None


def derive_stage(change_dir: Path) -> str:
    """阶段工件判定（v3.0 唯一 stage 权威，取代 VALID_TRANSITIONS 矩阵）。

    判定表（按序短路）：
    - 目录不存在 → explore（未开工或探索进行中）
    - meta.mode=fast → fast（fast 态无三件套，自包含登记在 meta+checklist）
    - proposal.md 缺 → explore（仅 meta = 探索完成待 propose）
    - specs/ 或 tasks.md 缺 → propose（proposal 已落、三件套未齐 = 进行中）
    - 三件套齐 + tasks 有勾选（排除「## 已作废」小节）→ apply
    - 三件套齐 + 无勾选 → propose（apply 可入，apply 入口另有工件校验）

    Args:
        change_dir: change 目录路径。

    Returns:
        阶段值 {explore, propose, apply, fast}；archived 由 is_archived 承担。
    """
    if not change_dir.is_dir():
        return STAGE_EXPLORE
    meta = read_meta(change_dir) or {}
    if str(meta.get("mode") or "").strip() == "fast":
        return STAGE_FAST
    if not (change_dir / "proposal.md").is_file():
        return STAGE_EXPLORE
    if not (change_dir / "specs").is_dir() or not (change_dir / "tasks.md").is_file():
        return STAGE_PROPOSE
    # 勾选判定取「## 已作废」之前的活动区（作废留痕的勾选非执行进度）
    tasks_text = (change_dir / "tasks.md").read_text(encoding="utf-8", errors="replace")
    active_part = tasks_text.split(_RETIRED_SECTION)[0]
    if _TASK_DONE_RE.search(active_part):
        return STAGE_APPLY
    return STAGE_PROPOSE


def is_archived(root: Path, slug: str) -> bool:
    """归档判定：changes/archive/<slug>/ 快照目录存在即已归档（需求终结）。"""
    return (root / "openspec" / "changes" / "archive" / slug).is_dir()


def active_slugs(root: Path) -> list[str]:
    """活跃需求清单（v3.0 唯一活跃权威）：扫描 changes/ 非归档目录。

    取代 features 映射——目录被手动删除/归档的需求即时从清单消失，
    僵尸条目类漂移从源头消灭。

    Args:
        root: 项目根目录。

    Returns:
        活跃 slug 列表（按名排序）。
    """
    base = root / "openspec" / "changes"
    if not base.is_dir():
        return []
    return sorted(
        d.name for d in base.iterdir()
        if d.is_dir() and d.name != "archive" and is_active_change(d)
    )


def _touched_epoch(change_dir: Path) -> float:
    """前台排序键：meta last_touched 优先，缺失/损坏降级目录 mtime。"""
    meta = read_meta(change_dir) or {}
    raw = str(meta.get("last_touched") or "").strip()
    if raw:
        try:
            return datetime.fromisoformat(raw).timestamp()
        except ValueError:
            pass
    try:
        return change_dir.stat().st_mtime
    except OSError:
        return 0.0


def foreground_slug(root: Path) -> str | None:
    """前台推导：active_slugs 中 meta last_touched 最大者（无全局写点）。

    Args:
        root: 项目根目录。

    Returns:
        前台 slug；无活跃需求时 None。
    """
    slugs = active_slugs(root)
    if not slugs:
        return None
    return max(slugs, key=lambda s: _touched_epoch(change_dir_of(root, s)))


def audit_artifacts(root: Path, slug: str) -> list[str]:
    """工件一致性核对（facade reconcile 报告用，纯判定不写盘）。

    v3.0 下推导即权威、无「不一致」概念，核对只覆盖两类异常：
    meta 文件存在但损坏（推导按缺失降级的可追溯信号）、目录已消失
    （清单外的残留引用场景）。

    Args:
        root: 项目根目录。
        slug: feature slug。

    Returns:
        警告行列表（无异常返回空列表）。
    """
    change_dir = change_dir_of(root, slug)
    if not change_dir.is_dir():
        return [f"[审计] '{slug}' change 目录不存在（已归档或被删除）"]
    warnings: list[str] = []
    if (change_dir / META_FILENAME).exists() and read_meta(change_dir) is None:
        warnings.append(f"[审计] '{slug}' meta 损坏（非法 JSON），推导按缺失降级；可删除该文件或修复后重试")
    return warnings


def migrate_legacy_state(root: Path) -> dict:
    """旧 state.json 退役迁移（首次命令触发，幂等）。

    三步：① features 条目转换——有 change 目录者 meta 齐全化
    （design_doc/mode/execution_mode/last_touched/created_at 仅补缺），
    无目录条目警告丢弃（explore 未收口无工件，重跑即可）；
    ② fallback_count/last_archive_ref 写 runtime.json；
    ③ state.json 改名 state.json.bak 留底（可人工删除）。

    schema 1（v2.7.0 及以前扁平顶层）兼容：顶层 feature 字段视作单条目。
    损坏 state：留底为 state.json.corrupted-<时间戳>，条目丢弃（工件侧
    可经 reconcile 重建），报告标注 corrupted。

    Args:
        root: 项目根目录。

    Returns:
        迁移报告 dict（migrated/features_migrated/dropped/runtime/warnings/corrupted）。
    """
    from specpowers_cli.bridge.core.fs_state import atomic_write_json
    state_path = root / ".specpowers" / "state.json"
    report: dict = {
        "migrated": False,
        "features_migrated": [],
        "dropped": [],
        "warnings": [],
        "corrupted": False,
    }
    if not state_path.is_file():
        return report
    raw: dict = {}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            raise ValueError("top level must be a JSON object")
        raw = loaded
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        # 损坏留底：条目无法解析即丢弃，工件侧 reconcile 可重建
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = state_path.with_name(f"state.json.corrupted-{stamp}")
        state_path.rename(backup)
        report.update(migrated=True, corrupted=True, warnings=[
            f"[迁移] state.json 损坏（{exc}），已留底为 {backup.name}；"
            f"活跃需求将从 openspec/changes/ 工件推导，如需恢复请 facade reconcile"
        ])
        return report

    # 条目归一：schema 2 读 features 映射；schema 1 顶层扁平字段视作单条目
    features = raw.get("features")
    if not isinstance(features, dict) or not features:
        legacy_slug = str(raw.get("feature") or "").strip()
        features = {legacy_slug: raw} if legacy_slug else {}
    report["migrated"] = True

    for slug, entry in features.items():
        slug = str(slug).strip()
        if not slug or not isinstance(entry, dict):
            continue
        change_dir = change_dir_of(root, slug)
        if not is_active_change(change_dir):
            # explore 未收口 / 目录已被手动删除：无工件可迁，重跑入口即可
            report["dropped"].append(slug)
            report["warnings"].append(
                f"[迁移] '{slug}'（stage={entry.get('stage')}）无 change 目录，"
                f"条目丢弃；如需继续请重走对应入口"
            )
            continue
        # meta 齐全化：仅补缺失字段，不覆盖已有（幂等重跑安全）
        updates: dict = {}
        for key in ("design_doc", "mode", "execution_mode", "last_touched", "created_at"):
            value = str(entry.get(key) or "").strip()
            if value:
                updates[key] = value
        if updates:
            update_meta(root, slug, updates)
        report["features_migrated"].append(slug)

    # runtime 承接：跨需求全局过程字段（fallback 额度刻意跨迁移保留）
    runtime = {
        "fallback_count": int(raw.get("fallback_count") or 0),
        "last_archive_ref": str(raw.get("last_archive_ref") or ""),
    }
    atomic_write_json(root / ".specpowers" / "runtime.json", runtime)
    report["runtime"] = runtime

    # 留底退役：改名保留回退凭据（升级须知注明可删）
    state_path.rename(state_path.with_name("state.json.bak"))
    return report


def _is_exempt(entry: dict) -> bool:
    """对账豁免判定（v2.12 遗留，随 fs_state 读后对账钩子在 v3.0 退役）。

    explore 态与 ready 态目录合法缺席，条目保留。ready 含 fast（待用户
    编码，无三件套）与 auto 编排中间态（auto 第 0 步后、explore 驱动前
    stage 停在 ready）。
    """
    stage = str(entry.get("stage") or "")
    return stage in ("explore", "ready")


def reconcile_feature(root: Path, slug: str, entry: dict) -> tuple[dict | None, list[str]]:
    """读后对账：state 条目与工件目录对齐（纯判定，不写盘）。

    Args:
        root: 项目根目录。
        slug: feature slug。
        entry: fs_state 读出的需求级条目。

    Returns:
        (对齐后条目, 警告行列表)。条目为 None = 僵尸（调用方应清理）；
        警告行供命令输出与对账报告消费。
    """
    if _is_exempt(entry):
        return entry, []

    change_dir = change_dir_of(root, slug)
    if not change_dir.is_dir():
        # propose 窗口保护：命令跃迁与三件套落盘之间的合法窗口（多会话
        # 并行读到不得误清）——仅警告；apply/archive 无此窗口，直接清理
        if str(entry.get("stage") or "") == "propose":
            return entry, [
                f"[对账] 需求 '{slug}' 处于 propose 态但 change 目录暂缺"
                f"（三件套落盘窗口或目录被移除）；窗口期保留条目，持续出现"
                f"请 facade reconcile 处理"
            ]
        # 僵尸条目：apply/archive 态无目录 = 目录被手动归档/删除——推导式
        # 下以工件为权威
        return None, [
            f"[对账] 需求 '{slug}'（stage={entry.get('stage')}）的 change 目录"
            f"不存在，条目已清理；如需恢复请 facade reconcile（目录含 meta 时可重建）"
        ]

    warnings: list[str] = []
    result = dict(entry)

    # 轮次回写：工件推导值为准（高于缓存才回写并留差异行）
    derived_round = iteration_count_of(change_dir)
    cached_round = int(entry.get("iteration_count") or 0)
    if derived_round > cached_round:
        result["iteration_count"] = derived_round
        warnings.append(
            f"[对账] 需求 '{slug}' iteration_count {cached_round} → {derived_round}"
            f"（以工件推导为准）"
        )

    # 指针回填：meta 提供值且缓存为空时回填（meta 缺失保留缓存——旧登记仍有效）
    if not str(entry.get("design_doc") or "").strip():
        derived_doc = design_doc_of(root, slug)
        if derived_doc:
            result["design_doc"] = derived_doc
            warnings.append(
                f"[对账] 需求 '{slug}' design_doc 已从 meta 回填：{derived_doc}"
            )

    return result, warnings
