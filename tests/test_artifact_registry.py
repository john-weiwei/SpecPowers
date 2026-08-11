"""Tests for artifact_registry — 路径 A 下的产物路径解析。

验证：
- DYNAMIC_KINDS = {proposal, spec, tasks}（不再是 brief/spec/plan）
- required_for 解析动态产物到 openspec/changes/<feature>/ 路径
- proposal/tasks 解析为精确文件，spec 解析为 specs 目录级
- mode 过滤（full/fast）
"""

from specpowers_cli.bridge.modules.artifact_registry import (
    required_for, get_artifact, list_by_producer, list_by_consumer,
    DYNAMIC_KINDS, MANIFEST,
)


def test_dynamic_kinds_are_openspec_categories():
    """DYNAMIC_KINDS 为 proposal/spec/tasks（路径 A）。"""
    assert DYNAMIC_KINDS == {"proposal", "spec", "tasks"}


def test_manifest_proposal_producer_is_brainstorm():
    """proposal 的 producer 是 brainstorm。"""
    proposal = get_artifact("proposal")
    assert proposal is not None
    assert proposal["producer"] == "brainstorm"


def test_manifest_spec_producer_is_specify():
    """spec 的 producer 是 specify。"""
    spec = get_artifact("spec")
    assert spec is not None
    assert spec["producer"] == "specify"


def test_manifest_tasks_producer_is_plan():
    """tasks 的 producer 是 plan。"""
    tasks = get_artifact("tasks")
    assert tasks is not None
    assert tasks["producer"] == "plan"


def test_required_for_specify_hard_requires_proposal_full_mode():
    """specify 阶段 full 模式硬性要求 proposal（倒逼 brainstorm 必须完成探索）。

    proposal 的 required 为 {"full": True, "fast": False}：
    full 模式下 proposal（含「数据流契约」小节）是 specify 的硬依赖，
    防止 brainstorming 被架空；fast 模式跳过 brainstorm/specify 故不需要。
    """
    required = required_for("specify", "full", feature="login")
    paths = [a["path"] for a in required]
    # proposal 在 full 模式硬必需列表
    assert "openspec/changes/login/proposal.md" in paths


def test_required_for_plan_includes_spec_full_mode():
    """plan 阶段 full 模式需要 spec（delta spec）。"""
    required = required_for("plan", "full", feature="login")
    paths = [a["path"] for a in required]
    assert "openspec/changes/login/specs" in paths


def test_required_for_build_includes_tasks_full_mode():
    """build 阶段 full 模式需要 tasks。"""
    required = required_for("build", "full", feature="login")
    paths = [a["path"] for a in required]
    assert "openspec/changes/login/tasks.md" in paths


def test_required_for_build_includes_spec_for_verification():
    """build 阶段需要 spec（验证 Scenario）。"""
    required = required_for("build", "full", feature="login")
    paths = [a["path"] for a in required]
    assert "openspec/changes/login/specs" in paths


def test_required_for_archive_includes_spec():
    """archive 阶段需要 spec（归档输入）。"""
    required = required_for("archive", "full", feature="login")
    paths = [a["path"] for a in required]
    assert "openspec/changes/login/specs" in paths


def test_required_for_constitution_always():
    """constitution.md 所有认知阶段都需要。"""
    for stage in ["brainstorm", "specify", "plan", "build", "archive"]:
        required = required_for(stage, "full", feature="login")
        paths = [a["path"] for a in required]
        assert ".specpowers/constitution.md" in paths


def test_required_for_fast_mode_excludes_proposal():
    """fast 模式不需要 proposal（跳过 brainstorm/specify）。"""
    required = required_for("build", "fast", feature="login")
    paths = [a["path"] for a in required]
    # proposal 不在 fast 必需列表（required={"full": True, "fast": False}）
    assert "openspec/changes/login/proposal.md" not in paths


def test_required_for_empty_feature_defaults_unnamed():
    """空 feature 兜底为 unnamed（spec/tasks 动态产物解析时）。"""
    # 用 plan 阶段（需要 spec，spec 是必需的）测试空 feature 兜底
    required = required_for("plan", "full", feature="")
    paths = [a["path"] for a in required]
    assert any("unnamed" in p for p in paths)


def test_required_for_chinese_feature():
    """中文 feature 路径正确解析（spec 产物）。"""
    # 用 plan 阶段（spec 是必需的）测试中文路径解析
    required = required_for("plan", "full", feature="用户登录")
    paths = [a["path"] for a in required]
    assert "openspec/changes/用户登录/specs" in paths


def test_list_by_producer_brainstorm():
    """brainstorm 产出 proposal。"""
    artifacts = list_by_producer("brainstorm")
    paths = [a["path"] for a in artifacts]
    assert "proposal" in paths


def test_list_by_consumer_build():
    """build 消费 tasks 和 spec。"""
    artifacts = list_by_consumer("build")
    paths = [a["path"] for a in artifacts]
    assert "tasks" in paths
    assert "spec" in paths