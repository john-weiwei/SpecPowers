"""产物路径解析器——OpenSpec change 产物的动态路径单一出口。

路径方案（feature slug 作为文件名前缀，同一流程天然一致）：
- proposal → openspec/changes/<feature>/proposal.md（propose 产出）
- spec     → openspec/changes/<feature>/specs/<capability>/spec.md（propose 产出）
- tasks    → openspec/changes/<feature>/tasks.md（propose 产出）

explore 阶段产物为设计文档（docs/specpowers/design/，路径动态登记在
state.design_doc，不随 feature 推导，不经过本模块）。

固定路径产物（项目级，不随 feature 变化，仍由各自模块管理）：
- constitution.md / baseline.json / state.json / .lock → .specpowers/

所有需要生成 change 产物路径的代码都应通过本模块，避免路径散落多处。
"""

from pathlib import Path

# 保留的 feature slug：与 OpenSpec 归档目录或 Windows 设备名冲突，禁止直接用作 change 名
# - "archive"：openspec/changes/archive/ 是归档快照目录，同名 change 会被自引用移动
# - con/prn/aux/nul/com1-9/lpt1-9：Windows 保留设备名，用作目录名行为异常
# 作者：005819 | 协作：GLM-5.3
RESERVED_FEATURE_SLUGS = frozenset(
    {"archive", "con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)

# 保留字冲突时的后缀（拼在 slug 后避免撞名）
RESERVED_FALLBACK_SUFFIX = "-feature"


def sanitize_feature_slug(slug: str) -> str:
    """校验并修正 feature slug，规避与系统目录/设备名的冲突。

    slug 命中保留字（archive、Windows 设备名等，大小写不敏感）时追加
    后缀消歧；其余值原样返回（幂等，已修正值不会被二次修改）。

    Args:
        slug: 待校验的 feature slug。

    Returns:
        可安全用作目录名的 feature slug。
    """
    if slug and slug.lower() in RESERVED_FEATURE_SLUGS:
        return slug + RESERVED_FALLBACK_SUFFIX
    return slug


def resolve_openspec_change(root: Path, feature: str) -> Path:
    """解析 OpenSpec change 目录的绝对路径（临时 active change，归档前所在位置）。

    路径：openspec/changes/<feature>
    归档成功后 OpenSpec 会把它移到 openspec/changes/archive/YYYY-MM-DD-<feature>/。
    作为纵深防御，feature 在拼接前统一过 sanitize_feature_slug，
    即使调用方传入未净化的保留字（如 "archive"）也不会落到归档目录本身。

    Args:
        root: 项目根目录。
        feature: feature slug，作为 change 名（保留原样，含中文亦可）。
    """
    if not feature or not feature.strip():
        feature = "unnamed"
    feature = sanitize_feature_slug(feature)
    return root / "openspec" / "changes" / feature


def resolve_openspec_spec(root: Path, capability: str) -> Path:
    """解析 OpenSpec 主规格（合并目标）的绝对路径。

    路径：openspec/specs/<capability>/spec.md
    capability 默认等于 feature slug（specpowers 一个 feature = 一个 capability）。

    Args:
        root: 项目根目录。
        capability: 能力名（目录名），通常与 feature 一致。
    """
    if not capability or not capability.strip():
        capability = "unnamed"
    return root / "openspec" / "specs" / capability / "spec.md"


def resolve_openspec_archive_dir(root: Path) -> Path:
    """解析 OpenSpec 归档目录（change 快照最终落点）的绝对路径。

    路径：openspec/changes/archive/
    目录不保证已存在，调用方按需 mkdir。
    """
    return root / "openspec" / "changes" / "archive"


# ---- OpenSpec change 产物路径（路径 A：propose 一次性生成）----

def resolve_change_dir(root: Path, feature: str) -> Path:
    """解析 OpenSpec change 目录（active 状态，归档前所在位置）。

    路径：openspec/changes/<feature>
    propose 阶段一次性写入此目录（v2.0.0 合并原 brainstorm/specify/plan 的落盘职责）：
      - proposal.md（方案提案，承接 explore 设计文档结论）
      - specs/<capability>/spec.md（delta 规格）
      - tasks.md（任务清单）
    归档成功后 OpenSpec 把它整体移到 openspec/changes/archive/YYYY-MM-DD-<feature>/。

    Args:
        root: 项目根目录。
        feature: feature slug，作为 change 名。
    """
    return resolve_openspec_change(root, feature)


def resolve_change_proposal(root: Path, feature: str) -> Path:
    """解析 change 的 proposal.md 路径（propose 产出）。

    路径：openspec/changes/<feature>/proposal.md
    OpenSpec 结构：## Why / ## What Changes / ## Capabilities / ## Impact
    """
    return resolve_change_dir(root, feature) / "proposal.md"


def resolve_change_spec(root: Path, feature: str, capability: str) -> Path:
    """解析 change 的 delta spec 路径（propose 产出）。

    路径：openspec/changes/<feature>/specs/<capability>/spec.md
    capability 默认 = feature slug（独立能力）；
    迭代场景 capability 来自 proposal.md 的 frontmatter（共享已有能力）。

    Args:
        root: 项目根目录。
        feature: feature slug（change 名）。
        capability: 能力名（delta spec 所属目录，决定归档时合并到哪个主规格）。
    """
    if not capability or not capability.strip():
        capability = feature if feature and feature.strip() else "unnamed"
    return resolve_change_dir(root, feature) / "specs" / capability / "spec.md"


def resolve_change_tasks(root: Path, feature: str) -> Path:
    """解析 change 的 tasks.md 路径（propose 产出）。

    路径：openspec/changes/<feature>/tasks.md
    OpenSpec 复选框格式：## 任务组 / - [ ] 任务项
    apply 阶段执行时勾选 - [x]。
    """
    return resolve_change_dir(root, feature) / "tasks.md"


def ensure_feature_locked(state: dict) -> str:
    """从 state 取已锁定的 feature slug，防止跨阶段漂移。

    feature 一旦在 explore/fast 阶段写入 state，后续阶段（propose/apply/
    archive）应复用同一值，保证 openspec change 目录与产物名一致。

    Args:
        state: state.json 加载出的 dict。

    Returns:
        feature slug；若 state 中为空则返回 "unnamed"。
    """
    feature = state.get("feature", "")
    if not feature or not feature.strip():
        return "unnamed"
    return feature.strip()
