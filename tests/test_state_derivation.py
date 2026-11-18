"""Tests for state_derivation module — 工件推导纯函数集（v2.12 状态机推导化）。

覆盖四组能力：
- is_active_change：change 目录活跃判定（含 .specpowers-meta.json 扩展）
- iteration_count_of：迭代轮次从 design-round-N.md 与 tasks.md Round 小节推导
- meta 读写：.specpowers-meta.json 自包含登记（损坏降级不阻断）
- reconcile_feature：读后对账（僵尸清理 / explore-fast 豁免 / 推导回写）

作者：005819 | 协作：GLM-5.3 | 日期：2026-11-17
"""

import json
import tempfile
from pathlib import Path

from specpowers_cli.bridge.modules.state_derivation import (
    META_FILENAME,
    change_dir_of,
    design_doc_of,
    is_active_change,
    iteration_count_of,
    read_meta,
    reconcile_feature,
    write_meta,
)


def _make_change(root: Path, slug: str, files: list[str] | None = None) -> Path:
    """构造 change 目录工件（files 为相对 change 目录的文件/目录列表）。"""
    change = change_dir_of(root, slug)
    change.mkdir(parents=True, exist_ok=True)
    for rel in files or []:
        target = change / rel
        if rel.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x", encoding="utf-8")
    return change


# ---- is_active_change ----

def test_is_active_change_variants():
    """活跃判定：三件套与 meta 任一存在即活跃；空目录与缺失目录不活跃。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        assert is_active_change(_make_change(root, "a", ["proposal.md"])) is True
        assert is_active_change(_make_change(root, "b", ["specs/"])) is True
        assert is_active_change(_make_change(root, "c", ["tasks.md"])) is True
        # v2.12 扩展：仅 meta（explore 完成待 propose）也算活跃
        assert is_active_change(_make_change(root, "d", [META_FILENAME])) is True
        # 空目录 / 目录不存在
        assert is_active_change(_make_change(root, "e")) is False
        assert is_active_change(root / "openspec" / "changes" / "missing") is False


# ---- iteration_count_of ----

def test_iteration_count_from_design_rounds():
    """轮次推导：design-round-N.md 文件名取最大 N。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        change = _make_change(Path(tmpdir), "a", ["design-round-1.md", "design-round-3.md"])
        assert iteration_count_of(change) == 3


def test_iteration_count_from_tasks_round_sections():
    """轮次推导：tasks.md「## Round N」小节标题取最大 N。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        change = _make_change(Path(tmpdir), "a", ["tasks.md"])
        (change / "tasks.md").write_text(
            "# Tasks\n\n## Round 2（调整A）\n\n### Task 1: x\n\n## Round 5（调整B）\n",
            encoding="utf-8",
        )
        assert iteration_count_of(change) == 5


def test_iteration_count_takes_max_of_both_sources():
    """轮次推导：两来源取大（design-round-7 + Round 2 → 7；design-round-3 + Round 5 → 5）。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        change = _make_change(Path(tmpdir), "a", ["design-round-7.md", "tasks.md"])
        (change / "tasks.md").write_text("## Round 2\n", encoding="utf-8")
        assert iteration_count_of(change) == 7

        change2 = _make_change(Path(tmpdir), "b", ["design-round-3.md", "tasks.md"])
        (change2 / "tasks.md").write_text("## Round 5\n", encoding="utf-8")
        assert iteration_count_of(change2) == 5


def test_iteration_count_empty_dir_returns_zero():
    """轮次推导：无任何轮次痕迹返回 0（首轮）。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        assert iteration_count_of(_make_change(Path(tmpdir), "a", ["proposal.md"])) == 0


# ---- meta 读写 ----

def test_read_meta_corrupt_degrades_to_none():
    """meta 损坏降级：非法 JSON / 顶层非对象 → None，不抛异常不阻断。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        change = _make_change(Path(tmpdir), "a")
        (change / META_FILENAME).write_text("{not-json", encoding="utf-8")
        assert read_meta(change) is None
        (change / META_FILENAME).write_text('["array"]', encoding="utf-8")
        assert read_meta(change) is None
        # 目录缺失同样降级
        assert read_meta(change_dir_of(Path(tmpdir), "missing")) is None


def test_write_meta_creates_change_dir_atomically():
    """meta 写入：change 目录不存在时创建，内容含 design_doc 与 created_at。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        meta_path = write_meta(root, "new-feature", "docs/specpowers/design/x-design.md")
        assert meta_path == change_dir_of(root, "new-feature") / META_FILENAME
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        assert data["design_doc"] == "docs/specpowers/design/x-design.md"
        assert data["created_at"]
        # 覆盖写（迭代登记）幂等
        write_meta(root, "new-feature", "docs/specpowers/design/y-design.md")
        data2 = json.loads(meta_path.read_text(encoding="utf-8"))
        assert data2["design_doc"] == "docs/specpowers/design/y-design.md"


def test_design_doc_of_via_meta():
    """设计文档指针推导：meta 提供路径；无 meta / meta 无值返回 None。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        write_meta(root, "a", "docs/specpowers/design/a-design.md")
        assert design_doc_of(root, "a") == "docs/specpowers/design/a-design.md"
        # 无 meta → None（工件无法证明）
        _make_change(root, "b", ["proposal.md"])
        assert design_doc_of(root, "b") is None
        # meta 存在但 design_doc 空 → None
        change = _make_change(root, "c", [META_FILENAME])
        (change / META_FILENAME).write_text(json.dumps({"design_doc": ""}), encoding="utf-8")
        assert design_doc_of(root, "c") is None


# ---- reconcile_feature（读后对账） ----

def _entry(stage: str = "propose", mode: str = "full", **extra) -> dict:
    """构造最小需求级条目（与 DEFAULT_FEATURE_STATE 合并语义对齐）。"""
    base = {
        "stage": stage,
        "mode": mode,
        "execution_mode": "",
        "iteration_count": 0,
        "design_doc": "",
        "created_at": "2026-11-17T00:00:00",
        "last_touched": "2026-11-17T00:00:00",
    }
    base.update(extra)
    return base


def test_reconcile_zombie_entry_cleaned():
    """僵尸清理：apply/archive 态条目无 change 目录 → 条目清 None + 警告含 slug。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        cleaned, warnings = reconcile_feature(root, "ghost", _entry(stage="apply"))
        assert cleaned is None
        assert len(warnings) == 1
        assert "ghost" in warnings[0]
        cleaned2, _ = reconcile_feature(root, "ghost2", _entry(stage="archive"))
        assert cleaned2 is None


def test_reconcile_propose_window_protected():
    """propose 窗口保护：三件套落盘窗口内目录暂缺 → 仅警告不清理（多会话安全）。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        entry = _entry(stage="propose")
        cleaned, warnings = reconcile_feature(root, "window", entry)
        assert cleaned == entry
        assert len(warnings) == 1
        assert "propose" in warnings[0]


def test_reconcile_exempt_explore_and_ready():
    """豁免：explore 态与 ready 态（fast 待编码 / auto 中间态）目录缺席合法。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        entry_explore = _entry(stage="explore")
        cleaned, warnings = reconcile_feature(root, "e1", entry_explore)
        assert cleaned == entry_explore
        assert warnings == []

        entry_fast = _entry(stage="ready", mode="fast")
        cleaned2, warnings2 = reconcile_feature(root, "f1", entry_fast)
        assert cleaned2 == entry_fast
        assert warnings2 == []

        # auto 编排中间态：ready + full 同样豁免
        entry_auto = _entry(stage="ready", mode="full")
        cleaned3, warnings3 = reconcile_feature(root, "a1", entry_auto)
        assert cleaned3 == entry_auto
        assert warnings3 == []


def test_reconcile_round_backfill_from_artifacts():
    """推导回写：工件轮次高于缓存（0）→ 回写推导值并记录差异行。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _make_change(root, "a", ["design-round-2.md", "tasks.md"])
        (change_dir_of(root, "a") / "tasks.md").write_text("## Round 1\n", encoding="utf-8")
        cleaned, warnings = reconcile_feature(root, "a", _entry(stage="apply"))
        assert cleaned["iteration_count"] == 2
        assert any("iteration_count" in w for w in warnings)


def test_reconcile_design_doc_backfill_from_meta():
    """推导回写：meta 提供指针而缓存为空 → 回填 meta 值。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        write_meta(root, "a", "docs/specpowers/design/a-design.md")
        cleaned, _ = reconcile_feature(root, "a", _entry(stage="propose"))
        assert cleaned["design_doc"] == "docs/specpowers/design/a-design.md"


def test_reconcile_keeps_cached_doc_without_meta():
    """旧需求兼容：缓存已有登记而 meta 缺失 → 保留缓存值（None≠应清除）。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _make_change(root, "legacy", ["proposal.md", "tasks.md"])
        entry = _entry(stage="apply", design_doc="docs/specpowers/design/legacy-design.md")
        cleaned, _ = reconcile_feature(root, "legacy", entry)
        assert cleaned["design_doc"] == "docs/specpowers/design/legacy-design.md"


def test_reconcile_consistent_entry_unchanged():
    """一致条目：推导值与缓存一致 → 原样返回零警告。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _make_change(root, "a", ["proposal.md", "design-round-2.md"])
        entry = _entry(stage="apply", iteration_count=2)
        cleaned, warnings = reconcile_feature(root, "a", entry)
        assert cleaned == entry
        assert warnings == []


# ---- derive_stage（v3.0 stage 判定表） ----

from specpowers_cli.bridge.modules.state_derivation import (  # noqa: E402
    active_slugs,
    audit_artifacts,
    derive_stage,
    foreground_slug,
    migrate_legacy_state,
    update_meta,
)


def _triple(root: Path, slug: str, tasks_text: str = "### Task 1: x\n\n- [ ] a\n") -> Path:
    """构造三件套齐全的 change 目录（tasks 文本可自定义勾选状态）。"""
    change = _make_change(root, slug, ["proposal.md", "specs/", "tasks.md"])
    (change / "tasks.md").write_text(tasks_text, encoding="utf-8")
    return change


def test_derive_stage_full_table():
    """stage 判定表全行覆盖：六种工件形态逐一短路判定。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        # 目录不存在 → explore
        assert derive_stage(change_dir_of(root, "missing")) == "explore"
        # 仅 meta（无 proposal）→ explore
        assert derive_stage(_make_change(root, "a", [META_FILENAME])) == "explore"
        # proposal 存在、specs 缺 → propose（进行中）
        assert derive_stage(_make_change(root, "b", ["proposal.md"])) == "propose"
        # proposal+specs、tasks 缺 → propose
        assert derive_stage(_make_change(root, "c", ["proposal.md", "specs/"])) == "propose"
        # 三件套齐无勾选 → propose
        assert derive_stage(_triple(root, "d")) == "propose"
        # 三件套齐有勾选 → apply
        assert derive_stage(
            _triple(root, "e", "### Task 1: x\n\n- [x] done\n- [ ] todo\n")
        ) == "apply"


def test_derive_stage_fast_mode_via_meta():
    """fast 判定：meta.mode=fast 短路（无三件套也判 fast）。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _make_change(root, "f", [META_FILENAME, "checklist.md"])
        update_meta(root, "f", {"mode": "fast"})
        assert derive_stage(change_dir_of(root, "f")) == "fast"


def test_derive_stage_ignores_retired_section_checkboxes():
    """勾选判定排除「## 已作废」小节：作废留痕勾选非 apply 进度。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        tasks = "### Task 1: x\n\n- [ ] todo\n\n## 已作废\n\n- [x] retired\n"
        assert derive_stage(_triple(root, "g", tasks)) == "propose"


def test_active_slugs_scans_directory():
    """活跃清单：目录扫描（排除 archive 与空目录），手动删目录即时消失。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _make_change(root, "b", ["proposal.md"])
        _make_change(root, "a", [META_FILENAME])
        _make_change(root, "empty")
        archive = root / "openspec" / "changes" / "archive" / "old"
        archive.mkdir(parents=True)
        (archive / "proposal.md").write_text("x", encoding="utf-8")
        assert active_slugs(root) == ["a", "b"]
        # 手动删目录 → 即时从清单消失（防僵尸语义）
        import shutil
        shutil.rmtree(change_dir_of(root, "b"))
        assert active_slugs(root) == ["a"]


def test_foreground_slug_by_meta_last_touched():
    """前台推导：meta last_touched 最大者；无 meta 降级目录 mtime；空清单 None。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        assert foreground_slug(root) is None
        _make_change(root, "a", ["proposal.md"])
        _make_change(root, "b", ["proposal.md"])
        update_meta(root, "a", {"last_touched": "2026-11-17T10:00:00+00:00"})
        update_meta(root, "b", {"last_touched": "2026-11-17T12:00:00+00:00"})
        assert foreground_slug(root) == "b"
        # switch 语义：touch 后前台切换
        update_meta(root, "a", {"last_touched": "2026-11-17T13:00:00+00:00"})
        assert foreground_slug(root) == "a"


def test_update_meta_merges_and_preserves():
    """meta 合并更新：覆盖同名键、保留其余键；目录不存在时创建。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        write_meta(root, "a", "docs/x-design.md")
        update_meta(root, "a", {"mode": "fast", "last_touched": "2026-11-17T00:00:00+00:00"})
        data = json.loads((change_dir_of(root, "a") / META_FILENAME).read_text(encoding="utf-8"))
        assert data["design_doc"] == "docs/x-design.md"
        assert data["mode"] == "fast"
        assert data["created_at"]
        # write_meta 重复登记保留原 created_at（目录创建时间语义）
        first_created = data["created_at"]
        write_meta(root, "a", "docs/y-design.md")
        data2 = json.loads((change_dir_of(root, "a") / META_FILENAME).read_text(encoding="utf-8"))
        assert data2["created_at"] == first_created
        assert data2["design_doc"] == "docs/y-design.md"


def test_audit_artifacts_warnings():
    """工件审计：meta 损坏给警告；目录消失给警告；健康目录零警告。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        assert audit_artifacts(root, "missing") != []
        change = _make_change(root, "bad", [META_FILENAME])
        (change / META_FILENAME).write_text("{broken", encoding="utf-8")
        assert len(audit_artifacts(root, "bad")) == 1
        _make_change(root, "ok", ["proposal.md"])
        assert audit_artifacts(root, "ok") == []


# ---- migrate_legacy_state（v3.0 state 退役迁移） ----

def test_migrate_absent_state_is_noop():
    """无旧 state → 幂等 noop（migrated=False，零副作用）。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        report = migrate_legacy_state(root)
        assert report["migrated"] is False
        assert not (root / ".specpowers" / "runtime.json").exists()


def test_migrate_schema2_full_path():
    """schema 2 迁移：有目录条目 meta 齐全化、无目录条目丢弃、runtime 承接、.bak 留底。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        spec_dir = root / ".specpowers"
        spec_dir.mkdir(parents=True)
        _make_change(root, "alive", ["proposal.md"])
        write_meta(root, "alive", "docs/x-design.md")
        (spec_dir / "state.json").write_text(json.dumps({
            "schema": 2,
            "fallback_count": 2,
            "last_archive_ref": "abc1234",
            "features": {
                "alive": {"stage": "propose", "mode": "full", "execution_mode": "TDD",
                          "iteration_count": 1, "design_doc": "docs/x-design.md",
                          "created_at": "2026-01-01T00:00:00+00:00",
                          "last_touched": "2026-01-02T00:00:00+00:00"},
                "ghost": {"stage": "apply", "mode": "full", "execution_mode": "",
                          "iteration_count": 0, "design_doc": "", "created_at": "",
                          "last_touched": ""},
            },
        }, ensure_ascii=False), encoding="utf-8")
        report = migrate_legacy_state(root)
        assert report["migrated"] is True
        assert report["features_migrated"] == ["alive"]
        assert report["dropped"] == ["ghost"]
        meta = json.loads((change_dir_of(root, "alive") / META_FILENAME).read_text(encoding="utf-8"))
        assert meta["mode"] == "full"
        assert meta["execution_mode"] == "TDD"
        assert meta["design_doc"] == "docs/x-design.md"
        runtime = json.loads((spec_dir / "runtime.json").read_text(encoding="utf-8"))
        assert runtime == {"fallback_count": 2, "last_archive_ref": "abc1234"}
        assert (spec_dir / "state.json.bak").is_file()
        assert not (spec_dir / "state.json").is_file()


def test_migrate_schema1_flat_top_level():
    """schema 1 兼容：顶层扁平 feature 字段视作单条目迁移。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        spec_dir = root / ".specpowers"
        spec_dir.mkdir(parents=True)
        _make_change(root, "legacy", ["proposal.md", "tasks.md"])
        (spec_dir / "state.json").write_text(json.dumps({
            "schema": 1, "feature": "legacy", "stage": "apply", "mode": "full",
            "fallback_count": 1, "last_archive_ref": "",
        }), encoding="utf-8")
        report = migrate_legacy_state(root)
        assert report["features_migrated"] == ["legacy"]
        meta = json.loads((change_dir_of(root, "legacy") / META_FILENAME).read_text(encoding="utf-8"))
        assert meta["mode"] == "full"


def test_migrate_idempotent_second_run_skips():
    """迁移幂等：二次执行时 state.json 已不存在 → noop。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        spec_dir = root / ".specpowers"
        spec_dir.mkdir(parents=True)
        _make_change(root, "a", ["proposal.md"])
        (spec_dir / "state.json").write_text(json.dumps({
            "schema": 2, "fallback_count": 0, "last_archive_ref": "",
            "features": {"a": {"stage": "propose", "mode": "full"}},
        }), encoding="utf-8")
        assert migrate_legacy_state(root)["migrated"] is True
        report2 = migrate_legacy_state(root)
        assert report2["migrated"] is False


def test_migrate_corrupt_state_quarantined():
    """损坏 state：留底 corrupted-<时间戳>，报告标注 corrupted，不抛异常。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        spec_dir = root / ".specpowers"
        spec_dir.mkdir(parents=True)
        (spec_dir / "state.json").write_text("{broken", encoding="utf-8")
        report = migrate_legacy_state(root)
        assert report["migrated"] is True
        assert report["corrupted"] is True
        leftovers = list(spec_dir.glob("state.json.corrupted-*"))
        assert len(leftovers) == 1

