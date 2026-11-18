"""Tests for bridge.modules.resume_probe — SessionStart 只读探测（v3.0 全推导）。

v3.0.0 状态机推导化改写：state.json 退役，probe_resume / sticky_note 全部
从 openspec/changes/ 工件推导（active_slugs 目录扫描 + derive_stage +
iteration_count_of + foreground_slug）。测试现场从 save_state 换为
helpers_v3 的 make_change / make_triple 工件工厂，断言换推导预期：
- make_triple（三件套齐、无勾选）→ stage="propose"；tasks 有勾选 → "apply"
- 仅 meta 登记 → "explore"；meta mode=fast → "fast"

覆盖（分支短路顺序 + 活跃判定 + 防阻断）：
- 零活跃（全新项目 / 仅归档快照）→ 空串（零噪音，借鉴 Comet resume-probe 低噪声定位）
- 活跃 stage → 阶段续跑指引（auto_base/<slug>.json 存在时 auto 断点提示优先）
- fast 态 → 验收提示
- 多需求 → 前台排首行；sticky ≤3 全列、>3 前台+后台一行汇总
- 遗留损坏 state.json → 推导不受影响、探测绝不抛异常阻断（零 state 读取）

随双真相源退役而删除的旧用例（分支已不存在，勿恢复）：
- 「工件存在但 state 未接管」跨机接管分支 ×2（目录即活跃，跨机天然一致）
- 对账警告透传断言（读后对账钩子随 state 退役，探测不再输出警告行）

作者：005819 | 协作：GLM-5.3
"""

from pathlib import Path

from tests.helpers_v3 import make_change, make_triple

from specpowers_cli.bridge.modules.resume_probe import (
    _capability_names,
    _scope_prefixes,
    active_changes,
    probe_resume,
    sticky_note,
)

# meta last_touched 时间戳（前台排序的确定性现场；last_touched 最大者为前台）
_T_EARLY = "2026-11-17T00:00:01+00:00"
_T_LATE = "2026-11-17T00:00:02+00:00"


def _write_corrupt_legacy_state(root: Path) -> None:
    """落盘一份损坏的遗留 state.json（v3.0 推导逻辑应完全无视它）。"""
    (root / ".specpowers").mkdir(parents=True, exist_ok=True)
    (root / ".specpowers" / "state.json").write_text("{broken", encoding="utf-8")


def _make_archive_snapshot(root: Path, slug: str = "old") -> None:
    """构造归档快照目录（changes/archive/<slug>/，不属活跃清单）。"""
    d = root / "openspec" / "changes" / "archive" / slug
    d.mkdir(parents=True)
    (d / "proposal.md").write_text("# archived", encoding="utf-8")


def test_probe_silent_when_fresh_project(tmp_path):
    """全新项目（无 .specpowers、无 openspec）→ 空串，零噪音。"""
    assert probe_resume(tmp_path) == ""


def test_probe_silent_when_only_archive_snapshot(tmp_path):
    """仅剩归档快照（正常收口后）→ 空串，零噪音。

    v3.0 活跃权威 = changes/ 非归档目录扫描；archive/ 快照不在清单内，
    「全部归档后的收口态」等价于零活跃。
    """
    _make_archive_snapshot(tmp_path, "done-feature")
    assert probe_resume(tmp_path) == ""


def test_probe_pipeline_stage_hint(tmp_path):
    """活跃流水线：按推导 stage 给续跑指引（explore/propose/apply 三态）。

    现场构造（v3.0 工件推导）：
    - explore：仅 meta 登记（探索收口待提案）
    - propose：三件套齐且 tasks 无勾选
    - apply：三件套齐且 tasks 活动区有勾选
    """
    cases = [
        ("explore", lambda r: make_change(r, "demo", meta={"design_doc": "docs/d.md"})),
        ("propose", lambda r: make_triple(r, "demo")),
        ("apply", lambda r: make_triple(r, "demo", tasks_text="### T: x\n\n- [x] a\n")),
    ]
    for stage, build in cases:
        root = tmp_path / stage
        root.mkdir()
        build(root)
        msg = probe_resume(root)
        assert "demo" in msg, f"stage={stage} 提示缺 feature: {msg}"
        assert f"当前阶段 {stage}" in msg, f"stage={stage} 提示阶段不符: {msg}"
        assert "续跑：" in msg, f"stage={stage} 提示缺续跑指引: {msg}"
        assert "auto 无人值守" not in msg, f"无 auto_base 不应出 auto 断点提示: {msg}"


def test_probe_auto_breakpoint(tmp_path):
    """auto_base/<slug>.json 存在 → auto 断点提示优先于阶段指引（重入 /specpowers-auto）。"""
    make_triple(tmp_path, "demo", tasks_text="### T: x\n\n- [x] a\n")
    base_dir = tmp_path / ".specpowers" / "auto_base"
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "demo.json").write_text("{}", encoding="utf-8")
    msg = probe_resume(tmp_path)
    assert "auto 无人值守任务中断" in msg
    assert "/specpowers-auto" in msg
    assert "断点阶段 apply" in msg


def test_probe_round_note_derived_from_artifacts(tmp_path):
    """迭代轮从工件推导（tasks.md「## Round N」小节）→ 提示带 Round 注记。"""
    make_triple(tmp_path, "demo", tasks_text="## Round 2\n### T: x\n\n- [ ] a\n")
    msg = probe_resume(tmp_path)
    assert "Round 2" in msg


def test_probe_fast_mode_hint(tmp_path):
    """meta mode=fast → fast 态验收提示（编码完成后 /specpowers-apply）。"""
    make_change(tmp_path, "demo", meta={"mode": "fast"})
    msg = probe_resume(tmp_path)
    assert "fast 优化模式进行中" in msg
    assert "/specpowers-apply" in msg


def test_probe_foreground_first_among_multi(tmp_path):
    """多活跃需求：前台（meta last_touched 最大者）排首行并标注（前台）。"""
    make_change(tmp_path, "alpha", meta={"last_touched": _T_EARLY})
    make_change(tmp_path, "beta", meta={"last_touched": _T_LATE})
    msg = probe_resume(tmp_path)
    first_line = msg.splitlines()[0]
    assert "beta（前台）" in first_line, f"前台应排首行: {msg}"
    assert msg.count("（前台）") == 1, f"仅前台标注一次: {msg}"
    assert "alpha" in msg, f"后台活跃需求仍应列出: {msg}"


def test_probe_caps_many_active_with_summary(tmp_path):
    """v3.1.0 展示封顶：活跃 >5 时前台 + 前 4 + 一行后台汇总（hook 注入控量）。

    probe 行数 ∝ 活跃需求数无理论上限，hook 输出进每会话首条消息；
    封顶后未展示需求以汇总行列出（带名提示 --feature 指定）。
    """
    # 7 个活跃需求：beta 前台（last_touched 最大），其余 last_touched 递增排列
    slugs = ["f1", "f2", "f3", "f4", "f5", "f6"]
    for idx, slug in enumerate(slugs):
        make_change(tmp_path, slug, meta={"last_touched": _T_EARLY})
    make_change(tmp_path, "beta", meta={"last_touched": _T_LATE})
    msg = probe_resume(tmp_path)
    lines = msg.splitlines()
    # 7 个活跃 → 展示 5 行 + 1 行汇总 = 6 行（未封顶时是 7 行）
    assert len(lines) == 6, f"应封顶为 5 行展示 + 1 行汇总: {msg}"
    assert "beta（前台）" in lines[0], f"前台仍应排首行: {msg}"
    assert "另有 2 个后台活跃需求" in lines[-1], f"汇总行应列出未展示需求: {msg}"
    assert "--feature" in lines[-1], f"汇总行应提示显式指名: {msg}"


def test_probe_survives_legacy_corrupt_state(tmp_path):
    """遗留 state.json 损坏 → 推导不受影响（v3.0 探测零 state 读取，绝不阻断）。"""
    _write_corrupt_legacy_state(tmp_path)
    # 无活跃 change：损坏遗留文件不产生噪音
    assert probe_resume(tmp_path) == ""
    # 有活跃 change：正常给续跑指引（工件为唯一权威）
    make_triple(tmp_path, "demo")
    assert "demo" in probe_resume(tmp_path)


def test_active_changes_filters_and_sorts(tmp_path):
    """active_changes（v3.0 即 active_slugs 别名）：归档快照与空目录排除，按名排序。"""
    make_change(tmp_path, "beta", ["proposal.md"])
    make_change(tmp_path, "alpha", ["tasks.md"])
    make_change(tmp_path, "gamma", ["specs/"])
    # archive 快照目录 → 排除
    _make_archive_snapshot(tmp_path, "old")
    # 无任何三件套/meta 工件的目录 → 排除
    (tmp_path / "openspec" / "changes" / "empty-dir").mkdir()
    assert active_changes(tmp_path) == ["alpha", "beta", "gamma"]


def test_active_changes_empty_when_no_dir(tmp_path):
    """无 openspec/changes 目录 → 空列表。"""
    assert active_changes(tmp_path) == []


def test_active_changes_includes_meta_only_dir(tmp_path):
    """仅含 .specpowers-meta.json 的目录视为活跃 change（explore 收口即登记）。"""
    make_change(tmp_path, "explore-done", meta={"design_doc": "docs/d.md"})
    assert active_changes(tmp_path) == ["explore-done"]


# ---------- sticky_note 会话粘滞锚点行（v2.7.0 引入；v3.0 全推导） ----------


def test_sticky_note_active_pipeline_with_anchors(tmp_path):
    """apply 态 + specs/tasks 齐备 → 锚点行含 slug/stage/Round/capability/修改范围。"""
    make_triple(
        tmp_path, "demo",
        tasks_text=(
            "<!-- 修改范围：src/order/**, src/mq/** -->\n"
            "## Round 2\n### T: x\n\n- [x] a\n"
        ),
        meta={"design_doc": "docs/d.md"},
    )
    (tmp_path / "openspec" / "changes" / "demo" / "specs" / "order-retry").mkdir(parents=True)
    (tmp_path / "openspec" / "changes" / "demo" / "specs" / "mq-send").mkdir(parents=True)
    msg = sticky_note(tmp_path)
    assert "demo（前台）" in msg
    assert "apply" in msg
    assert "Round 2" in msg
    assert "capability=mq-send,order-retry" in msg
    assert "修改范围=src/order/**, src/mq/**" in msg
    # 注释闭合符不得泄漏进修改范围取值（tasks.md 声明行在 HTML 注释块内）
    assert "-->" not in msg.split("修改范围=", 1)[1].split(" —— ")[0]
    assert "/specpowers-archive" in msg
    assert "/specpowers-maintain reset" in msg


def test_sticky_note_first_round_without_round_note(tmp_path):
    """首轮（工件无任何 Round 痕迹）锚点行不带 Round 注记。"""
    make_triple(tmp_path, "demo")
    msg = sticky_note(tmp_path)
    assert "demo" in msg
    assert "propose" in msg
    assert "Round" not in msg


def test_sticky_note_degrades_without_artifacts(tmp_path):
    """仅 meta 登记（explore 收口未提案）→ 降级为不含 capability/修改范围的简版。"""
    make_change(tmp_path, "demo", meta={"design_doc": "docs/d.md"})
    msg = sticky_note(tmp_path)
    assert "demo" in msg
    assert "capability=" not in msg
    assert "修改范围=" not in msg


def test_sticky_note_silent_when_all_archived(tmp_path):
    """无活跃需求（全部已归档）→ 空串零注入。"""
    _make_archive_snapshot(tmp_path, "done-feature")
    assert sticky_note(tmp_path) == ""


def test_sticky_note_silent_on_fresh_project(tmp_path):
    """全新项目 → 空串零噪音。"""
    assert sticky_note(tmp_path) == ""


def test_sticky_note_fast_mode_hint(tmp_path):
    """meta mode=fast → 验收/放弃提示（粘滞期间编码由用户完成）。"""
    make_change(tmp_path, "demo", meta={"mode": "fast"})
    msg = sticky_note(tmp_path)
    assert "fast 优化模式进行中" in msg
    assert "/specpowers-apply" in msg
    assert "/specpowers-maintain reset --feature demo" in msg


def test_sticky_note_survives_legacy_corrupt_state(tmp_path):
    """遗留 state.json 损坏 → 零活跃时空串；有活跃需求时锚点照常推导（绝不阻断）。"""
    _write_corrupt_legacy_state(tmp_path)
    assert sticky_note(tmp_path) == ""
    make_triple(tmp_path, "demo")
    assert "demo" in sticky_note(tmp_path)


def test_sticky_note_summarizes_when_more_than_three(tmp_path):
    """>3 个活跃需求：前台排首行 + 其余按名排序全列 2 个，最后一行汇总（控 token）。

    前台 = meta last_touched 最大者（change-d）；其余活跃按名字序展示，
    超出上限的 change-c 进汇总行。
    """
    for i, slug in enumerate(("change-a", "change-b", "change-c", "change-d"), start=1):
        make_change(tmp_path, slug, meta={"last_touched": f"2026-11-17T00:00:0{i}+00:00"})
    msg = sticky_note(tmp_path)
    lines = msg.splitlines()
    assert len(lines) == 4, f"应为 3 行锚点 + 1 行汇总：{msg}"
    assert "活跃需求 change-d（前台）" in lines[0]
    assert "活跃需求 change-a" in lines[1]
    assert "活跃需求 change-b" in lines[2]
    assert "另有 1 个后台活跃需求：change-c" in lines[3]
    assert "--feature" in lines[3]


def test_scope_prefixes_truncation(tmp_path):
    """修改范围声明超 120 字符截断加省略号；缺声明行返回空串。"""
    feature_dir = tmp_path / "openspec" / "changes" / "demo"
    feature_dir.mkdir(parents=True)
    long_decl = ",".join(f"src/module-{i:03d}/**" for i in range(30))
    (feature_dir / "tasks.md").write_text(
        f"<!-- 修改范围：{long_decl} -->\n# t\n", encoding="utf-8",
    )
    got = _scope_prefixes(tmp_path, "demo")
    assert len(got) == 120
    assert got.endswith("…")
    # 无声明行 → 空串
    (feature_dir / "tasks.md").write_text("# t\n", encoding="utf-8")
    assert _scope_prefixes(tmp_path, "demo") == ""


def test_capability_names_sorted_and_missing(tmp_path):
    """capability 取 specs/ 下一级目录并排序；目录缺失返回空列表。"""
    (tmp_path / "openspec" / "changes" / "demo" / "specs" / "beta").mkdir(parents=True)
    (tmp_path / "openspec" / "changes" / "demo" / "specs" / "alpha").mkdir(parents=True)
    assert _capability_names(tmp_path, "demo") == ["alpha", "beta"]
    assert _capability_names(tmp_path, "missing") == []
