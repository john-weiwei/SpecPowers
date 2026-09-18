"""Tests for auto 模式多轮迭代 — 三分判定 / new-round 受控切换 / 归档清理 / feature 锁定。

覆盖方案 docs/auto-iteration-plan.md 的确定性层改动：
- auto-status 三分判定（fresh 残留清理 / resume 文档未变 / iterate 文档变更与口头指令 / 人工流程接管 / 旧格式兼容）
- auto new-round（轮次递增 + feature 锁定 + rounds 落盘 + 旧格式迁移 + 三类拒绝）
- brainstorm/specify 的 --feature 显式锁定
- 归档成功后清理 auto_base.json + iteration_count 清零

作者：005819 | 协作：GLM-5.3
"""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from specpowers_cli.bridge.core.errors import StateError


def _create_temp_git_repo(tmp_path: Path) -> Path:
    """在 pytest tmp_path 下创建带提交的临时 git 仓库。"""
    root = tmp_path / "auto-iter-repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(root), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(root), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(root), capture_output=True, check=True,
    )
    (root / "README.md").write_text("# Test", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(root), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"],
        cwd=str(root), capture_output=True, check=True,
    )
    return root


def _write_auto_base(root: Path, data: dict) -> None:
    """写入 .specpowers/auto_base.json（测试辅助）。"""
    base_dir = root / ".specpowers"
    base_dir.mkdir(exist_ok=True)
    (base_dir / "auto_base.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8",
    )


def _read_auto_base(root: Path) -> dict:
    """读取 .specpowers/auto_base.json（测试辅助）。"""
    return json.loads(
        (root / ".specpowers" / "auto_base.json").read_text(encoding="utf-8"),
    )


def _seed_active_auto_feature(root: Path, feature: str = "auto-feat",
                              iteration_count: int = 1, stage: str = "build") -> None:
    """构造活跃 auto 需求：stage 默认 build、iteration_count 默认 1（已跑过一轮）。"""
    from specpowers_cli.bridge.core.fs_state import save_state, DEFAULT_STATE

    state = dict(DEFAULT_STATE)
    state["stage"] = stage
    state["mode"] = "full"
    state["feature"] = feature
    state["iteration_count"] = iteration_count
    state["execution_mode"] = "conductor"
    save_state(root, state)
    _write_auto_base(root, {
        "base_commit": "aaa111",
        "feature": feature,
        "design_doc": "",
        "design_doc_hash": "",
        "created_at": "2026-01-01T00:00:00+00:00",
        "rounds": [{
            "round": 1,
            "input": {"type": "doc", "doc": "design.md", "instruction": ""},
            "started_at": "2026-01-01T00:00:00+00:00",
        }],
    })


def _make_design_doc(tmp_path: Path, name: str = "design.md", content: str = "# 设计") -> Path:
    """在 tmp 下创建设计文档，返回路径。"""
    doc = tmp_path / name
    doc.write_text(content, encoding="utf-8")
    return doc


# ---- auto-status 三分判定 ----

def test_auto_status_fresh_and_cleans_legacy_base(tmp_path):
    """无活跃 feature → fresh；上一需求的 auto_base.json 残留顺带清理（归档即新需求）。"""
    from specpowers_cli.bridge.dispatcher import auto_status
    from specpowers_cli.bridge.core.fs_state import save_state, DEFAULT_STATE

    root = _create_temp_git_repo(tmp_path)
    state = dict(DEFAULT_STATE)
    state["stage"] = "ready"
    save_state(root, state)
    _write_auto_base(root, {"base_commit": "old", "design_doc": "old.md"})

    result = auto_status(root)
    assert result["mode"] == "fresh"
    assert result["auto_base_removed"] is True
    assert not (root / ".specpowers" / "auto_base.json").exists()


def test_auto_status_resume_when_doc_unchanged(tmp_path):
    """活跃需求 + 文档 hash 未变 + 无指令 → resume（断点续跑）。"""
    from specpowers_cli.bridge.dispatcher import auto_status

    root = _create_temp_git_repo(tmp_path)
    doc = _make_design_doc(tmp_path, content="# 设计 v1")
    _seed_active_auto_feature(root)
    base = _read_auto_base(root)
    base["design_doc"] = str(doc)
    base["design_doc_hash"] = hashlib.sha256(doc.read_bytes()).hexdigest()
    _write_auto_base(root, base)

    result = auto_status(root, design_doc=str(doc))
    assert result["mode"] == "resume"
    assert result["iteration_count"] == 1


def test_auto_status_iterate_on_doc_change_scope_full(tmp_path):
    """文档内容变更（hash 不同）→ iterate + scope_hint=full，轮次建议 +1。"""
    from specpowers_cli.bridge.dispatcher import auto_status

    root = _create_temp_git_repo(tmp_path)
    old_doc = _make_design_doc(tmp_path, name="design-v1.md", content="# 设计 v1")
    new_doc = _make_design_doc(tmp_path, name="design-v2.md", content="# 设计 v2")
    _seed_active_auto_feature(root)
    base = _read_auto_base(root)
    base["design_doc"] = str(old_doc)
    base["design_doc_hash"] = hashlib.sha256(old_doc.read_bytes()).hexdigest()
    _write_auto_base(root, base)

    result = auto_status(root, design_doc=str(new_doc))
    assert result["mode"] == "iterate"
    assert result["scope_hint"] == "full"
    assert result["round"] == 2
    assert result["design_doc_exists"] is True


def test_auto_status_iterate_on_instruction_only_scope_light(tmp_path):
    """仅口头指令（无文档）→ iterate + scope_hint=light。"""
    from specpowers_cli.bridge.dispatcher import auto_status

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root)

    result = auto_status(root, instruction="补充导出失败的失败场景")
    assert result["mode"] == "iterate"
    assert result["scope_hint"] == "light"


def test_auto_status_iterate_when_manual_pipeline_no_base(tmp_path):
    """人工流程被 auto 接管（活跃 feature 无 auto_base.json）→ iterate + auto_base_missing。"""
    from specpowers_cli.bridge.dispatcher import auto_status
    from specpowers_cli.bridge.core.fs_state import save_state, DEFAULT_STATE

    root = _create_temp_git_repo(tmp_path)
    state = dict(DEFAULT_STATE)
    state["stage"] = "specify"
    state["feature"] = "manual-feat"
    save_state(root, state)

    result = auto_status(root)
    assert result["mode"] == "iterate"
    assert result["auto_base_missing"] is True
    assert result["scope_hint"] == "full"


def test_auto_status_legacy_base_same_path_resume_diff_path_iterate(tmp_path):
    """旧格式 base（无 hash 基准）：同路径视为未变 → resume；异路径 → iterate。"""
    from specpowers_cli.bridge.dispatcher import auto_status

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root)
    legacy = _read_auto_base(root)
    legacy.pop("rounds")
    legacy.pop("design_doc_hash")

    doc = _make_design_doc(tmp_path)
    legacy["design_doc"] = str(doc)
    _write_auto_base(root, legacy)
    assert auto_status(root, design_doc=str(doc))["mode"] == "resume"

    other = _make_design_doc(tmp_path, name="other.md")
    assert auto_status(root, design_doc=str(other))["mode"] == "iterate"


def test_auto_status_missing_doc_marks_not_exists(tmp_path):
    """传入的文档不存在 → 保守按新输入（iterate），并标记 design_doc_exists=False。"""
    from specpowers_cli.bridge.dispatcher import auto_status

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root)

    missing = tmp_path / "not-exist.md"
    result = auto_status(root, design_doc=str(missing))
    assert result["mode"] == "iterate"
    assert result["design_doc_exists"] is False


# ---- auto new-round 受控轮次切换 ----

def test_auto_new_round_increments_and_locks_feature(tmp_path):
    """new-round：iteration_count+1、stage→specify、feature 锁定、rounds 追加、execution_mode 清空。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import load_state

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root, iteration_count=1)

    new_doc = _make_design_doc(tmp_path, name="design-v2.md")
    assert route("auto-new-round", "full", root, extra={
        "design_doc": str(new_doc), "instruction": "补充失败场景",
    }) == 0

    state = load_state(root)
    assert state["iteration_count"] == 2
    assert state["stage"] == "specify"
    assert state["feature"] == "auto-feat"
    assert state["execution_mode"] == ""

    base = _read_auto_base(root)
    assert len(base["rounds"]) == 2
    assert base["rounds"][1]["round"] == 2
    assert base["rounds"][1]["input"]["type"] == "doc+instruction"
    assert base["design_doc"] == str(new_doc)
    assert base["design_doc_hash"]


def test_auto_new_round_migrates_legacy_base(tmp_path):
    """旧格式 base（无 rounds 字段）→ 迁移为 round 1，新轮追加为 round 2。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import load_state

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root, iteration_count=0)
    legacy = _read_auto_base(root)
    legacy.pop("rounds")
    legacy["design_doc"] = "old-design.md"
    _write_auto_base(root, legacy)

    assert route("auto-new-round", "full", root, extra={"instruction": "第二轮"}) == 0

    base = _read_auto_base(root)
    assert [r["round"] for r in base["rounds"]] == [1, 2]
    assert base["rounds"][0]["note"].startswith("旧格式")
    # 迁移代表历史已跑一轮：轮次基线校正为 1，新轮为 2
    assert load_state(root)["iteration_count"] == 2


def test_auto_new_round_requires_auto_base(tmp_path):
    """无 auto_base.json → 拒绝（不是 auto 模式需求）。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import save_state, DEFAULT_STATE

    root = _create_temp_git_repo(tmp_path)
    state = dict(DEFAULT_STATE)
    state["stage"] = "build"
    state["feature"] = "plain-feat"
    save_state(root, state)

    with pytest.raises(StateError):
        route("auto-new-round", "full", root, extra={})


def test_auto_new_round_requires_active_feature(tmp_path):
    """state 无活跃 feature（已归档）→ 拒绝。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import save_state, DEFAULT_STATE

    root = _create_temp_git_repo(tmp_path)
    state = dict(DEFAULT_STATE)
    state["stage"] = "ready"
    save_state(root, state)
    _write_auto_base(root, {"base_commit": "x"})

    with pytest.raises(StateError):
        route("auto-new-round", "full", root, extra={})


def test_auto_new_round_rejected_when_archived(tmp_path):
    """feature 已有 archive commit → 拒绝迭代轮（归档即新需求）。"""
    from specpowers_cli.bridge.dispatcher import route

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root, feature="archived-feat")
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", "specpowers: archived-feat"],
        cwd=str(root), capture_output=True, check=True,
    )

    with pytest.raises(StateError):
        route("auto-new-round", "full", root, extra={})


# ---- feature 显式锁定（--feature）----

def test_brainstorm_explicit_feature_lock(tmp_path):
    """brainstorm --feature 显式锁定 slug，不随 requirement 措辞漂移。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import save_state, DEFAULT_STATE, load_state

    root = _create_temp_git_repo(tmp_path)
    state = dict(DEFAULT_STATE)
    state["stage"] = "ready"
    save_state(root, state)
    (root / ".specpowers").mkdir(exist_ok=True)
    (root / ".specpowers" / "constitution.md").write_text("# C", encoding="utf-8")

    assert route("brainstorm", "full", root, extra={
        "requirement": "全新需求措辞",
        "feature": "locked-feat",
    }) == 0
    assert load_state(root)["feature"] == "locked-feat"


def test_specify_explicit_feature_overrides_existing(tmp_path):
    """specify --feature 显式指定优先级高于 state 已有 feature。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import load_state, save_state

    root = _create_temp_git_repo(tmp_path)
    state = load_state(root)
    state["stage"] = "brainstorm"
    state["feature"] = "origin-feat"
    save_state(root, state)
    (root / ".specpowers").mkdir(exist_ok=True)
    (root / ".specpowers" / "constitution.md").write_text("# C", encoding="utf-8")
    # proposal 按显式锁定的 slug 解析路径（迭代场景 change 目录即锁定 slug）
    proposal = root / "openspec" / "changes" / "locked-feat" / "proposal.md"
    proposal.parent.mkdir(parents=True, exist_ok=True)
    proposal.write_text("## 数据流契约\n\n本特性无跨链路字段\n", encoding="utf-8")

    assert route("specify", "full", root, extra={
        "requirement": "需求描述",
        "feature": "locked-feat",
    }) == 0
    assert load_state(root)["feature"] == "locked-feat"


# ---- 归档清理 auto_base.json + iteration_count 清零 ----

def test_archive_cleans_auto_base_and_resets_iteration(tmp_path, monkeypatch):
    """归档成功：auto_base.json 删除、iteration_count 清零、feature 清空（双通道统一生效）。"""
    import specpowers_cli.bridge.modules.archive_auditor as archive_auditor
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import load_state

    monkeypatch.setattr(
        archive_auditor, "prepare_openspec_archive",
        lambda root, feature, state, skip_validation=False: {
            "archivedAs": feature, "specsUpdated": False,
        },
    )

    root = _create_temp_git_repo(tmp_path)
    feature = "auto-feat"
    _seed_active_auto_feature(root, feature=feature, iteration_count=2)
    # archive 前置产物：constitution.md + baseline.json + delta spec 目录
    (root / ".specpowers" / "constitution.md").write_text("# C", encoding="utf-8")
    (root / ".specpowers" / "baseline.json").write_text(
        '{"git_ref":"","top_dirs":[],"deps":{},"src_patterns":[]}', encoding="utf-8",
    )
    spec_dir = root / "openspec" / "changes" / feature / "specs" / feature
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(
        "## ADDED Requirements\n\n### Requirement: " + feature +
        "\nThe system SHALL work.\n\n#### Scenario: s1\n- **WHEN** x\n- **THEN** y\n",
        encoding="utf-8",
    )

    assert route("archive", "full", root, extra={}) == 0

    assert not (root / ".specpowers" / "auto_base.json").exists()
    state = load_state(root)
    assert state["stage"] == "ready"
    assert state["feature"] == ""
    assert state["iteration_count"] == 0


# ---- 人工模式迭代轮（specify/brainstorm 重入识别 → facade iterate，不要求 auto_base.json）----

def test_iterate_without_auto_base_succeeds(tmp_path):
    """人工流程（无 auto_base.json）也能开启迭代轮：stage→specify、feature 锁定、计数+1。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import load_state, save_state, DEFAULT_STATE

    root = _create_temp_git_repo(tmp_path)
    state = dict(DEFAULT_STATE)
    state["stage"] = "build"
    state["mode"] = "full"
    state["feature"] = "manual-feat"
    state["execution_mode"] = "conductor"
    save_state(root, state)

    assert route("iterate", "full", root, extra={"instruction": "补充失败场景"}) == 0

    state = load_state(root)
    assert state["stage"] == "specify"
    assert state["feature"] == "manual-feat"
    assert state["iteration_count"] == 1
    assert state["execution_mode"] == ""
    # 无 auto 基线时不落盘 auto_base.json（人工模式无此文件）
    assert not (root / ".specpowers" / "auto_base.json").exists()


def test_iterate_with_auto_base_updates_rounds(tmp_path):
    """人工入口但 auto_base.json 存在（auto/人工共用基线）→ rounds 同样追加。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import load_state

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root, iteration_count=1)

    assert route("iterate", "full", root, extra={"instruction": "调整范围"}) == 0

    assert load_state(root)["iteration_count"] == 2
    base = _read_auto_base(root)
    assert [r["round"] for r in base["rounds"]] == [1, 2]
    assert base["rounds"][1]["input"]["type"] == "instruction"


def test_iterate_rejected_when_archived(tmp_path):
    """人工模式迭代：feature 已归档 → 拒绝（归档即新需求，两模式一致）。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import save_state, DEFAULT_STATE

    root = _create_temp_git_repo(tmp_path)
    state = dict(DEFAULT_STATE)
    state["stage"] = "build"
    state["feature"] = "done-feat"
    save_state(root, state)
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", "specpowers: done-feat"],
        cwd=str(root), capture_output=True, check=True,
    )

    with pytest.raises(StateError):
        route("iterate", "full", root, extra={})


def test_iterate_does_not_consume_fallback_count(tmp_path):
    """迭代轮不占用 fallback 额度：iterate 后 fallback_count 仍为 0，build→specify 回退仍可用。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import load_state, save_state, DEFAULT_STATE

    root = _create_temp_git_repo(tmp_path)
    state = dict(DEFAULT_STATE)
    state["stage"] = "build"
    state["mode"] = "fast"
    state["feature"] = "manual-feat"
    save_state(root, state)
    (root / ".specpowers").mkdir(exist_ok=True)
    (root / ".specpowers" / "constitution.md").write_text("# C", encoding="utf-8")
    # fallback（build→specify）前置：proposal 含数据流契约
    proposal = root / "openspec" / "changes" / "manual-feat" / "proposal.md"
    proposal.parent.mkdir(parents=True, exist_ok=True)
    proposal.write_text("## 数据流契约\n\n本特性无跨链路字段\n", encoding="utf-8")

    # 先消耗唯一一次 fallback（build→specify）
    assert route("specify", "full", root, extra={"requirement": "升级完整流程"}) == 0
    assert load_state(root)["fallback_count"] == 1

    # 推回 build 后走 iterate（不是 fallback）→ 放行且 fallback_count 不变
    state = load_state(root)
    state["stage"] = "build"
    save_state(root, state)
    assert route("iterate", "full", root, extra={}) == 0
    assert load_state(root)["fallback_count"] == 1
    assert load_state(root)["stage"] == "specify"


def _seed_manual_iteration_repo(tmp_path: Path, feature: str = "manual-feat") -> Path:
    """构造人工模式活跃需求的完整前置（constitution + proposal 含数据流契约）。"""
    root = _create_temp_git_repo(tmp_path)
    from specpowers_cli.bridge.core.fs_state import save_state, DEFAULT_STATE

    state = dict(DEFAULT_STATE)
    state["stage"] = "build"
    state["mode"] = "full"
    state["feature"] = feature
    save_state(root, state)
    (root / ".specpowers").mkdir(exist_ok=True)
    (root / ".specpowers" / "constitution.md").write_text("# C", encoding="utf-8")
    proposal = root / "openspec" / "changes" / feature / "proposal.md"
    proposal.parent.mkdir(parents=True, exist_ok=True)
    proposal.write_text("## 数据流契约\n\n本特性无跨链路字段\n", encoding="utf-8")
    return root


def test_specify_self_loop_after_iterate_continues_round(tmp_path):
    """迭代轮开启后重跑 /specpowers-specify（from specify 自环）→ 放行续作：轮次不变、feature 锁定、不消耗 fallback。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import load_state

    root = _seed_manual_iteration_repo(tmp_path)
    assert route("iterate", "full", root, extra={"instruction": "补充失败场景"}) == 0
    assert load_state(root)["iteration_count"] == 1

    # 迭代轮中重跑 specify：自环幂等放行（续作修订，不是新一轮，也不占 fallback 额度）
    assert route("specify", "full", root, extra={"requirement": "补充失败场景"}) == 0

    state = load_state(root)
    assert state["stage"] == "specify"
    assert state["feature"] == "manual-feat"
    assert state["iteration_count"] == 1
    assert state["fallback_count"] == 0


def test_specify_self_loop_idempotent_without_iteration(tmp_path):
    """无迭代上下文（iteration_count=0）的 specify 自环重跑同样放行（幂等，轮次仍为 0）。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import load_state, save_state

    root = _seed_manual_iteration_repo(tmp_path)
    state = load_state(root)
    state["stage"] = "specify"
    save_state(root, state)

    assert route("specify", "full", root, extra={"requirement": "重新生成"}) == 0

    state = load_state(root)
    assert state["stage"] == "specify"
    assert state["iteration_count"] == 0
    assert state["fallback_count"] == 0


# ---- 需求澄清登记（auto clarify，方案 docs/auto-clarification-plan.md）----

def test_auto_clarify_registers_ceiling_and_refresh(tmp_path):
    """clarify：ceiling 落盘 clarification 字段；重复调用为刷新（覆盖，非追加），rounds 不受影响。"""
    from specpowers_cli.bridge.dispatcher import route

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root, iteration_count=0, stage="ready")

    assert route("auto-clarify", "full", root, extra={
        "ceiling": "brainstorm",
        "report": ".specpowers/auto_clarifications/auto-feat.md",
    }) == 0
    base = _read_auto_base(root)
    clar = base["clarification"]
    assert clar["ceiling"] == "brainstorm"
    assert clar["report_path"] == ".specpowers/auto_clarifications/auto-feat.md"
    assert clar["checked_at"]
    assert len(base["rounds"]) == 1

    # 刷新语义：再次登记覆盖旧结论（迭代轮 ceiling 上调落盘凭据）
    assert route("auto-clarify", "full", root, extra={"ceiling": "full"}) == 0
    clar = _read_auto_base(root)["clarification"]
    assert clar["ceiling"] == "full"
    assert clar["report_path"] == ""


def test_auto_clarify_rejects_invalid_ceiling(tmp_path):
    """ceiling 非法值 → FatalError 拒绝且不落盘。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.errors import FatalError

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root)

    with pytest.raises(FatalError):
        route("auto-clarify", "full", root, extra={"ceiling": "specify"})
    assert "clarification" not in _read_auto_base(root)


def test_auto_clarify_requires_auto_base(tmp_path):
    """无 auto_base.json（第 0 步基点记录未执行）→ 拒绝登记（防声称澄清但无基线）。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.errors import StateError
    from specpowers_cli.bridge.core.fs_state import save_state, DEFAULT_STATE

    root = _create_temp_git_repo(tmp_path)
    state = dict(DEFAULT_STATE)
    state["stage"] = "build"
    state["feature"] = "plain-feat"
    save_state(root, state)

    with pytest.raises(StateError):
        route("auto-clarify", "full", root, extra={"ceiling": "full"})


def test_auto_status_resume_reports_pending_input_when_parked(tmp_path):
    """ceiling=brainstorm 停靠 + 无新输入重入 → resume + pending_input=True（契约层据此禁止盲续跑 specify）。"""
    from specpowers_cli.bridge.dispatcher import auto_status

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root, iteration_count=0, stage="brainstorm")
    base = _read_auto_base(root)
    base["clarification"] = {
        "ceiling": "brainstorm",
        "report_path": ".specpowers/auto_clarifications/auto-feat.md",
        "checked_at": "2026-01-01T00:00:00+00:00",
    }
    _write_auto_base(root, base)

    result = auto_status(root)
    assert result["mode"] == "resume"
    assert result["clarification"]["ceiling"] == "brainstorm"
    assert result["clarification"]["pending_input"] is True
    assert result["clarification"]["report_path"].endswith("auto-feat.md")


def test_auto_status_iterate_clears_pending_input(tmp_path):
    """停靠后带口头指令（方案结论）重入 → iterate + pending_input=False，ceiling 原值透传给契约层上调。"""
    from specpowers_cli.bridge.dispatcher import auto_status

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root, iteration_count=0, stage="brainstorm")
    base = _read_auto_base(root)
    base["clarification"] = {
        "ceiling": "brainstorm",
        "report_path": "",
        "checked_at": "2026-01-01T00:00:00+00:00",
    }
    _write_auto_base(root, base)

    result = auto_status(root, instruction="方案定为方案B，理由见讨论")
    assert result["mode"] == "iterate"
    assert result["clarification"]["ceiling"] == "brainstorm"
    assert result["clarification"]["pending_input"] is False


def test_auto_status_clarification_none_when_unregistered(tmp_path):
    """旧格式/未登记澄清（auto_base.json 无 clarification 字段）→ clarification=None（契约层补做全量澄清）。"""
    from specpowers_cli.bridge.dispatcher import auto_status

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root)

    result = auto_status(root, instruction="补充场景")
    assert result["mode"] == "iterate"
    assert result["clarification"] is None


def test_auto_clarify_via_facade_main(tmp_path):
    """facade main："auto clarify" 空格形式归一化为 auto-clarify；ceiling 非法值退出码 2。"""
    from specpowers_cli.bridge.facade import main

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root, iteration_count=0, stage="ready")

    assert main(["auto", "clarify", "--ceiling", "brainstorm", "--root", str(root)]) == 0
    assert _read_auto_base(root)["clarification"]["ceiling"] == "brainstorm"

    assert main(["auto", "clarify", "--ceiling", "bad", "--root", str(root)]) == 2
