"""多活跃需求（v2.8.0 schema 2）核心行为测试。

覆盖方案「状态分片映射 + 推导式前台 + slug 即身份」的确定性层行为：
- schema 1 → schema 2 迁移（活跃需求迁入 features 映射 / 空状态 / auto_base 搬移 / 幂等）
- 多需求并存（A apply 中开 B，A 分片不动、B 自动前台；slug 命中即续作）
- 推进类命令多活跃未指名拒绝（防错需求）与 --feature 显式路由
- switch 切前台 / 归档按需求终结（其余活跃不受影响、前台自动切换）
- reset 按需求放弃（多活跃强制指名）
- 粘滞锚点与 resume 探测多需求多行（前台标注、>3 截断、per-feature 解除）
- auto 三分判定/auto_base 按需求隔离（归档 B 不清 A 的基线与计数）

作者：005819 | 协作：GLM-5.3
"""

import json
import time
from pathlib import Path

import pytest

from specpowers_cli.bridge.core.errors import StateError, FatalError


def _create_temp_git_repo(tmp_path: Path) -> Path:
    """在 pytest tmp_path 下创建带提交的临时 git 仓库（会话级模板复制，约 10ms）。"""
    from tests._gitrepo import create_git_repo

    return create_git_repo(tmp_path / "multi-feat-repo")


def _init_project(root: Path) -> None:
    """初始化项目产物（constitution/baseline/state），模拟已 init 的 ready 态。"""
    from specpowers_cli.bridge.core.fs_state import init_state

    (root / ".specpowers").mkdir(exist_ok=True)
    (root / ".specpowers" / "constitution.md").write_text("# C", encoding="utf-8")
    (root / ".specpowers" / "baseline.json").write_text(
        '{"git_ref":"","top_dirs":[],"deps":{},"src_patterns":[]}', encoding="utf-8",
    )
    init_state(root)


def _seed_feature(root: Path, slug: str, stage: str = "apply", mode: str = "full",
                  iteration_count: int = 0, design_doc: str = "") -> None:
    """落盘一个活跃需求（视图 save → features 映射）。"""
    from specpowers_cli.bridge.core.fs_state import save_state

    state = {
        "stage": stage, "mode": mode, "feature": slug,
        "execution_mode": "", "iteration_count": iteration_count,
        "design_doc": design_doc,
    }
    save_state(root, state)
    # last_touched 微秒精度下连续 seed 可能同刻（tie-break 名字序会翻前台判定），
    # sleep 拉开保证「后 seed 者为前台」
    time.sleep(0.002)


def _read_raw(root: Path) -> dict:
    """读取顶层 state.json 原始内容（不经视图展开）。"""
    return json.loads(
        (root / ".specpowers" / "state.json").read_text(encoding="utf-8"),
    )


def _write_legacy_state(root: Path, feature: str, stage: str = "apply") -> None:
    """落盘一份 schema 1 扁平旧结构（v2.7.0 及以前形态，迁移用）。"""
    (root / ".specpowers").mkdir(exist_ok=True)
    (root / ".specpowers" / "state.json").write_text(json.dumps({
        "stage": stage,
        "mode": "full",
        "fallback_used": True,
        "fallback_count": 1,
        "feature": feature,
        "last_archive_ref": "abc123",
        "execution_mode": "conductor",
        "iteration_count": 2,
        "design_doc": "docs/design/x.md",
    }, ensure_ascii=False, indent=2), encoding="utf-8")


# ---- schema 1 → schema 2 迁移 ----

def test_migrate_schema1_active_feature(tmp_path):
    """schema 1 活跃需求 → features 映射（全局保留、需求级迁入、死字段清除）。"""
    from specpowers_cli.bridge.core.fs_state import load_state, list_features

    root = tmp_path
    _write_legacy_state(root, "legacy-feat", stage="apply")

    view = load_state(root)
    # 迁移即写盘：顶层变 schema 2
    raw = _read_raw(root)
    assert raw["schema"] == 2
    assert raw["fallback_count"] == 1
    assert raw["last_archive_ref"] == "abc123"
    assert "fallback_used" not in raw
    assert list_features(root) == ["legacy-feat"]
    # 视图：前台 = 迁移需求，字段完整展开
    assert view["feature"] == "legacy-feat"
    assert view["stage"] == "apply"
    assert view["iteration_count"] == 2
    assert view["execution_mode"] == "conductor"
    assert view["design_doc"] == "docs/design/x.md"


def test_migrate_schema1_empty_feature(tmp_path):
    """schema 1 空转态（feature 空）→ 顶层重写 schema 2 空映射。"""
    from specpowers_cli.bridge.core.fs_state import load_state

    root = tmp_path
    _write_legacy_state(root, "", stage="ready")

    view = load_state(root)
    raw = _read_raw(root)
    assert raw["schema"] == 2
    assert raw["features"] == {}
    assert view["feature"] == ""
    assert view["stage"] == "ready"


def test_migrate_schema1_moves_auto_base(tmp_path):
    """迁移时顶层 auto_base.json 原子搬入 auto_base/<slug>.json。"""
    from specpowers_cli.bridge.core.fs_state import load_state, auto_base_path

    root = tmp_path
    _write_legacy_state(root, "legacy-feat")
    legacy = root / ".specpowers" / "auto_base.json"
    legacy.write_text('{"base_commit": "aaa"}', encoding="utf-8")

    load_state(root)

    assert not legacy.exists()
    assert auto_base_path(root, "legacy-feat").exists()
    assert json.loads(auto_base_path(root, "legacy-feat").read_text(encoding="utf-8"))["base_commit"] == "aaa"


def test_migrate_is_idempotent(tmp_path):
    """迁移幂等：二次 load 不重复迁移、字段不漂移。"""
    from specpowers_cli.bridge.core.fs_state import load_state

    root = tmp_path
    _write_legacy_state(root, "legacy-feat", stage="propose")

    first = load_state(root)
    second = load_state(root)

    assert first == second
    assert _read_raw(root)["schema"] == 2


def test_load_state_unknown_feature_rejected(tmp_path):
    """load_state(feature=不活跃 slug) → FatalError（多活跃防错路由）。"""
    from specpowers_cli.bridge.core.fs_state import load_state

    root = tmp_path
    _init_project(root)
    _seed_feature(root, "feat-a", stage="apply")

    with pytest.raises(FatalError, match="不是活跃需求"):
        load_state(root, "feat-b")


# ---- 多需求并存与路由 ----

def test_second_explore_keeps_first_intact(tmp_path):
    """A apply 中开新需求 B：A 分片不动，B 自动成为前台。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import load_state, load_feature

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_feature(root, "feat-a", stage="apply", iteration_count=1, design_doc="docs/a.md")

    assert route("explore", root, {"requirement": "新需求", "feature": "feat-b"}) == 0

    # A 分片原样保留（多需求并存的根基）
    a = load_feature(root, "feat-a")
    assert a is not None
    assert a["stage"] == "apply"
    assert a["iteration_count"] == 1
    assert a["design_doc"] == "docs/a.md"
    # B 新需求：无污染（不继承 A 的 execution_mode/迭代轮/设计文档指针）
    b = load_feature(root, "feat-b")
    assert b is not None
    assert b["stage"] == "explore"
    assert b["execution_mode"] == ""
    assert b["iteration_count"] == 0
    assert b["design_doc"] == ""
    # 前台 = 最近操作者（B）
    assert load_state(root)["feature"] == "feat-b"


def test_explore_slug_hit_rejected_with_guidance(tmp_path):
    """explore 的 requirement normalize 命中活跃 slug → 续作语义拒绝（可执行指引）。"""
    from specpowers_cli.bridge.dispatcher import route

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_feature(root, "fix-typo", stage="apply")

    with pytest.raises(StateError, match="已在活跃集中"):
        route("explore", root, {"requirement": "fix typo"})


def test_propose_slug_hit_continues_existing(tmp_path):
    """propose 的 normalize 命中活跃 slug → 锁定为该需求续作（slug 即身份）。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import load_state, load_feature

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    doc = root / "docs" / "specpowers" / "design" / "a.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("# 设计", encoding="utf-8")
    _seed_feature(root, "feat-a", stage="explore", design_doc=str(doc))

    # requirement 措辞 normalize 后仍是 feat-a → 续作而非新需求
    assert route("propose", root, {"requirement": "feat-a"}) == 0

    assert load_feature(root, "feat-a")["stage"] == "propose"
    assert load_state(root)["feature"] == "feat-a"
    from specpowers_cli.bridge.core.fs_state import list_features
    assert list_features(root) == ["feat-a"]


def test_advance_command_rejected_when_multi_active_unnamed(tmp_path):
    """多活跃 + 推进类命令（apply）未指名 → 拒绝并列出活跃需求与阶段。"""
    from specpowers_cli.bridge.dispatcher import route

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_feature(root, "feat-a", stage="propose")
    _seed_feature(root, "feat-b", stage="propose")

    with pytest.raises(StateError, match="--feature") as exc_info:
        route("apply", root, {})
    # 报错必须把活跃清单递给模型（带名重试的依据）
    assert "feat-a" in str(exc_info.value)
    assert "feat-b" in str(exc_info.value)


def test_advance_command_explicit_feature_routes_background(tmp_path):
    """多活跃 + apply --feature B（后台需求）→ 路由正确且 A 分片不动。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import load_state, load_feature

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_feature(root, "feat-a", stage="apply")
    _seed_feature(root, "feat-b", stage="propose")
    # B 的 propose 产物（apply 前置校验需要）
    proposal = root / "openspec" / "changes" / "feat-b" / "proposal.md"
    proposal.parent.mkdir(parents=True, exist_ok=True)
    proposal.write_text("## 数据流契约\n- 无", encoding="utf-8")
    tasks = root / "openspec" / "changes" / "feat-b" / "tasks.md"
    tasks.write_text("# t", encoding="utf-8")
    specs = root / "openspec" / "changes" / "feat-b" / "specs" / "feat-b"
    specs.mkdir(parents=True, exist_ok=True)
    (specs / "spec.md").write_text("# spec", encoding="utf-8")

    assert route("apply", root, {"feature": "feat-b"}) == 0

    assert load_feature(root, "feat-b")["stage"] == "apply"
    assert load_feature(root, "feat-a")["stage"] == "apply"
    # 操作即前台：B
    assert load_state(root)["feature"] == "feat-b"


def test_advance_command_unknown_feature_rejected(tmp_path):
    """--feature 指定不活跃 slug → 拒绝并给出活跃清单。"""
    from specpowers_cli.bridge.dispatcher import route

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_feature(root, "feat-a", stage="propose")

    with pytest.raises(StateError, match="不是活跃需求"):
        route("apply", root, {"feature": "ghost"})


def test_switch_touches_foreground(tmp_path):
    """switch 切前台（touch last_touched）；不活跃目标拒绝。"""
    from specpowers_cli.bridge.core.fs_state import foreground_feature, touch_feature
    from specpowers_cli.bridge.facade import main

    root = tmp_path
    _init_project(root)
    _seed_feature(root, "feat-a", stage="apply")
    _seed_feature(root, "feat-b", stage="propose")
    assert foreground_feature(root) == "feat-b"

    assert main(["switch", "feat-a", "--root", str(root)]) == 0
    assert foreground_feature(root) == "feat-a"

    with pytest.raises(FatalError, match="不是活跃需求"):
        touch_feature(root, "ghost")


# ---- 归档按需求终结 ----

def _mock_openspec_archive(monkeypatch):
    """屏蔽真实 openspec 归档（返回成功结果）。"""
    import specpowers_cli.bridge.modules.archive_auditor as archive_auditor

    monkeypatch.setattr(
        archive_auditor, "prepare_openspec_archive",
        lambda root, feature, state, skip_validation=False: {
            "archivedAs": feature, "specsUpdated": False,
        },
    )


def _seed_archive_ready_feature(root: Path, slug: str) -> None:
    """构造 apply 态需求 + archive 前置产物（spec 目录 + tasks）。"""
    _seed_feature(root, slug, stage="apply")
    spec_dir = root / "openspec" / "changes" / slug / "specs" / slug
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(
        "## ADDED Requirements\n\n### Requirement: " + slug +
        "\nThe system SHALL work.\n\n#### Scenario: s1\n- **WHEN** x\n- **THEN** y\n",
        encoding="utf-8",
    )
    (root / "openspec" / "changes" / slug / "tasks.md").write_text("# t", encoding="utf-8")


def test_archive_one_feature_keeps_others(tmp_path, monkeypatch):
    """归档 B：B 需求终结（映射移除 + auto_base 清理），A 不受影响且自动回前台。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import (
        load_state, load_feature, list_features, foreground_feature, auto_base_path,
    )

    _mock_openspec_archive(monkeypatch)
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_archive_ready_feature(root, "feat-a")
    _seed_archive_ready_feature(root, "feat-b")
    # 两个需求各有 auto_base（按 slug 隔离）
    auto_base_path(root, "feat-a").parent.mkdir(parents=True, exist_ok=True)
    auto_base_path(root, "feat-a").write_text('{"base_commit": "a"}', encoding="utf-8")
    auto_base_path(root, "feat-b").write_text('{"base_commit": "b"}', encoding="utf-8")

    assert route("archive", root, {"feature": "feat-b"}) == 0

    assert list_features(root) == ["feat-a"]
    assert load_feature(root, "feat-a")["stage"] == "apply"
    # 前台自动切到剩余 last_touched 最大者（A），无需显式切换
    assert foreground_feature(root) == "feat-a"
    assert load_state(root)["feature"] == "feat-a"
    # B 的 auto_base 随需求清理；A 的保留（多需求基线互不串扰）
    assert not auto_base_path(root, "feat-b").exists()
    assert auto_base_path(root, "feat-a").exists()


def test_archive_iteration_count_not_leaked(tmp_path, monkeypatch):
    """归档 B 后 A 的迭代轮保留（per-feature 清零语义：B 的计数随分片删除）。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import load_feature

    _mock_openspec_archive(monkeypatch)
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_feature(root, "feat-a", stage="apply", iteration_count=3)
    _seed_archive_ready_feature(root, "feat-b")

    assert route("archive", root, {"feature": "feat-b"}) == 0

    assert load_feature(root, "feat-a")["iteration_count"] == 3


# ---- reset 按需求放弃 ----

def test_reset_multi_active_requires_feature(tmp_path):
    """多活跃 + reset 未指名 → 拒绝（防误清全部）。"""
    from specpowers_cli.bridge.dispatcher import route

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_feature(root, "feat-a", stage="apply")
    _seed_feature(root, "feat-b", stage="propose")

    with pytest.raises(StateError, match="--feature"):
        route("reset", root, {})


def test_reset_feature_abandons_only_target(tmp_path):
    """reset --feature B：仅 B 终结，A 保留且自动前台。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import list_features, foreground_feature, load_state

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_feature(root, "feat-a", stage="apply")
    _seed_feature(root, "feat-b", stage="propose")

    assert route("reset", root, {"feature": "feat-b"}) == 0

    assert list_features(root) == ["feat-a"]
    assert foreground_feature(root) == "feat-a"
    assert load_state(root)["feature"] == "feat-a"


def test_reset_unknown_feature_rejected(tmp_path):
    """reset --feature 指向不活跃 slug → 拒绝并列出活跃清单。"""
    from specpowers_cli.bridge.dispatcher import route

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_feature(root, "feat-a", stage="apply")

    with pytest.raises(StateError, match="不是活跃需求"):
        route("reset", root, {"feature": "ghost"})


# ---- 粘滞锚点与 resume 探测多需求 ----

def test_sticky_note_multi_feature_lines(tmp_path):
    """多需求粘滞：每需求一行、前台标注、前台排首行。"""
    from specpowers_cli.bridge.modules.resume_probe import sticky_note

    root = tmp_path
    _init_project(root)
    _seed_feature(root, "feat-a", stage="apply")
    _seed_feature(root, "feat-b", stage="propose")

    msg = sticky_note(root)
    lines = msg.splitlines()
    assert len(lines) == 2
    # 前台（feat-b，最近 seed）排首行且带标注
    assert lines[0].startswith("活跃需求 feat-b（前台）")
    assert lines[1].startswith("活跃需求 feat-a（")
    # 每行锚点含各自的解除指引（per-feature 粒度）
    assert "/specpowers-archive --feature feat-b" in lines[0]
    assert "/specpowers-reset --feature feat-a" in lines[1]


def test_sticky_note_truncates_beyond_three(tmp_path):
    """>3 个活跃需求：前台 + 2 行后台 + 1 行汇总（控 token）。"""
    from specpowers_cli.bridge.modules.resume_probe import sticky_note

    root = tmp_path
    _init_project(root)
    for slug in ("feat-a", "feat-b", "feat-c", "feat-d"):
        _seed_feature(root, slug, stage="apply")

    msg = sticky_note(root)
    lines = msg.splitlines()
    assert len(lines) == 4
    assert lines[0].startswith("活跃需求 feat-d（前台）")
    assert lines[3].startswith("另有 1 个后台活跃需求：feat-c")
    assert "--feature" in lines[3]


def test_sticky_note_per_feature_release(tmp_path, monkeypatch):
    """归档 B 后 A 的锚点仍在（粘滞解除是 per-feature 的）。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.modules.resume_probe import sticky_note
    from specpowers_cli.bridge.core.fs_state import load_state

    _mock_openspec_archive(monkeypatch)
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_archive_ready_feature(root, "feat-a")
    _seed_archive_ready_feature(root, "feat-b")

    assert route("archive", root, {"feature": "feat-b"}) == 0

    msg = sticky_note(root)
    assert "feat-a" in msg
    assert "feat-b" not in msg
    # A 自动回前台
    assert load_state(root)["feature"] == "feat-a"


def test_probe_resume_multi_feature(tmp_path):
    """probe 多需求：每需求一行续跑指引，前台标注。"""
    from specpowers_cli.bridge.modules.resume_probe import probe_resume

    root = tmp_path
    _init_project(root)
    _seed_feature(root, "feat-a", stage="apply")
    _seed_feature(root, "feat-b", stage="explore")

    msg = probe_resume(root)
    assert "feat-a" in msg
    assert "feat-b" in msg
    assert "（前台）" in msg
    assert msg.splitlines()[0].startswith("📌 检测到未完成的特性流水线：feat-b（前台）")


# ---- auto 按需求隔离 ----

def test_auto_status_targets_background_feature(tmp_path):
    """auto_status --feature 指定后台需求：按其分片与 auto_base 判定。"""
    from specpowers_cli.bridge.dispatcher import auto_status
    from specpowers_cli.bridge.core.fs_state import auto_base_path

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_feature(root, "feat-a", stage="apply", iteration_count=1)
    _seed_feature(root, "feat-b", stage="apply", iteration_count=0)
    base = auto_base_path(root, "feat-b")
    base.parent.mkdir(parents=True, exist_ok=True)
    base.write_text(json.dumps({
        "base_commit": "x", "feature": "feat-b", "design_doc": "",
        "design_doc_hash": "", "rounds": [],
    }), encoding="utf-8")

    result = auto_status(root)
    # 未指名 → 前台（feat-b），resume
    assert result["mode"] == "resume"
    assert result["feature"] == "feat-b"

    # 显式指定后台 A（无 auto_base）→ iterate + auto_base_missing
    result = auto_status(root, feature="feat-a")
    assert result["mode"] == "iterate"
    assert result["feature"] == "feat-a"
    assert result["auto_base_missing"] is True


def test_auto_status_unknown_feature_rejected(tmp_path):
    """auto_status 显式指定不活跃 slug → 报错（防误判 fresh）。"""
    from specpowers_cli.bridge.dispatcher import auto_status

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_feature(root, "feat-a", stage="apply")

    with pytest.raises(StateError, match="不是活跃需求"):
        auto_status(root, feature="ghost")


# ---- facade status / record-execution-mode 多需求 ----

def test_facade_status_reports_features_overview(tmp_path, capsys):
    """facade status：顶层平铺前台字段 + features 概览 + foreground 键。"""
    from specpowers_cli.bridge.facade import main

    root = tmp_path
    _init_project(root)
    _seed_feature(root, "feat-a", stage="apply", iteration_count=2)
    _seed_feature(root, "feat-b", stage="propose")

    assert main(["status", "--root", str(root)]) == 0
    out = json.loads(capsys.readouterr().out)
    # 顶层平铺（旧消费者兼容：前台需求展开）
    assert out["feature"] == "feat-b"
    assert out["stage"] == "propose"
    assert out["schema"] == 2
    # 概览键（新增信息只增不改）
    assert out["features"]["feat-a"] == {"stage": "apply", "mode": "full", "iteration_count": 2}
    assert out["features"]["feat-b"]["stage"] == "propose"
    assert out["foreground"] == "feat-b"


def test_record_execution_mode_feature_targeting(tmp_path, capsys):
    """record-execution-mode --feature B：写入 B 分片，A 不受影响。"""
    from specpowers_cli.bridge.facade import main
    from specpowers_cli.bridge.core.fs_state import load_feature

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_feature(root, "feat-a", stage="apply")
    _seed_feature(root, "feat-b", stage="apply")

    assert main(["record-execution-mode", "tdd", "--feature", "feat-b", "--root", str(root)]) == 0

    assert load_feature(root, "feat-b")["execution_mode"] == "tdd"
    assert load_feature(root, "feat-a")["execution_mode"] == ""


def test_record_execution_mode_multi_active_requires_feature(tmp_path):
    """多活跃 + record-execution-mode 未指名 → 非 0 退出并提示 --feature。"""
    from specpowers_cli.bridge.facade import main

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_feature(root, "feat-a", stage="apply")
    _seed_feature(root, "feat-b", stage="apply")

    rc = main(["record-execution-mode", "tdd", "--root", str(root)])
    assert rc != 0
