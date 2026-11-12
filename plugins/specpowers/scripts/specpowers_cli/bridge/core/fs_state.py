"""Atomic file state operations for state.json.

Uses temp-file + rename pattern for atomic writes.

v2.8.0 起 schema 2（多活跃需求，单文件 features 映射模型）：

顶层 .specpowers/state.json —— 唯一状态文件：
{
    "schema": 2,              # 结构版本（无 schema 键 = schema 1 扁平旧结构）
    "fallback_count": int,    # 人工回退限额计次（跨需求刻意保留，归档/reset 不清）
    "last_archive_ref": str,  # 最近一次归档时的 HEAD（merge check 基准）
    "features": {             # 活跃需求映射（每需求一份需求级状态）
        "<slug>": {
            "stage": str,           # explore|propose|apply|archive（ready 仅 fast 分片）
            "mode": str,            # full|fast
            "execution_mode": str,  # conductor|worktree|subagent|tdd（空=未选择）
            "iteration_count": int, # auto 迭代轮次（0=首轮；删需求即清零）
            "design_doc": str,      # explore 登记的设计文档路径（空=未登记）
            "created_at": str,      # 需求纳入时间（展示用）
            "last_touched": str     # 最近一次写入时间（前台推导依据）
        }
    }
}

前台（active）需求 = features 中 last_touched 最大者，推导式不落盘
（与 openspec list --sort recent 同构）：操作谁（save_state 视图的 feature）
谁自动成为前台；多会话并行时无指针争抢写点。并发正确性由 route() 的
全局锁保证（命令级读-改-写全程互斥），无需按 feature 拆状态文件。

auto_base 是唯一按需求拆分的文件（.specpowers/auto_base/<slug>.json）：
它由认知层（agent）在 auto 第 0 步直接写盘、不持锁，多需求并行时必须
物理隔离防串扰。

兼容层（关键设计）：load_state 返回「全局 + 前台需求展开」的扁平视图
（旧 schema 1 结构的超集），save_state 按视图 feature 拆回映射——上层
（dispatcher handlers / mode_controller）继续按扁平 dict 读写，无感知。
schema 1（v2.7.0 及以前扁平顶层）读出即迁移：feature 非空 → 迁入
features 映射 + 顶层 auto_base.json 搬入 auto_base/<slug>.json；幂等。
"""

import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


def _utc_now_iso() -> str:
    """当前 UTC 时间的 ISO 格式字符串（微秒精度，保 last_touched 排序分辨率）。"""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


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


# ---- schema 2 结构常量 ----

# 顶层全局字段（跨需求生命周期）
GLOBAL_KEYS = ("schema", "fallback_count", "last_archive_ref", "features")

# 需求级字段（存 features 映射的每个条目，随需求生灭）
FEATURE_KEYS = ("stage", "mode", "execution_mode", "iteration_count", "design_doc")

DEFAULT_GLOBAL_STATE = {
    "schema": 2,
    # 人工回退限额计次：整个项目生命周期最多 1 次 apply→propose 回退，
    # 归档/reset 均不清除（跨需求刻意保留，防 reset 刷额度）
    "fallback_count": 0,
    # 最近一次归档时的 HEAD（merge check 基准）
    "last_archive_ref": "",
    # 活跃需求映射（slug → 需求级状态）
    "features": {},
}

DEFAULT_FEATURE_STATE = {
    # explore|propose|apply|archive（ready 仅 fast 模式需求出现：
    # fast 把状态设为 ready+mode=fast 待编码验收）
    "stage": "ready",
    # full|fast
    "mode": "full",
    # apply 阶段选择的执行方式：conductor|worktree|subagent|tdd（空=未选择）
    "execution_mode": "",
    # auto 模式需求迭代轮次（0=首轮；删除该需求即清零）
    "iteration_count": 0,
    # explore 阶段登记的设计文档路径（propose 前置校验凭据；空=未登记）
    "design_doc": "",
    # 需求纳入时间（展示用）
    "created_at": "",
    # 最近一次写入时间（前台推导依据，每次 save_state 刷新）
    "last_touched": "",
}

# 兼容别名：旧代码/测试按扁平视图引用 DEFAULT_STATE。视图形态 =
# 全局默认 + 空前台展开（stage=init 表示从未执行过 init）。
DEFAULT_STATE = {
    **{k: v for k, v in DEFAULT_GLOBAL_STATE.items() if k != "features"},
    "stage": "init",
    "mode": "full",
    "feature": "",
    "execution_mode": "",
    "iteration_count": 0,
    "design_doc": "",
}

# v2.0.0 阶段重命名的旧值映射（schema 1 迁移 + 读出惰性归一，幂等：
# 新名不在表内原样返回）：constitution→init、brainstorm→explore、
# specify/plan→propose、build→apply；ready/archive 不变。
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


# ---- 路径解析 ----

def _get_state_path(root: Path) -> Path:
    """Return path to state.json（顶层，全局字段 + features 映射）."""
    return root / ".specpowers" / "state.json"


def _auto_base_dir(root: Path) -> Path:
    """auto 基点目录：.specpowers/auto_base/（每需求一个 <slug>.json）。"""
    return root / ".specpowers" / "auto_base"


def auto_base_path(root: Path, feature: str) -> Path:
    """auto 基点文件路径（v2.8.0 起按 feature 隔离）。

    auto_base 由认知层第 0 步直接写盘（不持锁），多需求并行时必须
    物理隔离，是唯一按需求拆分的状态文件。

    Args:
        root: 项目根目录。
        feature: feature slug（auto_base 所属需求）。

    Returns:
        .specpowers/auto_base/<feature>.json 路径。
    """
    return _auto_base_dir(root) / f"{feature}.json"


# ---- JSON 读写（含损坏校验） ----

def _read_json_object(path: Path, label: str) -> dict:
    """读取 JSON 对象；损坏或非对象时抛 FatalError 引导 reset。

    Args:
        path: 目标 JSON 文件。
        label: 报错文案中的人类可读文件名（如 state.json）。

    Returns:
        解析后的 dict。

    Raises:
        FatalError: JSON 解析失败或顶层非对象。
    """
    from specpowers_cli.bridge.core.errors import FatalError
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise FatalError(
            f"{label} is corrupted: {e}. "
            f"Run /specpowers-reset to recover."
        )
    # 顶层类型校验：合法 JSON 但非对象（数组/字符串/数字）时后续合并
    # 逻辑会抛意外异常或静默混入错误结构，显式拒绝并引导 reset
    if not isinstance(data, dict):
        raise FatalError(
            f"{label} is corrupted: top level must be a JSON object, "
            f"got {type(data).__name__}. "
            f"Run /specpowers-reset to recover."
        )
    return data


# ---- schema 1 → schema 2 迁移 ----

def _is_legacy_schema(data: dict) -> bool:
    """判定顶层 state.json 是否为 schema 1（v2.7.0 及以前的扁平结构）。"""
    return data.get("schema") != 2


def _migrate_schema1(root: Path, data: dict) -> dict:
    """schema 1 扁平顶层 → schema 2 features 映射，迁移即写盘（幂等）。

    - feature 非空：需求级字段迁入 features[<feature>]，顶层
      auto_base.json（若存在）原子搬入 auto_base/<feature>.json
    - feature 为空：顶层直接重写 schema 2 空映射（需求级字段随无活跃丢弃）
    - 死字段 fallback_used（v2.7.0 及以前仅定义无读写）借迁移清除

    与既有「读出惰性迁移不写回」模式的差异：顶层结构本身变了，不写盘
    则每次 load 都重复迁移，故主动落盘；原子写保证并发下幂等。

    Args:
        root: 项目根目录。
        data: schema 1 顶层内容。

    Returns:
        迁移后的 schema 2 顶层 dict。
    """
    feature = str(data.get("feature") or "").strip()
    migrated = {
        "schema": 2,
        "fallback_count": data.get("fallback_count", 0),
        "last_archive_ref": data.get("last_archive_ref", ""),
        "features": {},
    }

    if feature:
        now = _utc_now_iso()
        migrated["features"][feature] = {
            "stage": migrate_legacy_stage(str(data.get("stage", "ready"))),
            "mode": str(data.get("mode", "full")),
            "execution_mode": str(data.get("execution_mode", "")),
            "iteration_count": int(data.get("iteration_count", 0) or 0),
            "design_doc": str(data.get("design_doc", "")),
            "created_at": now,
            "last_touched": now,
        }
        # 顶层 auto_base.json 搬入按需求隔离的新位置（目标已存在则跳过防覆盖）
        legacy_base = root / ".specpowers" / "auto_base.json"
        if legacy_base.exists():
            target = auto_base_path(root, feature)
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(str(legacy_base), str(target))

    atomic_write_json(_get_state_path(root), migrated)
    return migrated


# ---- 顶层加载（含迁移与默认合并） ----

def _load_raw(root: Path) -> dict:
    """加载顶层 schema 2 状态（schema 1 自动迁移）；文件不存在返回默认值。

    Returns:
        顶层 dict（features 值恒为 dict，各条目已与 DEFAULT_FEATURE_STATE 合并）。

    Raises:
        FatalError: state.json 损坏（JSON 非法或顶层非对象）。
    """
    state_path = _get_state_path(root)
    if not state_path.exists():
        # 深隔离：features 必须是独立 dict——浅拷贝会让调用方的写入
        # 污染模块级 DEFAULT_GLOBAL_STATE，造成跨目录状态串扰
        fresh = dict(DEFAULT_GLOBAL_STATE)
        fresh["features"] = {}
        return fresh
    data = _read_json_object(state_path, "state.json")
    if _is_legacy_schema(data):
        data = _migrate_schema1(root, data)
    result = dict(DEFAULT_GLOBAL_STATE)
    result.update(data)
    if not isinstance(result.get("features"), dict):
        # features 非对象（手改坏）：按空映射降级，需求状态以磁盘工件为准
        result["features"] = {}
    # 各需求条目与默认值合并（容忍旧条目缺 created_at/last_touched 等新键）
    merged_features = {}
    for slug, entry in result["features"].items():
        if not isinstance(entry, dict):
            continue
        item = dict(DEFAULT_FEATURE_STATE)
        item.update(entry)
        merged_features[str(slug)] = item
    result["features"] = merged_features
    return result


# ---- 需求级操作 ----

def list_features(root: Path) -> list[str]:
    """枚举活跃需求 slug（features 映射键），按名字排序。

    活跃需求集合 = state 映射事实；「单一活跃」的旧假设不再存在。
    """
    return sorted(_load_raw(root)["features"].keys())


def load_feature(root: Path, feature: str) -> dict | None:
    """读取单个活跃需求的状态；不在映射中返回 None。

    Args:
        root: 项目根目录。
        feature: feature slug。

    Returns:
        需求级状态 dict（已与默认值合并）；无该需求时 None。
    """
    raw = _load_raw(root)
    entry = raw["features"].get(feature)
    if entry is None:
        return None
    item = dict(DEFAULT_FEATURE_STATE)
    item.update(entry)
    return item


def foreground_feature(root: Path) -> str:
    """推导前台需求：features 中 last_touched 最大者；无活跃返回空串。

    tie-break：last_touched 相同时 list_features 的名字序先到者胜，
    保证推导稳定。前台不落盘（多会话并行时无争抢写点）。
    """
    raw = _load_raw(root)
    best = ""
    best_ts = ""
    for slug in sorted(raw["features"].keys()):
        ts = str(raw["features"][slug].get("last_touched") or "")
        if ts > best_ts:
            best = slug
            best_ts = ts
    return best


def features_snapshot(root: Path) -> dict:
    """活跃需求概览（status/粘滞/多活跃报错共用）：slug → 精简视图。"""
    raw = _load_raw(root)
    return {
        slug: {
            "stage": entry.get("stage", ""),
            "mode": entry.get("mode", ""),
            "iteration_count": entry.get("iteration_count", 0),
        }
        for slug, entry in sorted(raw["features"].items())
    }


def touch_feature(root: Path, feature: str) -> dict:
    """刷新需求 last_touched（switch 命令的实现原语：touch 即切前台）。

    Args:
        root: 项目根目录。
        feature: 目标需求 slug。

    Returns:
        刷新后的需求级状态 dict。

    Raises:
        FatalError: 目标不是活跃需求（switch 必须指名活跃者）。
    """
    from specpowers_cli.bridge.core.errors import FatalError
    raw = _load_raw(root)
    entry = raw["features"].get(feature)
    if entry is None:
        active = ", ".join(sorted(raw["features"].keys())) or "（无）"
        raise FatalError(
            f"switch 目标 '{feature}' 不是活跃需求。当前活跃：{active}。"
            f"用法：facade switch <slug> --root ."
        )
    entry["last_touched"] = _utc_now_iso()
    raw["features"][feature] = entry
    atomic_write_json(_get_state_path(root), raw)
    return entry


def delete_feature(root: Path, feature: str) -> bool:
    """删除需求：features 映射移除该键 + auto_base/<slug>.json 一并清理。

    归档（归档即该需求完结）与 reset --feature（放弃指定需求）共用；
    其余活跃需求不受影响，前台自动切换为剩余 last_touched 最大者。

    Args:
        root: 项目根目录。
        feature: feature slug。

    Returns:
        是否实际删除了活跃需求（映射中原本存在）。
    """
    raw = _load_raw(root)
    existed = raw["features"].pop(feature, None) is not None
    atomic_write_json(_get_state_path(root), raw)
    base = auto_base_path(root, feature)
    if base.exists():
        base.unlink()
    return existed


def cleanup_auto_base(root: Path, keep: list[str]) -> int:
    """清理 auto_base 目录中不属于 keep 集合的残留文件，返回清理数。

    fresh 判定（无活跃需求 → keep 为空即全清）与归档后兜底共用；
    keep 内的 slug 文件（活跃需求的基线）不受影响。

    Args:
        root: 项目根目录。
        keep: 保留的 feature slug 集合。
    """
    base_dir = _auto_base_dir(root)
    if not base_dir.is_dir():
        return 0
    removed = 0
    keep_set = {f"{slug}.json" for slug in keep}
    for entry in base_dir.glob("*.json"):
        if entry.name not in keep_set:
            entry.unlink(missing_ok=True)
            removed += 1
    return removed


def clear_features(root: Path) -> None:
    """清空全部活跃需求（保留 fallback_count/last_archive_ref 等全局字段）。

    init --force（CI 自动确认）与 reset 的共用原语：features 映射清空 +
    auto_base/ 目录残留一并清理；前台随无活跃自动为空。
    """
    raw = _load_raw(root)
    raw["features"] = {}
    atomic_write_json(_get_state_path(root), raw)
    base_dir = _auto_base_dir(root)
    if base_dir.is_dir():
        for entry in base_dir.glob("*.json"):
            entry.unlink(missing_ok=True)


# ---- 扁平视图（兼容层核心） ----

def load_state(root: Path, feature: str = "") -> dict:
    """Load state（全局 + 目标需求展开的扁平视图）。

    视图形态（旧 schema 1 结构超集，上层无感知映射结构）：
    - feature / stage / mode / execution_mode / iteration_count / design_doc
      取目标需求；无活跃需求时 feature=""、stage 取 "init"
      （state.json 不存在，从未 init）或 "ready"（空转）
    - fallback_count / last_archive_ref 取顶层全局
    - schema 键透传（值恒为 2，供消费者识别结构版本）

    Args:
        root: 项目根目录。
        feature: 目标需求 slug；空串 = 前台（last_touched 最大者）。
                 非空且不在活跃映射中 → FatalError（多活跃防错路由）。

    Raises:
        FatalError: state.json 损坏，或 feature 非空但不是活跃需求。
    """
    from specpowers_cli.bridge.core.errors import FatalError
    raw = _load_raw(root)
    view = {
        "schema": raw["schema"],
        "fallback_count": raw["fallback_count"],
        "last_archive_ref": raw["last_archive_ref"],
    }

    fg = feature.strip() or foreground_feature(root)
    if fg:
        entry = raw["features"].get(fg)
        if entry is None:
            active = ", ".join(sorted(raw["features"].keys())) or "（无）"
            raise FatalError(
                f"'{fg}' 不是活跃需求。当前活跃：{active}。"
                f"多活跃时命令须显式 --feature 指定目标需求。"
            )
        view["feature"] = fg
        for key in FEATURE_KEYS:
            view[key] = entry.get(key, DEFAULT_FEATURE_STATE[key])
        return view

    # 无活跃需求：stage 取决于项目是否执行过 init（state.json 存在与否）
    view["feature"] = ""
    view["stage"] = "ready" if _get_state_path(root).exists() else "init"
    view["mode"] = "full"
    view["execution_mode"] = ""
    view["iteration_count"] = 0
    view["design_doc"] = ""
    return view


def save_state(root: Path, state: dict) -> None:
    """Atomically write state（拆解：全局键 → 顶层，需求级键 → features 条目）。

    视图 feature 非空时：需求级字段写入 features[<feature>] 并刷新
    last_touched（操作即前台）；feature 为空时仅更新顶层全局键
    （features 映射原样保留——空视图 ≠ 清空全部活跃需求，删除走
    delete_feature）。
    """
    raw = _load_raw(root)

    # 顶层全局键：从视图同步；未识别键保留（兼容旧承诺）
    for key, value in state.items():
        if key in ("feature", "features") or key in FEATURE_KEYS:
            continue
        raw[key] = value
    raw["schema"] = 2

    feature = str(state.get("feature") or "").strip()
    if feature:
        now = _utc_now_iso()
        entry = dict(raw["features"].get(feature, {}))
        if not entry.get("created_at"):
            entry["created_at"] = now
        for key in FEATURE_KEYS:
            if key in state:
                entry[key] = state[key]
        entry["last_touched"] = now
        raw["features"][feature] = entry

    atomic_write_json(_get_state_path(root), raw)


def atomic_write_json(path: Path, data: dict) -> None:
    """原子写 JSON 文件（临时文件 + rename），state/auto_base 等状态文件共用。

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


def init_state(root: Path) -> dict:
    """Initialize state.json with defaults and persist（schema 2 全局层）."""
    state = dict(DEFAULT_GLOBAL_STATE)
    atomic_write_json(_get_state_path(root), state)
    return state


def reset_state(root: Path) -> dict:
    """Reset 全局状态（保留 fallback_count）并清空全部活跃需求。

    多活跃需求下「全清」入口：单活跃或确认放弃全部时使用；按需求放弃
    走 delete_feature（dispatcher _handle_reset --feature 分流）。
    fallback_count 刻意保留：reset 不能刷回退额度。
    """
    old_raw = _load_raw(root)
    new_raw = {
        "schema": 2,
        "fallback_count": old_raw.get("fallback_count", 0),
        "last_archive_ref": "",
        "features": {},
    }
    atomic_write_json(_get_state_path(root), new_raw)
    # auto_base 目录整体清理（全清语义下按需求残留无意义）
    base_dir = _auto_base_dir(root)
    if base_dir.is_dir():
        for entry in base_dir.glob("*.json"):
            entry.unlink(missing_ok=True)
    # 返回扁平视图（无活跃 → stage=ready）
    view = dict(DEFAULT_STATE)
    view["stage"] = "ready"
    view["fallback_count"] = new_raw["fallback_count"]
    return view


def delete_state(root: Path) -> None:
    """Delete state.json (for full reset)."""
    state_path = _get_state_path(root)
    if state_path.exists():
        state_path.unlink()
