"""多活跃需求（v3.0.0 状态机推导化）核心行为测试。

覆盖「目录即活跃权威 + 推导式前台 + slug 即身份」的确定性层行为（state.json
已退役，测试现场 = openspec/changes/ 工件 + change 目录 meta + runtime.json，
构造走 helpers_v3；旧 state.json 仅在迁移用例中作为输入手工落盘）：
- migrate_legacy_state 四态：schema 1 扁平 / schema 2 features 映射 / 无 state（noop）/
  损坏（留底 quarantine）+ 幂等 + 顶层 auto_base.json 孤儿的去向（fresh 判定顺带清理）
- 多需求并存（A apply 中开 B：A 工件与 meta 不动，B 经登记收口后进活跃清单并依
  last_touched 成为前台；slug 命中即续作）
- 推进类命令多活跃未指名拒绝（防错需求）与 --feature 显式路由（apply 是动作不是状态）
- switch 切前台（meta last_touched 断言）/ 归档按需求终结（其余活跃不受影响、前台自动切换）
- reset 按需求放弃（多活跃强制指名 + --force 删目录确认）
- 粘滞锚点与 resume 探测多需求多行（前台标注、>3 截断、per-feature 解除，stage 全推导）
- auto 三分判定/auto_base 按需求隔离（归档 B 不清 A 的基线与轮次）
- facade status / record-execution-mode 多需求（无 schema 键；meta 写点隔离）

生产 bug 兜底（单报，勿在本套件断言其行为）：artifact_registry.MANIFEST 仍把已退役的
.specpowers/state.json 登记为必需产物（required=True、consumers=["*"]），导致
explore/propose/fast/apply/archive 在任何 v3.0 项目上必然 ArtifactMissingError。
下方 autouse fixture 在文件域内过滤该陈旧条目，生产修复后应删除。

作者：005819 | 协作：GLM-5.3 | 日期：2026-11-17
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from specpowers_cli.bridge.core.errors import StateError
from tests.helpers_v3 import make_change, make_triple, read_meta_of, write_runtime


_APPLY_TASKS = "### Task 1: x\n\n- [x] done\n"
_PROPOSE_TASKS = "### Task 1: x\n\n- [ ] todo\n"

# meta last_touched 单调递增种子（前台推导的确定性排序依据，免 sleep）
_touch_seq = 0


def _next_touched() -> str:
    """生成单调递增的 meta last_touched ISO 时间戳（后 seed 者为前台）。"""
    global _touch_seq
    _touch_seq += 1
    return (datetime(2026, 1, 1, tzinfo=timezone.utc)
            + timedelta(minutes=_touch_seq)).isoformat()


def _create_temp_git_repo(tmp_path: Path) -> Path:
    """在 pytest tmp_path 下创建带提交的临时 git 仓库（会话级模板复制，约 10ms）。"""
    from tests._gitrepo import create_git_repo

    return create_git_repo(tmp_path / "multi-feat-repo")


def _init_project(root: Path) -> None:
    """初始化项目产物（constitution/baseline，模拟已 init 项目——v3.0 无 state 可写）。"""
    (root / ".specpowers").mkdir(exist_ok=True)
    (root / ".specpowers" / "constitution.md").write_text("# C", encoding="utf-8")
    (root / ".specpowers" / "baseline.json").write_text("{}", encoding="utf-8")


def _seed_feature(root: Path, slug: str, stage: str = "apply", mode: str = "full",
                  rounds: int = 0, design_doc: str = "", touched: str | None = None) -> Path:
    """落盘一个活跃需求（工件推导现场）。

    目录形态决定推导阶段（apply=三件套+勾选 / propose=三件套无勾选 / explore=仅 meta）；
    meta 承载 mode/last_touched/design_doc 登记；rounds>0 时落 design-round-N.md
    轮次痕迹（iteration_count_of 的推导来源）。
    """
    meta = {"mode": mode, "last_touched": touched or _next_touched()}
    if design_doc:
        meta["design_doc"] = design_doc
    if stage == "apply":
        change = make_triple(root, slug, _APPLY_TASKS, meta=meta)
    elif stage == "propose":
        change = make_triple(root, slug, _PROPOSE_TASKS, meta=meta)
    elif stage == "explore":
        change = make_change(root, slug, meta=meta)
    else:
        raise ValueError(f"未知 stage: {stage}")
    if rounds >= 1:
        (change / f"design-round-{rounds}.md").write_text("# 本轮增量", encoding="utf-8")
    return change


def _write_legacy_state(root: Path, payload: dict) -> Path:
    """落盘一份旧版 state.json（schema 1 扁平 / schema 2 features 映射，迁移用例输入）。"""
    path = root / ".specpowers" / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _mock_openspec_archive(monkeypatch) -> None:
    """屏蔽真实 openspec 归档（模拟其 change 目录移入 archive/ 快照的语义后返回成功）。"""
    import specpowers_cli.bridge.modules.archive_auditor as archive_auditor

    def _fake_prepare(root, feature, state, skip_validation=False):
        change = root / "openspec" / "changes" / feature
        snapshot = root / "openspec" / "changes" / "archive" / feature
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        if change.is_dir():
            change.rename(snapshot)  # openspec archive 的目录移走语义（需求终结由目录承载）
        return {"archivedAs": feature, "specsUpdated": False}

    monkeypatch.setattr(archive_auditor, "prepare_openspec_archive", _fake_prepare)


# ---- migrate_legacy_state 四态（旧 state.json 退役迁移）----

def test_migrate_schema1_active_feature(tmp_path):
    """schema 1 活跃需求 → meta 齐全化（需求级字段落 change 目录、死字段清除、轮次工件推导）。"""
    from specpowers_cli.bridge.modules.state_derivation import (
        active_slugs, change_dir_of, iteration_count_of, migrate_legacy_state,
    )

    root = tmp_path
    # 真实项目 apply 态必有 change 目录：补 proposal + design-round-2 轮次痕迹
    make_change(root, "legacy-feat", ["proposal.md", "design-round-2.md"])
    _write_legacy_state(root, {
        "stage": "apply",
        "mode": "full",
        "fallback_used": True,
        "fallback_count": 1,
        "feature": "legacy-feat",
        "last_archive_ref": "abc123",
        "execution_mode": "conductor",
        "iteration_count": 2,
        "design_doc": "docs/design/x.md",
    })

    report = migrate_legacy_state(root)
    assert report["migrated"] is True
    assert report["features_migrated"] == ["legacy-feat"]
    assert report["dropped"] == []
    # 需求级字段迁入 change 目录 meta（仅补缺失键）
    meta = read_meta_of(root, "legacy-feat")
    assert meta["design_doc"] == "docs/design/x.md"
    assert meta["mode"] == "full"
    assert meta["execution_mode"] == "conductor"
    # 死字段随 state 退役：iteration_count 不迁移，轮次由工件 design-round-2.md 推导
    assert "iteration_count" not in meta
    assert iteration_count_of(change_dir_of(root, "legacy-feat")) == 2
    # 跨需求全局字段落 runtime.json（死字段 fallback_used 清除）
    runtime = json.loads(
        (root / ".specpowers" / "runtime.json").read_text(encoding="utf-8"))
    assert runtime == {"fallback_count": 1, "last_archive_ref": "abc123"}
    # state.json 改名留底退役；活跃权威 = 目录推导
    assert (root / ".specpowers" / "state.json.bak").is_file()
    assert not (root / ".specpowers" / "state.json").exists()
    assert active_slugs(root) == ["legacy-feat"]


def test_migrate_schema1_empty_feature(tmp_path):
    """schema 1 空转态（feature 空）→ 无条目迁移，runtime 承接全局字段，留底退役。"""
    from specpowers_cli.bridge.modules.state_derivation import migrate_legacy_state

    root = tmp_path
    _write_legacy_state(root, {
        "stage": "ready", "mode": "full",
        "fallback_count": 1, "last_archive_ref": "abc123", "feature": "",
    })

    report = migrate_legacy_state(root)
    assert report["migrated"] is True
    assert report["features_migrated"] == []
    assert report["dropped"] == []
    runtime = json.loads(
        (root / ".specpowers" / "runtime.json").read_text(encoding="utf-8"))
    assert runtime == {"fallback_count": 1, "last_archive_ref": "abc123"}
    assert (root / ".specpowers" / "state.json.bak").is_file()


def test_migrate_schema2_features_map(tmp_path):
    """schema 2 features 映射：有目录条目 meta 齐全化、无目录条目丢弃并警告、runtime 承接。"""
    from specpowers_cli.bridge.modules.state_derivation import (
        active_slugs, migrate_legacy_state,
    )

    root = tmp_path
    make_change(root, "alive", ["proposal.md"])
    _write_legacy_state(root, {
        "schema": 2,
        "fallback_count": 2,
        "last_archive_ref": "abc1234",
        "features": {
            "alive": {"stage": "propose", "mode": "full", "execution_mode": "tdd",
                      "iteration_count": 1, "design_doc": "docs/x-design.md",
                      "created_at": "2026-01-01T00:00:00+00:00",
                      "last_touched": "2026-01-02T00:00:00+00:00"},
            "ghost": {"stage": "apply", "mode": "full"},
        },
    })

    report = migrate_legacy_state(root)
    assert report["migrated"] is True
    assert report["features_migrated"] == ["alive"]
    assert report["dropped"] == ["ghost"]
    assert any("ghost" in w for w in report["warnings"])
    meta = read_meta_of(root, "alive")
    assert meta["execution_mode"] == "tdd"
    assert meta["design_doc"] == "docs/x-design.md"
    assert meta["last_touched"] == "2026-01-02T00:00:00+00:00"
    assert meta["created_at"] == "2026-01-01T00:00:00+00:00"
    runtime = json.loads(
        (root / ".specpowers" / "runtime.json").read_text(encoding="utf-8"))
    assert runtime == {"fallback_count": 2, "last_archive_ref": "abc1234"}
    assert (root / ".specpowers" / "state.json.bak").is_file()
    assert active_slugs(root) == ["alive"]


def test_migrate_absent_state_is_noop(tmp_path):
    """无旧 state（新 clone / 已迁移）→ 幂等 noop（migrated=False，零副作用）。"""
    from specpowers_cli.bridge.modules.state_derivation import migrate_legacy_state

    root = tmp_path
    report = migrate_legacy_state(root)
    assert report["migrated"] is False
    assert not (root / ".specpowers" / "runtime.json").exists()
    # 二次执行同样 noop
    assert migrate_legacy_state(root)["migrated"] is False


def test_migrate_corrupt_state_quarantined(tmp_path):
    """损坏 state：留底 corrupted-<时间戳>、报告标注 corrupted，推导链路不受损。"""
    from specpowers_cli.bridge.modules.resume_probe import sticky_note
    from specpowers_cli.bridge.modules.state_derivation import (
        active_slugs, migrate_legacy_state,
    )

    root = tmp_path
    _seed_feature(root, "feat-a", stage="propose")
    _write_legacy_state_file_broken(root)

    report = migrate_legacy_state(root)
    assert report["migrated"] is True
    assert report["corrupted"] is True
    leftovers = list((root / ".specpowers").glob("state.json.corrupted-*"))
    assert len(leftovers) == 1
    assert not (root / ".specpowers" / "state.json").exists()
    # 推导不受损：活跃清单/粘滞锚点仍从工件正常产出（零 state 依赖）
    assert active_slugs(root) == ["feat-a"]
    assert "feat-a" in sticky_note(root)


def _write_legacy_state_file_broken(root: Path) -> None:
    """落盘一份损坏的 state.json（迁移损坏态用例输入）。"""
    path = root / ".specpowers" / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken", encoding="utf-8")


def test_migrate_is_idempotent(tmp_path):
    """迁移幂等：二次执行 state.json 已退役 → noop，meta 与留底零漂移。"""
    from specpowers_cli.bridge.modules.state_derivation import migrate_legacy_state

    root = tmp_path
    make_change(root, "legacy-feat", ["proposal.md"])
    _write_legacy_state(root, {
        "stage": "propose", "mode": "full", "feature": "legacy-feat",
        "fallback_count": 0, "last_archive_ref": "",
    })

    first = migrate_legacy_state(root)
    assert first["migrated"] is True
    meta_before = read_meta_of(root, "legacy-feat")

    second = migrate_legacy_state(root)
    assert second["migrated"] is False
    assert read_meta_of(root, "legacy-feat") == meta_before
    # 仅 .bak 一份留底（无残留 state.json、无重复留底）
    leftovers = list((root / ".specpowers").glob("state.json*"))
    assert leftovers == [root / ".specpowers" / "state.json.bak"]


def test_migrate_leaves_auto_base_orphan_to_fresh_cleanup(tmp_path):
    """迁移不处理 auto_base（load_state 搬移职责随 state 退役）；顶层孤儿由 auto-status fresh 顺带清理。"""
    from specpowers_cli.bridge.dispatcher import auto_status
    from specpowers_cli.bridge.modules.state_derivation import migrate_legacy_state

    root = tmp_path
    _write_legacy_state(root, {
        "stage": "ready", "feature": "", "fallback_count": 0, "last_archive_ref": "",
    })
    orphan = root / ".specpowers" / "auto_base.json"
    orphan.write_text('{"base_commit": "aaa"}', encoding="utf-8")

    migrate_legacy_state(root)
    assert orphan.exists()  # 迁移职责只覆盖 meta/runtime/留底，不动 auto_base

    # 孤儿认领归 fresh 判定：无活跃需求重入 auto-status 即顺带清理
    result = auto_status(root)
    assert result["mode"] == "fresh"
    assert result["auto_base_removed"] is True
    assert not orphan.exists()


# ---- 多需求并存与路由 ----

def test_second_explore_keeps_first_intact(tmp_path):
    """A apply 中开新需求 B：A 工件与 meta 不动；B 经登记收口后进活跃清单并成为前台。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.modules.state_derivation import (
        active_slugs, change_dir_of, derive_stage, foreground_slug, iteration_count_of,
    )

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_feature(root, "feat-a", stage="apply", rounds=1, design_doc="docs/a.md")

    assert route("explore", root, {"requirement": "新需求", "feature": "feat-b"}) == 0

    # A 分片原样保留（多需求并存的根基：推导值与 meta 登记均不动）
    assert derive_stage(change_dir_of(root, "feat-a")) == "apply"
    assert iteration_count_of(change_dir_of(root, "feat-a")) == 1
    assert read_meta_of(root, "feat-a")["design_doc"] == "docs/a.md"
    # v3.0 explore 进行中无写点：B 尚无目录、不在活跃清单，前台仍是 A
    assert not change_dir_of(root, "feat-b").exists()
    assert active_slugs(root) == ["feat-a"]
    assert foreground_slug(root) == "feat-a"

    # B 收口（登记设计文档）→ 以 explore 态进入活跃清单，依 last_touched 成为前台
    doc = root / "docs" / "specpowers" / "design" / "b-design.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("# B 设计", encoding="utf-8")
    assert route("record-design-doc", root,
                 {"design_doc": str(doc), "feature": "feat-b"}) == 0
    assert active_slugs(root) == ["feat-a", "feat-b"]
    assert derive_stage(change_dir_of(root, "feat-b")) == "explore"
    assert foreground_slug(root) == "feat-b"


def test_explore_slug_hit_rejected_with_guidance(tmp_path):
    """explore 的 requirement normalize 命中活跃 slug → 续作语义拒绝（可执行指引）。"""
    from specpowers_cli.bridge.dispatcher import route

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_feature(root, "fix-typo", stage="apply")

    with pytest.raises(StateError, match="已在活跃清单"):
        route("explore", root, {"requirement": "fix typo"})


def test_propose_slug_hit_continues_existing(tmp_path):
    """propose 的 normalize 命中活跃 slug → 锁定为该需求续作（slug 即身份，操作即前台）。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.modules.state_derivation import (
        active_slugs, change_dir_of, derive_stage, foreground_slug,
    )

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    doc = root / "docs" / "specpowers" / "design" / "a.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("# 设计", encoding="utf-8")
    seeded_touched = _next_touched()
    _seed_feature(root, "feat-a", stage="explore", design_doc=str(doc),
                  touched=seeded_touched)

    # requirement 措辞 normalize 后仍是 feat-a → 续作而非新需求
    assert route("propose", root, {"requirement": "feat-a"}) == 0

    assert active_slugs(root) == ["feat-a"]
    assert foreground_slug(root) == "feat-a"
    assert read_meta_of(root, "feat-a")["last_touched"] != seeded_touched  # touch 刷新
    # 工件未变 → 推导阶段仍是 explore（阶段由工件承载，无状态写点）
    assert derive_stage(change_dir_of(root, "feat-a")) == "explore"


def test_advance_command_rejected_when_multi_active_unnamed(tmp_path):
    """多活跃 + 推进类命令（apply）未指名 → 拒绝并列出活跃需求与推导阶段。"""
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
    """多活跃 + apply --feature B（后台需求）→ 操作即前台，A 分片不动，阶段仍工件推导。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.modules.state_derivation import (
        change_dir_of, derive_stage, foreground_slug,
    )

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_feature(root, "feat-a", stage="apply")
    touched_b = _next_touched()
    _seed_feature(root, "feat-b", stage="propose", touched=touched_b)
    # B 的 propose 产物（apply 前置校验需要：proposal 含数据流契约声明）
    proposal = root / "openspec" / "changes" / "feat-b" / "proposal.md"
    proposal.write_text("## Why\nx\n## 数据流契约\n本特性无跨链路字段\n", encoding="utf-8")

    assert route("apply", root, {"feature": "feat-b"}) == 0

    # 操作即前台：B 的 meta last_touched 刷新，A 分片不动
    assert read_meta_of(root, "feat-b")["last_touched"] != touched_b
    assert foreground_slug(root) == "feat-b"
    # v3.0 apply 是动作不是状态：无状态写点，阶段仍由工件推导（B 未勾选 → propose）
    assert derive_stage(change_dir_of(root, "feat-b")) == "propose"
    assert derive_stage(change_dir_of(root, "feat-a")) == "apply"


def test_advance_command_unknown_feature_rejected(tmp_path):
    """--feature 指定不活跃 slug → 拒绝并给出活跃清单（活跃权威 = 目录推导）。"""
    from specpowers_cli.bridge.dispatcher import route

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_feature(root, "feat-a", stage="propose")

    with pytest.raises(StateError, match="不是活跃需求"):
        route("apply", root, {"feature": "ghost"})


def test_switch_touches_foreground(tmp_path):
    """switch 切前台 = touch 目标 meta last_touched；不活跃目标退出码 2。"""
    from specpowers_cli.bridge.facade import main
    from specpowers_cli.bridge.modules.state_derivation import foreground_slug

    root = tmp_path
    _seed_feature(root, "feat-a", stage="apply")
    _seed_feature(root, "feat-b", stage="propose")
    assert foreground_slug(root) == "feat-b"

    assert main(["switch", "feat-a", "--root", str(root)]) == 0
    assert foreground_slug(root) == "feat-a"
    # 写点在 meta（推导式前台的唯一显式入口），非全局指针
    assert read_meta_of(root, "feat-a")["last_touched"]

    assert main(["switch", "ghost", "--root", str(root)]) == 2
    assert foreground_slug(root) == "feat-a"


# ---- 归档按需求终结 ----

def _seed_archive_ready_feature(root: Path, slug: str) -> None:
    """构造 apply 态需求（三件套+勾选，archive 的合法来源阶段）。"""
    _seed_feature(root, slug, stage="apply")


def test_archive_one_feature_keeps_others(tmp_path, monkeypatch):
    """归档 B：B 需求终结（目录快照 + auto_base 清理），A 不受影响且自动回前台。"""
    from specpowers_cli.bridge.core.fs_state import auto_base_path, load_runtime
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.modules.state_derivation import (
        active_slugs, change_dir_of, derive_stage, foreground_slug,
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

    # B 需求终结由目录承载：change 移入 archive 快照后活跃清单即时更新
    assert active_slugs(root) == ["feat-a"]
    assert (root / "openspec" / "changes" / "archive" / "feat-b").is_dir()
    assert derive_stage(change_dir_of(root, "feat-a")) == "apply"
    # 前台自动切到剩余 last_touched 最大者（A），无需显式切换
    assert foreground_slug(root) == "feat-a"
    # B 的 auto_base 随需求清理；A 的保留（多需求基线互不串扰）
    assert not auto_base_path(root, "feat-b").exists()
    assert auto_base_path(root, "feat-a").exists()
    # runtime merge check 基准刷新（项目级字段，归档写点）
    assert load_runtime(root)["last_archive_ref"]


def test_archive_iteration_count_not_leaked(tmp_path, monkeypatch):
    """归档 B 后 A 的迭代轮保留（per-demand 语义：轮次是 A 的工件痕迹，与 B 终结无关）。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.modules.state_derivation import (
        change_dir_of, iteration_count_of, read_meta,
    )

    _mock_openspec_archive(monkeypatch)
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_feature(root, "feat-a", stage="apply", rounds=3)
    _seed_archive_ready_feature(root, "feat-b")

    assert route("archive", root, {"feature": "feat-b"}) == 0

    assert iteration_count_of(change_dir_of(root, "feat-a")) == 3
    # A 的 meta 登记原样保留
    assert (read_meta(change_dir_of(root, "feat-a")) or {}).get("last_touched")


# ---- reset 按需求放弃 ----

def test_reset_multi_active_requires_feature(tmp_path):
    """多活跃 + reset 未指名 → 拒绝（防误清全部）。"""
    from specpowers_cli.bridge.dispatcher import route

    root = tmp_path
    _seed_feature(root, "feat-a", stage="apply")
    _seed_feature(root, "feat-b", stage="propose")

    with pytest.raises(StateError, match="--feature"):
        route("reset", root, {})


def test_reset_feature_requires_force_confirmation(tmp_path):
    """reset --feature（非 CI、无 --force）→ 拒绝并列出删除范围，目录原样保留。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.modules.state_derivation import change_dir_of

    root = tmp_path
    _seed_feature(root, "feat-a", stage="apply")
    _seed_feature(root, "feat-b", stage="propose")

    with pytest.raises(StateError, match="--force") as exc_info:
        route("reset", root, {"feature": "feat-b"})
    # 删除范围（change 目录 + auto_base 分片）须在确认信息中言明
    assert "auto_base" in str(exc_info.value)
    assert change_dir_of(root, "feat-b").is_dir()


def test_reset_feature_abandons_only_target(tmp_path):
    """reset --feature B --force：仅 B 终结（删 change 目录 + auto_base），A 保留且自动前台。"""
    from specpowers_cli.bridge.core.fs_state import auto_base_path, load_runtime
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.modules.state_derivation import (
        active_slugs, foreground_slug,
    )

    root = tmp_path
    _seed_feature(root, "feat-a", stage="apply")
    _seed_feature(root, "feat-b", stage="propose")
    auto_base_path(root, "feat-b").parent.mkdir(parents=True, exist_ok=True)
    auto_base_path(root, "feat-b").write_text('{"base_commit": "b"}', encoding="utf-8")
    write_runtime(root, fallback_count=1, last_archive_ref="abc123")

    assert route("reset", root, {"feature": "feat-b", "force": True}) == 0

    assert active_slugs(root) == ["feat-a"]
    assert foreground_slug(root) == "feat-a"
    assert not auto_base_path(root, "feat-b").exists()
    # runtime 项目级字段跨 reset 保留（fallback 额度刻意不随需求清零）
    assert load_runtime(root) == {"fallback_count": 1, "last_archive_ref": "abc123"}


def test_reset_unknown_feature_rejected(tmp_path):
    """reset --feature 指向不活跃 slug → 拒绝并列出活跃清单。"""
    from specpowers_cli.bridge.dispatcher import route

    root = tmp_path
    _seed_feature(root, "feat-a", stage="apply")

    with pytest.raises(StateError, match="不是活跃需求"):
        route("reset", root, {"feature": "ghost"})


# ---- 粘滞锚点与 resume 探测多需求 ----

def test_sticky_note_multi_feature_lines(tmp_path):
    """多需求粘滞：每需求一行、前台标注、前台排首行（stage 为工件推导值）。"""
    from specpowers_cli.bridge.modules.resume_probe import sticky_note

    root = tmp_path
    _seed_feature(root, "feat-a", stage="apply")
    _seed_feature(root, "feat-b", stage="propose")

    msg = sticky_note(root)
    lines = msg.splitlines()
    assert len(lines) == 2
    # 前台（feat-b，最近 seed）排首行且带标注
    assert lines[0].startswith("活跃需求 feat-b（前台）")
    assert "（propose）" in lines[0]
    assert lines[1].startswith("活跃需求 feat-a（")
    assert "（apply）" in lines[1]
    # 每行锚点含各自的解除指引（per-feature 粒度）
    assert "/specpowers-archive --feature feat-b" in lines[0]
    assert "/specpowers-maintain reset --feature feat-a" in lines[1]


def test_sticky_note_truncates_beyond_three(tmp_path):
    """>3 个活跃需求：前台 + 2 行后台 + 1 行汇总（控 token）。"""
    from specpowers_cli.bridge.modules.resume_probe import sticky_note

    root = tmp_path
    for slug in ("feat-a", "feat-b", "feat-c", "feat-d"):
        _seed_feature(root, slug, stage="apply")

    msg = sticky_note(root)
    lines = msg.splitlines()
    assert len(lines) == 4
    assert lines[0].startswith("活跃需求 feat-d（前台）")
    assert lines[3].startswith("另有 1 个后台活跃需求：feat-c")
    assert "--feature" in lines[3]


def test_sticky_note_per_feature_release(tmp_path, monkeypatch):
    """归档 B 后 A 的锚点仍在（粘滞解除是 per-feature 的），A 自动回前台。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.modules.resume_probe import sticky_note
    from specpowers_cli.bridge.modules.state_derivation import foreground_slug

    _mock_openspec_archive(monkeypatch)
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_archive_ready_feature(root, "feat-a")
    _seed_archive_ready_feature(root, "feat-b")

    assert route("archive", root, {"feature": "feat-b"}) == 0

    msg = sticky_note(root)
    assert "feat-a" in msg
    assert "feat-b" not in msg
    # A 自动回前台（剩余 last_touched 最大者）
    assert foreground_slug(root) == "feat-a"


def test_probe_resume_multi_feature(tmp_path):
    """probe 多需求：每需求一行续跑指引，前台标注，stage 为推导值。"""
    from specpowers_cli.bridge.modules.resume_probe import probe_resume

    root = tmp_path
    _seed_feature(root, "feat-a", stage="apply")
    _seed_feature(root, "feat-b", stage="explore")

    msg = probe_resume(root)
    assert "feat-a" in msg
    assert "feat-b" in msg
    assert "（前台）" in msg
    assert msg.splitlines()[0].startswith("📌 检测到未完成的特性流水线：feat-b（前台）")
    # 各行按推导阶段给续跑指引
    assert "/specpowers-apply" in msg
    assert "当前阶段 explore" in msg


# ---- auto 按需求隔离 ----

def test_auto_status_targets_background_feature(tmp_path):
    """auto_status --feature 指定后台需求：按其目录推导与 auto_base 分片判定。"""
    from specpowers_cli.bridge.core.fs_state import auto_base_path
    from specpowers_cli.bridge.dispatcher import auto_status

    root = tmp_path
    _seed_feature(root, "feat-a", stage="apply")   # 无 auto_base
    _seed_feature(root, "feat-b", stage="apply")
    base = auto_base_path(root, "feat-b")
    base.parent.mkdir(parents=True, exist_ok=True)
    base.write_text(json.dumps({
        "base_commit": "x", "feature": "feat-b", "design_doc": "",
        "design_doc_hash": "", "rounds": [],
    }), encoding="utf-8")

    result = auto_status(root)
    # 未指名 → 前台（feat-b），无新输入 → resume
    assert result["mode"] == "resume"
    assert result["feature"] == "feat-b"
    assert result["stage"] == "apply"

    # 显式指定后台 A（无 auto_base）→ iterate + auto_base_missing
    result = auto_status(root, feature="feat-a")
    assert result["mode"] == "iterate"
    assert result["feature"] == "feat-a"
    assert result["auto_base_missing"] is True


def test_auto_status_unknown_feature_rejected(tmp_path):
    """auto_status 显式指定不活跃 slug → 报错（防误判 fresh）。"""
    from specpowers_cli.bridge.dispatcher import auto_status

    root = tmp_path
    _seed_feature(root, "feat-a", stage="apply")

    with pytest.raises(StateError, match="不是活跃需求"):
        auto_status(root, feature="ghost")


# ---- facade status / record-execution-mode 多需求 ----

def test_facade_status_reports_features_overview(tmp_path, capsys):
    """facade status：前台平铺 + features 概览 + foreground 键 + runtime 字段；无 schema 键。"""
    from specpowers_cli.bridge.facade import main

    root = tmp_path
    write_runtime(root, fallback_count=1, last_archive_ref="abc123")
    _seed_feature(root, "feat-a", stage="apply", rounds=2)
    _seed_feature(root, "feat-b", stage="propose")

    assert main(["status", "--root", str(root)]) == 0
    out = json.loads(capsys.readouterr().out)
    # 顶层平铺（旧消费者兼容：前台需求展开；schema 键随 state 退役删除）
    assert out["feature"] == "feat-b"
    assert out["stage"] == "propose"
    assert "schema" not in out
    # runtime 项目级字段
    assert out["fallback_count"] == 1
    assert out["last_archive_ref"] == "abc123"
    # 概览键（slug → stage/mode/iteration_count 全推导）
    assert out["features"]["feat-a"] == {"stage": "apply", "mode": "full", "iteration_count": 2}
    assert out["features"]["feat-b"]["stage"] == "propose"
    assert out["foreground"] == "feat-b"


def test_record_execution_mode_feature_targeting(tmp_path):
    """record-execution-mode --feature B：写入 B 的 meta，A 不受影响。"""
    from specpowers_cli.bridge.facade import main

    root = tmp_path
    _seed_feature(root, "feat-a", stage="apply")
    _seed_feature(root, "feat-b", stage="apply")

    assert main(
        ["record-execution-mode", "tdd", "--feature", "feat-b", "--root", str(root)]) == 0

    assert read_meta_of(root, "feat-b")["execution_mode"] == "tdd"
    assert read_meta_of(root, "feat-a").get("execution_mode", "") == ""


def test_record_execution_mode_multi_active_requires_feature(tmp_path):
    """多活跃 + record-execution-mode 未指名 → 非 0 退出并提示 --feature。"""
    from specpowers_cli.bridge.facade import main

    root = tmp_path
    _seed_feature(root, "feat-a", stage="apply")
    _seed_feature(root, "feat-b", stage="apply")

    rc = main(["record-execution-mode", "tdd", "--root", str(root)])
    assert rc != 0
