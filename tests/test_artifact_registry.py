"""Tests for artifact_registry — 路径 A 下的产物路径解析（v2.0.0 五阶段）。

验证：
- DYNAMIC_KINDS = {proposal, spec, tasks}（不再是 brief/spec/plan）
- required_for 解析动态产物到 openspec/changes/<feature>/ 路径
- proposal/tasks 解析为精确文件，spec 解析为 specs 目录级
- mode 过滤（full/fast）
- propose 一站式产三件套（producer 全归 propose），explore 产出设计文档
  （动态登记路径，不进 MANIFEST，由 dispatcher 特殊校验兜底）
"""

from specpowers_cli.bridge.modules.artifact_registry import (
    required_for, get_artifact, list_by_producer, list_by_consumer,
    DYNAMIC_KINDS, MANIFEST,
)


def test_dynamic_kinds_are_openspec_categories():
    """DYNAMIC_KINDS 为 proposal/spec/tasks（路径 A）。"""
    assert DYNAMIC_KINDS == {"proposal", "spec", "tasks"}


def test_manifest_proposal_producer_is_propose():
    """proposal 的 producer 是 propose（v2.0.0：从设计文档提炼，不再由 explore 落盘）。"""
    proposal = get_artifact("proposal")
    assert proposal is not None
    assert proposal["producer"] == "propose"


def test_manifest_spec_producer_is_propose():
    """spec 的 producer 是 propose。"""
    spec = get_artifact("spec")
    assert spec is not None
    assert spec["producer"] == "propose"


def test_manifest_tasks_producer_is_propose():
    """tasks 的 producer 是 propose。"""
    tasks = get_artifact("tasks")
    assert tasks is not None
    assert tasks["producer"] == "propose"


def test_required_for_apply_hard_requires_proposal_full_mode():
    """apply 阶段 full 模式硬性要求 proposal（倒逼 propose 必须承接 explore 探索结论）。

    proposal 的 required 为 {"full": True, "fast": False}：
    full 模式下 proposal（含「数据流契约」小节）是 apply 的硬依赖，
    防止探索结论被架空；fast 模式跳过 explore/propose 故不需要。
    """
    required = required_for("apply", "full", feature="login")
    paths = [a["path"] for a in required]
    # proposal 在 full 模式硬必需列表
    assert "openspec/changes/login/proposal.md" in paths


def test_required_for_apply_includes_spec_full_mode():
    """apply 阶段 full 模式需要 spec（delta spec，验证 Scenario）。"""
    required = required_for("apply", "full", feature="login")
    paths = [a["path"] for a in required]
    assert "openspec/changes/login/specs" in paths


def test_required_for_apply_includes_tasks_full_mode():
    """apply 阶段 full 模式需要 tasks。"""
    required = required_for("apply", "full", feature="login")
    paths = [a["path"] for a in required]
    assert "openspec/changes/login/tasks.md" in paths


def test_required_for_propose_does_not_consume_change_artifacts():
    """propose 是三件套的生产者而非消费者：入口不要求 proposal/spec/tasks 已存在。

    （探索完成凭据是 state.design_doc，由 dispatcher 特殊校验兜底，不走 MANIFEST。）
    """
    required = required_for("propose", "full", feature="login")
    paths = [a["path"] for a in required]
    assert "openspec/changes/login/proposal.md" not in paths
    assert "openspec/changes/login/specs" not in paths
    assert "openspec/changes/login/tasks.md" not in paths


def test_required_for_archive_includes_spec():
    """archive 阶段需要 spec（归档输入）。"""
    required = required_for("archive", "full", feature="login")
    paths = [a["path"] for a in required]
    assert "openspec/changes/login/specs" in paths


def test_required_for_constitution_always():
    """constitution.md 所有认知阶段都需要。"""
    for stage in ["explore", "propose", "apply", "archive"]:
        required = required_for(stage, "full", feature="login")
        paths = [a["path"] for a in required]
        assert ".specpowers/constitution.md" in paths


def test_required_for_fast_mode_excludes_proposal():
    """fast 模式不需要 proposal（跳过 explore/propose）。"""
    required = required_for("apply", "fast", feature="login")
    paths = [a["path"] for a in required]
    # proposal 不在 fast 必需列表（required={"full": True, "fast": False}）
    assert "openspec/changes/login/proposal.md" not in paths


def test_required_for_empty_feature_defaults_unnamed():
    """空 feature 兜底为 unnamed（spec/tasks 动态产物解析时）。"""
    # 用 apply 阶段（需要 spec，spec 是必需的）测试空 feature 兜底
    required = required_for("apply", "full", feature="")
    paths = [a["path"] for a in required]
    assert any("unnamed" in p for p in paths)


def test_required_for_chinese_feature():
    """中文 feature 路径正确解析（spec 产物）。"""
    # 用 apply 阶段（spec 是必需的）测试中文路径解析
    required = required_for("apply", "full", feature="用户登录")
    paths = [a["path"] for a in required]
    assert "openspec/changes/用户登录/specs" in paths


def test_list_by_producer_propose_yields_three_artifacts():
    """propose 一站式产出 proposal/spec/tasks 三件套。"""
    artifacts = list_by_producer("propose")
    paths = [a["path"] for a in artifacts]
    assert "proposal" in paths
    assert "spec" in paths
    assert "tasks" in paths


def test_list_by_producer_init_yields_fixed_artifacts():
    """init 产出 constitution.md / baseline.json / state.json（固定路径产物）。"""
    artifacts = list_by_producer("init")
    paths = [a["path"] for a in artifacts]
    assert ".specpowers/constitution.md" in paths
    assert ".specpowers/baseline.json" in paths


def test_list_by_consumer_apply():
    """apply 消费 proposal、tasks 和 spec。"""
    artifacts = list_by_consumer("apply")
    paths = [a["path"] for a in artifacts]
    assert "proposal" in paths
    assert "tasks" in paths
    assert "spec" in paths
