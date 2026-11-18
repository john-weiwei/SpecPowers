"""Tests for auto 模式多轮迭代 — 三分判定 / new-round rounds 记录 / 归档清理 / feature 锁定（v3.0 推导化）。

覆盖 v3.0.0 状态机推导化后的确定性层行为（state.json 退役，测试现场 =
openspec/changes/ 工件目录 + change 目录 meta + auto_base 分片，构造走 helpers_v3）：
- auto-status 三分判定：fresh 残留清理 / resume 无新输入 / iterate 文档 hash 变更
  （scope_hint=full）与仅口头指令（scope_hint=light）/ 旧格式 base 兼容 /
  base 缺失保守 iterate / stage 与 round 全推导（derive_stage + iteration_count_of）
- auto new-round：仅落 auto_base.rounds 记录（无 state 写点）/ 旧格式无 rounds 迁移 /
  三类拒绝（无 base / 无活跃 / 已归档）/ 轮次生效靠工件痕迹（design-round-N.md）推导 /
  不占用回退额度
- explore/propose 的 --feature 显式锁定（v3.0 断言走 meta 与输出指引，state 断言随退役删除）
- 归档成功：auto_base 分片清理 + 需求终结由目录承载 + runtime.last_archive_ref 刷新
- 人工迭代轮（facade iterate 子命令已退役）：propose 对 apply 态需求重入 = 回退额度入口；
  propose 自环幂等续作；rounds 记录唯一写点是 auto-new-round
- 需求澄清登记（ceiling 落盘 / 刷新 / 非法拒绝 / pending_input 停靠保护 / brainstorm 旧值归一）

生产 bug 兜底（单报，勿在本套件断言其行为）：artifact_registry.MANIFEST 仍把已退役的
.specpowers/state.json 登记为必需产物（required=True、consumers=["*"]），导致
explore/propose/fast/apply/archive 在任何 v3.0 项目（全新或迁移后）必然
ArtifactMissingError。下方 autouse fixture 在文件域内过滤该陈旧条目，生产修复后应删除。

作者：005819 | 协作：GLM-5.3 | 日期：2026-11-17
"""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from specpowers_cli.bridge.core.errors import StateError
from tests.helpers_v3 import make_change, make_triple, read_meta_of, write_runtime




def _create_temp_git_repo(tmp_path: Path) -> Path:
    """在 pytest tmp_path 下创建带提交的临时 git 仓库（会话级模板复制，约 10ms）。"""
    from tests._gitrepo import create_git_repo

    return create_git_repo(tmp_path / "auto-iter-repo")


def _init_project(root: Path) -> None:
    """初始化项目产物（constitution/baseline，模拟已 init 项目——v3.0 无 state 可写）。"""
    (root / ".specpowers").mkdir(exist_ok=True)
    (root / ".specpowers" / "constitution.md").write_text("# C", encoding="utf-8")
    (root / ".specpowers" / "baseline.json").write_text("{}", encoding="utf-8")


def _auto_base_file(root: Path, feature: str = "auto-feat") -> Path:
    """按需求隔离的 auto_base 路径（v2.8.0 起 .specpowers/auto_base/<feature>.json）。"""
    return root / ".specpowers" / "auto_base" / f"{feature}.json"


def _write_auto_base(root: Path, data: dict, feature: str = "auto-feat") -> None:
    """写入 .specpowers/auto_base/<feature>.json（测试辅助，直接 json 落盘）。"""
    path = _auto_base_file(root, feature)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8",
    )


def _read_auto_base(root: Path, feature: str = "auto-feat") -> dict:
    """读取 .specpowers/auto_base/<feature>.json（测试辅助）。"""
    return json.loads(_auto_base_file(root, feature).read_text(encoding="utf-8"))


_APPLY_TASKS = "### Task 1: x\n\n- [x] done\n"
_PROPOSE_TASKS = "### Task 1: x\n\n- [ ] todo\n"


def _seed_active_auto_feature(root: Path, feature: str = "auto-feat",
                              rounds: int = 1, stage: str = "apply") -> Path:
    """构造活跃 auto 需求：工件目录 + design-round 轮次痕迹 + auto_base 分片。

    stage 决定目录形态（apply=三件套+勾选 / propose=三件套无勾选 / explore=仅 meta），
    rounds>0 时落 design-round-<rounds>.md（轮次推导痕迹），auto_base.rounds 同步补
    1..rounds 记录，保持与工件推导值一致。
    """
    meta = {"mode": "full", "last_touched": "2026-01-01T00:00:00+00:00"}
    if stage == "apply":
        change = make_triple(root, feature, _APPLY_TASKS, meta=meta)
    elif stage == "propose":
        change = make_triple(root, feature, _PROPOSE_TASKS, meta=meta)
    else:  # explore：仅 meta（explore 收口态，尚无三件套）
        change = make_change(root, feature, meta=meta)
    if rounds >= 1:
        (change / f"design-round-{rounds}.md").write_text("# 本轮增量", encoding="utf-8")
    _write_auto_base(root, {
        "base_commit": "aaa111",
        "feature": feature,
        "design_doc": "",
        "design_doc_hash": "",
        "created_at": "2026-01-01T00:00:00+00:00",
        "rounds": [
            {
                "round": i,
                "input": {"type": "doc", "doc": "design.md", "instruction": ""},
                "started_at": "2026-01-01T00:00:00+00:00",
            }
            for i in range(1, rounds + 1)
        ],
    }, feature)
    return change


def _make_design_doc(tmp_path: Path, name: str = "design.md", content: str = "# 设计") -> Path:
    """在 tmp 下创建设计文档，返回路径。"""
    doc = tmp_path / name
    doc.write_text(content, encoding="utf-8")
    return doc


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


# ---- auto-status 三分判定 ----

def test_auto_status_fresh_and_cleans_legacy_base(tmp_path):
    """无活跃需求 → fresh；上一需求的 auto_base 分片残留与旧版顶层 auto_base.json 孤儿顺带清理。"""
    from specpowers_cli.bridge.dispatcher import auto_status

    root = _create_temp_git_repo(tmp_path)
    _write_auto_base(root, {"base_commit": "old", "design_doc": "old.md"}, feature="old")
    legacy = root / ".specpowers" / "auto_base.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text('{"base_commit": "older"}', encoding="utf-8")

    result = auto_status(root)
    assert result["mode"] == "fresh"
    assert result["feature"] == ""
    assert result["round"] == 0
    assert result["stage"] == "ready"
    assert result["auto_base_removed"] is True
    # 旧版顶层 auto_base.json 孤儿（无活跃需求时无人认领）一并清理
    assert not legacy.exists()
    assert not _auto_base_file(root, "old").exists()


def test_auto_status_resume_when_doc_unchanged(tmp_path):
    """活跃需求 + 文档 hash 未变 + 无指令 → resume（断点续跑；stage/round 全工件推导）。"""
    from specpowers_cli.bridge.dispatcher import auto_status

    root = _create_temp_git_repo(tmp_path)
    doc = _make_design_doc(tmp_path, content="# 设计 v1")
    _seed_active_auto_feature(root)  # apply 态 + design-round-1
    base = _read_auto_base(root)
    base["design_doc"] = str(doc)
    base["design_doc_hash"] = hashlib.sha256(doc.read_bytes()).hexdigest()
    _write_auto_base(root, base)

    result = auto_status(root, design_doc=str(doc))
    assert result["mode"] == "resume"
    assert result["feature"] == "auto-feat"
    # stage/iteration_count 不再读 state：apply 态与 Round 1 从工件推导
    assert result["stage"] == "apply"
    assert result["iteration_count"] == 1
    assert result["round"] == 1


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
    assert result["round"] == 2  # 推导轮次 1 + 1 的建议轮
    assert result["iteration_count"] == 1
    assert result["design_doc_exists"] is True


def test_auto_status_iterate_on_instruction_only_scope_light(tmp_path):
    """仅口头指令（无文档）→ iterate + scope_hint=light；stage 为工件推导值。"""
    from specpowers_cli.bridge.dispatcher import auto_status

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root, stage="propose")

    result = auto_status(root, instruction="补充导出失败的失败场景")
    assert result["mode"] == "iterate"
    assert result["scope_hint"] == "light"
    assert result["stage"] == "propose"  # 三件套齐无勾选 → 工件推导 propose
    assert result["round"] == 2  # 推导轮次 1（design-round-1）+ 1


def test_auto_status_iterate_when_manual_pipeline_no_base(tmp_path):
    """活跃需求缺 auto_base（人工流程被 auto 接管）→ iterate + auto_base_missing 保守全量。"""
    from specpowers_cli.bridge.dispatcher import auto_status
    from tests.helpers_v3 import make_triple

    root = _create_temp_git_repo(tmp_path)
    make_triple(root, "manual-feat", _APPLY_TASKS,
                meta={"mode": "full", "last_touched": "2026-01-01T00:00:00+00:00"})

    result = auto_status(root)
    assert result["mode"] == "iterate"
    assert result["feature"] == "manual-feat"
    assert result["auto_base_missing"] is True
    assert result["scope_hint"] == "full"
    assert result["round"] == 1  # 工件推导 0 + 1


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


# ---- auto new-round 受控轮次切换（v3.0：仅落 auto_base.rounds，无 state 写点）----

def test_auto_new_round_appends_round_record(tmp_path):
    """new-round：rounds 追加本轮记录、文档指针刷新；无任何 state 写点。"""
    from specpowers_cli.bridge.dispatcher import route

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root)  # design-round-1 → 推导轮次 1
    new_doc = _make_design_doc(tmp_path, name="design-v2.md")

    assert route("auto-new-round", root, extra={
        "design_doc": str(new_doc), "instruction": "补充失败场景",
    }) == 0

    base = _read_auto_base(root)
    assert len(base["rounds"]) == 2
    assert base["rounds"][1]["round"] == 2  # iteration_count_of + 1
    assert base["rounds"][1]["input"]["type"] == "doc+instruction"
    assert base["rounds"][1]["input"]["doc"] == str(new_doc)
    assert base["rounds"][1]["started_at"]
    assert base["design_doc"] == str(new_doc)
    assert base["design_doc_hash"] == hashlib.sha256(new_doc.read_bytes()).hexdigest()
    # v3.0 无 state 写点：state.json 不应被任何命令写出
    assert not (root / ".specpowers" / "state.json").exists()


def test_auto_new_round_migrates_legacy_base(tmp_path):
    """旧格式 base（无 rounds 字段）→ 按 round 1 迁移（留痕注记），新轮追加为 round 2。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.modules.state_derivation import iteration_count_of

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root)  # design-round-1 = 历史已跑一轮的工件凭据
    legacy = _read_auto_base(root)
    legacy.pop("rounds")
    legacy["design_doc"] = "old-design.md"
    _write_auto_base(root, legacy)

    assert route("auto-new-round", root, extra={"instruction": "第二轮"}) == 0

    base = _read_auto_base(root)
    assert [r["round"] for r in base["rounds"]] == [1, 2]
    assert base["rounds"][0]["note"].startswith("旧格式")
    # 迁移代表历史已跑一轮（工件痕迹 design-round-1 在）：新轮记录为 2
    assert iteration_count_of(root / "openspec" / "changes" / "auto-feat") == 1


def test_auto_new_round_requires_auto_base(tmp_path):
    """活跃需求无 auto_base 分片 → 拒绝（不是 auto 模式需求，请走全新 /specpowers-auto）。"""
    from specpowers_cli.bridge.dispatcher import route
    from tests.helpers_v3 import make_triple

    root = _create_temp_git_repo(tmp_path)
    make_triple(root, "plain-feat", _APPLY_TASKS,
                meta={"mode": "full", "last_touched": "2026-01-01T00:00:00+00:00"})

    with pytest.raises(StateError, match="auto_base"):
        route("auto-new-round", root, extra={})
    assert not _auto_base_file(root, "plain-feat").exists()


def test_auto_new_round_requires_active_feature(tmp_path):
    """无活跃需求（已归档/从未开始）→ 拒绝（活跃权威 = 目录扫描）。"""
    from specpowers_cli.bridge.dispatcher import route

    root = _create_temp_git_repo(tmp_path)
    _write_auto_base(root, {"base_commit": "x"})

    with pytest.raises(StateError, match="无活跃需求"):
        route("auto-new-round", root, extra={})


def test_auto_new_round_rejected_when_archived(tmp_path):
    """feature 已有 archive commit → 拒绝迭代轮（归档即新需求）。"""
    from specpowers_cli.bridge.dispatcher import route

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root, feature="archived-feat")
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", "specpowers: archived-feat"],
        cwd=str(root), capture_output=True, check=True,
    )

    with pytest.raises(StateError, match="已归档"):
        route("auto-new-round", root, extra={})


def test_auto_new_round_takes_effect_via_artifacts(tmp_path):
    """轮次生效靠工件痕迹：new-round 只落 rounds 记录，design-round-2.md 落盘后推导轮次才 +1。"""
    from specpowers_cli.bridge.dispatcher import auto_status, route
    from specpowers_cli.bridge.modules.state_derivation import iteration_count_of

    root = _create_temp_git_repo(tmp_path)
    change = _seed_active_auto_feature(root)  # design-round-1

    assert route("auto-new-round", root, extra={"instruction": "方案调整"}) == 0
    # 记录已追加（round 2），但工件无新一轮痕迹 → 推导轮次仍 1
    assert [r["round"] for r in _read_auto_base(root)["rounds"]] == [1, 2]
    assert iteration_count_of(change) == 1
    assert auto_status(root)["iteration_count"] == 1

    # 认知层落 design-round-2.md（工件痕迹）→ 推导轮次 2，下一轮建议 3
    (change / "design-round-2.md").write_text("# 第二轮增量", encoding="utf-8")
    assert iteration_count_of(change) == 2
    status = auto_status(root, instruction="再调整")
    assert status["iteration_count"] == 2
    assert status["round"] == 3

    assert route("auto-new-round", root, extra={"instruction": "第三轮"}) == 0
    assert [r["round"] for r in _read_auto_base(root)["rounds"]] == [1, 2, 3]


def test_auto_new_round_does_not_consume_fallback(tmp_path):
    """auto 轮次切换不走回退额度：额度已耗尽（fallback_count=1）仍可开轮，计次不动。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import load_runtime

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root)
    write_runtime(root, fallback_count=1)  # 项目生命周期唯一的 apply→propose 回退已用掉

    assert route("auto-new-round", root, extra={"instruction": "继续迭代"}) == 0
    assert load_runtime(root)["fallback_count"] == 1  # 不校验也不消耗
    assert [r["round"] for r in _read_auto_base(root)["rounds"]] == [1, 2]


# ---- feature 显式锁定（--feature）----

def test_explore_explicit_feature_lock(tmp_path, capsys):
    """explore --feature 显式锁定 slug 不随 requirement 措辞漂移；登记收口落 meta 建目录。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.modules.state_derivation import (
        active_slugs, change_dir_of, derive_stage,
    )

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)

    assert route("explore", root, extra={
        "requirement": "全新需求措辞",
        "feature": "locked-feat",
    }) == 0
    assert "locked-feat" in capsys.readouterr().out
    # v3.0 explore 进行中无写点：change 目录尚未建立（登记收口才落 meta）
    assert not change_dir_of(root, "locked-feat").exists()

    # 收口：设计文档落盘并登记 → 需求以锁定 slug 进入活跃清单（explore 态）
    doc = root / "docs" / "specpowers" / "design" / "locked-design.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("# 设计\n## 方案对比\nA\n## 详细设计\n略\n", encoding="utf-8")
    assert route("record-design-doc", root, extra={
        "design_doc": str(doc), "feature": "locked-feat",
    }) == 0
    assert active_slugs(root) == ["locked-feat"]
    assert derive_stage(change_dir_of(root, "locked-feat")) == "explore"
    meta = read_meta_of(root, "locked-feat")
    assert meta["design_doc"] == "docs/specpowers/design/locked-design.md"
    assert meta["last_touched"]


def test_propose_explicit_feature_overrides_existing(tmp_path):
    """propose --feature 显式指定优先于前台推导；操作即前台（meta last_touched）。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.modules.state_derivation import (
        change_dir_of, foreground_slug, read_meta,
    )

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    # 前台 origin-feat（explore 态，仅 meta；登记与 touch 时间均为种子值）
    make_change(root, "origin-feat", meta={
        "mode": "full", "last_touched": "2026-01-01T00:00:00+00:00",
        "design_doc": "docs/specpowers/design/origin-design.md",
    })

    # 显式 slug 不活跃 → from ready 开新需求（不校验设计文档登记）
    assert route("propose", root, extra={
        "requirement": "需求描述",
        "feature": "locked-feat",
    }) == 0

    meta = read_meta_of(root, "locked-feat")
    assert meta["mode"] == "full"  # 新需求建目录动作（meta 即登记）
    assert meta["last_touched"]
    assert foreground_slug(root) == "locked-feat"  # 操作即前台
    # origin-feat 分片不动（多需求并存的根基）
    origin = read_meta(change_dir_of(root, "origin-feat")) or {}
    assert origin["design_doc"] == "docs/specpowers/design/origin-design.md"
    assert origin["last_touched"] == "2026-01-01T00:00:00+00:00"


# ---- 归档清理 auto_base 分片 + 需求终结由目录承载 ----

def test_archive_cleans_auto_base_and_ends_feature(tmp_path, monkeypatch):
    """归档成功：auto_base 分片删除、需求从活跃清单消失（目录快照承载）、runtime 基准刷新。"""
    from specpowers_cli.bridge.core.fs_state import auto_base_path, load_runtime
    from specpowers_cli.bridge.core.git_util import git_ref_of
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.modules.state_derivation import active_slugs

    _mock_openspec_archive(monkeypatch)
    root = _create_temp_git_repo(tmp_path)
    feature = "auto-feat"
    _init_project(root)
    _seed_active_auto_feature(root, feature=feature, rounds=2)
    # 归档前置产物：delta spec 目录（spec 校验到目录级）
    spec_dir = root / "openspec" / "changes" / feature / "specs" / feature
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(
        "## ADDED Requirements\n\n### Requirement: " + feature +
        "\nThe system SHALL work.\n\n#### Scenario: s1\n- **WHEN** x\n- **THEN** y\n",
        encoding="utf-8",
    )

    assert route("archive", root, extra={}) == 0

    assert not auto_base_path(root, feature).exists()
    # 需求终结由工件承载：change 移入 archive 快照后活跃清单即时更新（无状态清零动作）
    assert feature not in active_slugs(root)
    assert (root / "openspec" / "changes" / "archive" / feature).is_dir()
    # merge check 基准刷新为归档时 HEAD（runtime 项目级字段）
    assert load_runtime(root)["last_archive_ref"] == git_ref_of(root)


# ---- 人工模式迭代轮（facade iterate 已退役：propose 重入由目录推导识别）----

def _seed_manual_apply_repo(tmp_path: Path, feature: str = "manual-feat") -> Path:
    """构造人工模式活跃需求的完整前置（constitution + baseline + apply 态工件）。"""
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    make_triple(root, feature, _APPLY_TASKS, meta={
        "mode": "full", "last_touched": "2026-01-01T00:00:00+00:00",
    })
    return root


def test_propose_reentry_on_apply_consumes_fallback(tmp_path):
    """人工迭代轮入口（v3.0）：propose 对 apply 态需求重入 = 消耗唯一回退额度 + mode 归 full。"""
    from specpowers_cli.bridge.core.fs_state import load_runtime
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.modules.state_derivation import change_dir_of, iteration_count_of

    root = _seed_manual_apply_repo(tmp_path)

    assert route("propose", root, extra={"requirement": "补充失败场景"}) == 0

    assert load_runtime(root)["fallback_count"] == 1
    assert read_meta_of(root, "manual-feat")["mode"] == "full"
    # 无 auto 基线时不落 auto_base 分片（人工模式无此文件）
    assert not _auto_base_file(root, "manual-feat").exists()
    # 轮次由工件推导：入口动作本身不产生痕迹，仍为首轮 0
    assert iteration_count_of(change_dir_of(root, "manual-feat")) == 0


def test_propose_reentry_leaves_rounds_to_auto_new_round(tmp_path):
    """rounds 记录唯一写点是 auto-new-round：人工 propose 重入共用基线但不追加轮记录。"""
    from specpowers_cli.bridge.core.fs_state import load_runtime
    from specpowers_cli.bridge.dispatcher import route

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    _seed_active_auto_feature(root, feature="manual-feat")  # apply 态 + auto_base rounds [1]

    assert route("propose", root, extra={"requirement": "调整范围"}) == 0
    # 人工重入（apply→propose 走回退额度）不写 rounds
    assert load_runtime(root)["fallback_count"] == 1
    assert [r["round"] for r in _read_auto_base(root, "manual-feat")["rounds"]] == [1]

    # auto 模式受控切换才追加本轮记录（推导轮次 1 + 1 = 2）
    assert route("auto-new-round", root, extra={"instruction": "调整范围"}) == 0
    base = _read_auto_base(root, "manual-feat")
    assert [r["round"] for r in base["rounds"]] == [1, 2]
    assert base["rounds"][1]["input"]["type"] == "instruction"


def test_propose_after_archive_starts_new_need(tmp_path):
    """人工侧归档即新需求（v3.0 无 iterate 命令）：已归档 slug 不续作，重入 propose 即全新需求。"""
    from specpowers_cli.bridge.core.fs_state import load_runtime
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.modules.state_derivation import (
        active_slugs, change_dir_of,
    )

    root = _seed_manual_apply_repo(tmp_path, feature="done-feat")
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", "specpowers: done-feat"],
        cwd=str(root), capture_output=True, check=True,
    )
    # openspec archive 的目录快照语义
    snapshot = root / "openspec" / "changes" / "archive" / "done-feat"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    change_dir_of(root, "done-feat").rename(snapshot)

    assert route("propose", root, extra={"requirement": "brand new requirement"}) == 0

    assert active_slugs(root) == ["brand-new-requirement"]
    assert (root / "openspec" / "changes" / "archive" / "done-feat").is_dir()
    # 新需求不吃回退额度（归档即新需求，回退路径只对活跃需求存在）
    assert load_runtime(root)["fallback_count"] == 0
    assert read_meta_of(root, "brand-new-requirement")["mode"] == "full"


def test_propose_self_loop_after_iteration_continues_round(tmp_path):
    """迭代轮中重跑 /specpowers-propose（propose 自环）→ 幂等放行续作：轮次不变、不占额度。"""
    from specpowers_cli.bridge.core.fs_state import load_runtime
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.modules.state_derivation import change_dir_of, iteration_count_of

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    change = make_triple(root, "manual-feat", _PROPOSE_TASKS, meta={
        "mode": "full", "last_touched": "2026-01-01T00:00:00+00:00"})
    (change / "design-round-1.md").write_text("# 第一轮增量", encoding="utf-8")

    assert route("propose", root, extra={"requirement": "补充失败场景"}) == 0

    assert load_runtime(root)["fallback_count"] == 0  # propose→propose 自环不是回退
    assert read_meta_of(root, "manual-feat")["mode"] == "full"
    # 轮次由工件承载：自环续作不产生新轮痕迹
    assert iteration_count_of(change_dir_of(root, "manual-feat")) == 1


def test_propose_self_loop_idempotent_without_iteration(tmp_path):
    """无迭代痕迹（Round 0）的 propose 自环重跑同样放行（幂等，轮次仍为 0）。"""
    from specpowers_cli.bridge.core.fs_state import load_runtime
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.modules.state_derivation import change_dir_of, iteration_count_of

    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    make_triple(root, "manual-feat", _PROPOSE_TASKS, meta={
        "mode": "full", "last_touched": "2026-01-01T00:00:00+00:00"})

    assert route("propose", root, extra={"requirement": "重新生成"}) == 0

    assert load_runtime(root)["fallback_count"] == 0
    assert iteration_count_of(change_dir_of(root, "manual-feat")) == 0
    assert read_meta_of(root, "manual-feat")["last_touched"]


# ---- 需求澄清登记（auto clarify，方案 docs/auto-clarification-plan.md）----

def test_auto_clarify_registers_ceiling_and_refresh(tmp_path):
    """clarify：ceiling 落盘 clarification 字段；重复调用为刷新（覆盖，非追加），rounds 不受影响。"""
    from specpowers_cli.bridge.dispatcher import route

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root, rounds=0)

    assert route("auto-clarify", root, extra={
        "ceiling": "explore",
        "report": ".specpowers/auto_clarifications/auto-feat.md",
    }) == 0
    base = _read_auto_base(root)
    clar = base["clarification"]
    assert clar["ceiling"] == "explore"
    assert clar["report_path"] == ".specpowers/auto_clarifications/auto-feat.md"
    assert clar["checked_at"]
    assert base["rounds"] == []  # 澄清登记不动轮次记录

    # 刷新语义：再次登记覆盖旧结论（迭代轮 ceiling 上调落盘凭据）
    assert route("auto-clarify", root, extra={"ceiling": "full"}) == 0
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
        route("auto-clarify", root, extra={"ceiling": "galaxy"})
    assert "clarification" not in _read_auto_base(root)


def test_auto_clarify_requires_auto_base(tmp_path):
    """活跃需求无 auto_base 分片（第 0 步基点记录未执行）→ 拒绝登记（防声称澄清但无基线）。"""
    from specpowers_cli.bridge.dispatcher import route
    from tests.helpers_v3 import make_triple

    root = _create_temp_git_repo(tmp_path)
    make_triple(root, "plain-feat", _APPLY_TASKS,
                meta={"mode": "full", "last_touched": "2026-01-01T00:00:00+00:00"})

    with pytest.raises(StateError):
        route("auto-clarify", root, extra={"ceiling": "full"})


def test_auto_status_resume_reports_pending_input_when_parked(tmp_path):
    """ceiling=explore 停靠 + 无新输入重入 → resume + pending_input=True（契约层据此禁止盲续跑）。"""
    from specpowers_cli.bridge.dispatcher import auto_status

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root, rounds=0, stage="explore")
    base = _read_auto_base(root)
    base["clarification"] = {
        "ceiling": "explore",
        "report_path": ".specpowers/auto_clarifications/auto-feat.md",
        "checked_at": "2026-01-01T00:00:00+00:00",
    }
    _write_auto_base(root, base)

    result = auto_status(root)
    assert result["mode"] == "resume"
    assert result["stage"] == "explore"  # 仅 meta 的目录形态 → 工件推导 explore
    assert result["clarification"]["ceiling"] == "explore"
    assert result["clarification"]["pending_input"] is True
    assert result["clarification"]["report_path"].endswith("auto-feat.md")


def test_auto_status_iterate_clears_pending_input(tmp_path):
    """停靠后带口头指令（方案结论）重入 → iterate + pending_input=False，ceiling 原值透传。"""
    from specpowers_cli.bridge.dispatcher import auto_status

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root, rounds=0, stage="explore")
    base = _read_auto_base(root)
    base["clarification"] = {
        "ceiling": "explore",
        "report_path": "",
        "checked_at": "2026-01-01T00:00:00+00:00",
    }
    _write_auto_base(root, base)

    result = auto_status(root, instruction="方案定为方案B，理由见讨论")
    assert result["mode"] == "iterate"
    assert result["clarification"]["ceiling"] == "explore"
    assert result["clarification"]["pending_input"] is False


def test_auto_status_clarification_none_when_unregistered(tmp_path):
    """旧格式/未登记澄清（auto_base 无 clarification 字段）→ clarification=None（契约层补做澄清）。"""
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
    _seed_active_auto_feature(root, rounds=0)

    assert main(["auto", "clarify", "--ceiling", "explore", "--root", str(root)]) == 0
    assert _read_auto_base(root)["clarification"]["ceiling"] == "explore"
    # 旧值兼容：v1.x 的 brainstorm 读入归一为 explore
    assert main(["auto", "clarify", "--ceiling", "brainstorm", "--root", str(root)]) == 0
    assert _read_auto_base(root)["clarification"]["ceiling"] == "explore"

    assert main(["auto", "clarify", "--ceiling", "bad", "--root", str(root)]) == 2


# ---- v2.0.0 旧值兼容（ceiling=brainstorm 归一为 explore）----

def test_auto_status_normalizes_legacy_brainstorm_ceiling(tmp_path):
    """v1.x 登记的 ceiling=brainstorm 读出归一为 explore，pending_input 语义不变。"""
    from specpowers_cli.bridge.dispatcher import auto_status

    root = _create_temp_git_repo(tmp_path)
    _seed_active_auto_feature(root, rounds=0, stage="explore")
    base = _read_auto_base(root)
    base["clarification"] = {
        "ceiling": "brainstorm",
        "report_path": "",
        "checked_at": "2026-01-01T00:00:00+00:00",
    }
    _write_auto_base(root, base)

    result = auto_status(root)
    assert result["clarification"]["ceiling"] == "explore"
    assert result["clarification"]["pending_input"] is True
