"""Artifact registry — 定义流水线产物及其依赖关系（路径 A：OpenSpec change 产物）。

v2.0.0 五阶段（init → explore → propose → apply → archive）下，explore 产出设计文档
（docs/specpowers/design/，路径动态登记在 state.design_doc，不适用 feature 推导，
由 dispatcher 特殊校验兜底，不进本注册表），propose 一站式产出 OpenSpec change 三件套：
- proposal  → openspec/changes/<feature>/proposal.md        （propose 产出）
- spec      → openspec/changes/<feature>/specs/<capability>/spec.md （propose 产出）
- tasks     → openspec/changes/<feature>/tasks.md            （propose 产出）

固定路径产物（项目级，不随 feature 变化）：
- constitution.md / baseline.json / state.json / .lock → .specpowers/

每个 artifact 含：
- layer: "cognitive" 或 "deterministic"
- path: 固定路径 或 动态类别标识（"proposal"/"spec"/"tasks"，由 path_resolver 解析）
- producer: 产出该 artifact 的 stage
- consumers: 读取该 artifact 的 stage
- required: True（总是必需）或 {"full": True, "fast": False}（按模式）

作者：005819 | 协作：GLM-5.2
"""

from typing import TypedDict


class Artifact(TypedDict):
    layer: str
    path: str
    producer: str
    consumers: list[str]
    required: bool | dict


# 动态路径产物的类别标识集合（path 字段非真实路径，由 path_resolver 按类别解析）
# proposal → openspec/changes/<feature>/proposal.md
# spec     → openspec/changes/<feature>/specs/（capability 未知，校验到 specs 目录级）
# tasks    → openspec/changes/<feature>/tasks.md
DYNAMIC_KINDS = {"proposal", "spec", "tasks"}


MANIFEST: list[Artifact] = [
    {
        "layer": "cognitive",
        "path": ".specpowers/constitution.md",
        "producer": "init",
        "consumers": ["explore", "propose", "apply", "archive"],
        "required": True,
    },
    {
        "layer": "cognitive",
        "path": "proposal",  # 动态：openspec/changes/<feature>/proposal.md
        "producer": "propose",
        "consumers": ["apply"],
        # full 模式下 proposal（含「数据流契约」小节）是 apply 的硬依赖，
        # apply 入口确定性层校验数据流契约段头，倒逼 propose 必须承接 explore
        # 探索结论（防止探索被架空，探空转直写 proposal）。fast 模式无 proposal。
        "required": {"full": True, "fast": False},
    },
    {
        "layer": "cognitive",
        "path": "spec",  # 动态：openspec/changes/<feature>/specs/<capability>/spec.md
        "producer": "propose",
        "consumers": ["apply", "archive"],
        "required": {"full": True, "fast": False},
    },
    {
        "layer": "cognitive",
        "path": "tasks",  # 动态：openspec/changes/<feature>/tasks.md
        "producer": "propose",
        "consumers": ["apply"],
        "required": {"full": True, "fast": False},
    },
    {
        "layer": "deterministic",
        "path": ".specpowers/baseline.json",
        "producer": "init",
        "consumers": ["apply", "archive", "baseline"],
        "required": True,
    },
    {
        "layer": "deterministic",
        "path": ".specpowers/state.json",
        "producer": "init",
        "consumers": ["*"],
        "required": True,
    },
]


def required_for(stage: str, mode: str, feature: str = "") -> list[Artifact]:
    """返回进入某 stage 前必需的 artifact 列表。

    动态产物（proposal/spec/tasks）的 path 由 feature 解析为 openspec change 路径：
    - proposal → openspec/changes/<feature>/proposal.md（精确文件）
    - spec     → openspec/changes/<feature>/specs（目录级，capability 未知时校验目录存在）
    - tasks    → openspec/changes/<feature>/tasks.md（精确文件）

    Args:
        stage: 目标 stage 名。
        mode: full / fast。
        feature: feature slug。动态路径产物需用它解析实际路径。

    Returns:
        必需 artifact 列表，动态产物的 path 已解析为相对路径字符串。
    """
    from pathlib import PurePosixPath
    from specpowers_cli.bridge.modules.path_resolver import (
        resolve_change_proposal, resolve_change_tasks, resolve_change_dir,
    )

    required = []
    for art in MANIFEST:
        if stage in art["consumers"] or "*" in art["consumers"]:
            req = art["required"]
            needed = False
            if isinstance(req, dict):
                if req.get(mode, True):
                    needed = True
            elif req:
                needed = True

            if needed:
                resolved_rel = _resolve_dynamic_path(art, feature)
                required.append({**art, "path": resolved_rel})
    return required


def _resolve_dynamic_path(art: Artifact, feature: str) -> str:
    """把动态产物的类别标识解析为相对路径字符串。

    Args:
        art: 含动态 path 的 artifact。
        feature: feature slug。

    Returns:
        正斜杠相对路径字符串。
    """
    from pathlib import PurePosixPath
    from specpowers_cli.bridge.modules.path_resolver import (
        resolve_change_proposal, resolve_change_tasks, resolve_change_dir,
    )

    if art["path"] not in DYNAMIC_KINDS:
        return art["path"]

    kind = art["path"]
    if not feature or not feature.strip():
        feature = "unnamed"

    if kind == "proposal":
        resolved = resolve_change_proposal(PurePosixPath(""), feature)
    elif kind == "tasks":
        resolved = resolve_change_tasks(PurePosixPath(""), feature)
    elif kind == "spec":
        # spec 校验到 specs 目录级（capability 未知时无法精确到文件）
        resolved = resolve_change_dir(PurePosixPath(""), feature) / "specs"
    else:
        return art["path"]

    return "/".join(resolved.parts)


def has_consumer(artifact: Artifact) -> bool:
    """检查 artifact 是否有 consumer（value gate guardian）。

    延迟 consumer（如 trace/audit）算有效 consumer。
    """
    consumers = artifact.get("consumers", [])
    return len(consumers) > 0


def get_artifact(path: str) -> Artifact | None:
    """按 path（或类别标识）查找 artifact。"""
    for art in MANIFEST:
        if art["path"] == path:
            return art
    return None


def list_by_producer(stage: str) -> list[Artifact]:
    """列出某 stage 产出的 artifact。"""
    return [art for art in MANIFEST if art["producer"] == stage]


def list_by_consumer(stage: str) -> list[Artifact]:
    """列出某 stage 消费的 artifact。"""
    result = []
    for art in MANIFEST:
        if stage in art["consumers"] or "*" in art["consumers"]:
            result.append(art)
    return result
