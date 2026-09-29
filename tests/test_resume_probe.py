"""Tests for bridge.modules.resume_probe — SessionStart 只读探测（v2.3.0）。

覆盖 probe_resume 四分支短路顺序 + active_changes 工件判定 + 防阻断：
- 零活跃状态 → 空串（零噪音，借鉴 Comet resume-probe 低噪声定位）
- 活跃 stage → 阶段续跑指引（auto_base.json 存在时切 auto 断点提示）
- fast 进行中 → 验收提示
- 工件存在但 state 未接管 → 接管提示（state.json 每人独立而工件共享的
  跨机协作场景）
- state.json 损坏 → 不抛异常（探测绝不阻断会话启动）

作者：005819 | 协作：GLM-5.3
"""

from pathlib import Path

from specpowers_cli.bridge.core.fs_state import DEFAULT_STATE, save_state
from specpowers_cli.bridge.modules.resume_probe import active_changes, probe_resume


def _write_state(root: Path, **overrides) -> None:
    """落盘一份 state.json（DEFAULT_STATE 打补丁）。"""
    state = dict(DEFAULT_STATE)
    state.update(overrides)
    save_state(root, state)


def _make_change(root: Path, name: str = "demo", artifact: str = "proposal.md") -> None:
    """构造一个活跃 change 目录（默认含 proposal.md）。"""
    d = root / "openspec" / "changes" / name
    d.mkdir(parents=True, exist_ok=True)
    if artifact:
        if artifact == "specs":
            (d / "specs" / "demo").mkdir(parents=True, exist_ok=True)
        else:
            (d / artifact).write_text("# artifact", encoding="utf-8")


def test_probe_silent_when_fresh_project(tmp_path):
    """全新项目（无 .specpowers、无 openspec）→ 空串，零噪音。"""
    assert probe_resume(tmp_path) == ""


def test_probe_silent_after_normal_finish(tmp_path):
    """正常收口态（stage=ready、mode=full、无活跃 change）→ 空串。"""
    _write_state(tmp_path, stage="ready", mode="full", feature="demo")
    assert probe_resume(tmp_path) == ""


def test_probe_pipeline_stage_hint(tmp_path):
    """人工流水线活跃：按 stage 给续跑指引（与状态机合法流转对齐）。"""
    for stage, fragment in [
        ("explore", "/specpowers-propose"),
        ("propose", "/specpowers-propose"),
        ("apply", "/specpowers-apply"),
        ("archive", "/specpowers-archive"),
    ]:
        root = tmp_path / stage
        root.mkdir()
        _write_state(root, stage=stage, mode="full", feature="demo")
        msg = probe_resume(root)
        assert "demo" in msg, f"stage={stage} 提示缺 feature: {msg}"
        assert fragment in msg, f"stage={stage} 提示缺续跑命令: {msg}"
        assert "auto 无人值守" not in msg, f"无 auto_base 不应出 auto 断点提示: {msg}"


def test_probe_auto_breakpoint(tmp_path):
    """auto_base.json 存在 → 按 auto 断点提示（重入 /specpowers-auto 续跑）。"""
    _write_state(tmp_path, stage="apply", mode="full", feature="demo")
    (tmp_path / ".specpowers" / "auto_base.json").write_text("{}", encoding="utf-8")
    msg = probe_resume(tmp_path)
    assert "auto 无人值守任务中断" in msg
    assert "/specpowers-auto" in msg


def test_probe_round_note_for_iteration(tmp_path):
    """迭代轮（iteration_count ≥ 1）提示带 Round 注记。"""
    _write_state(tmp_path, stage="propose", mode="full", feature="demo", iteration_count=2)
    msg = probe_resume(tmp_path)
    assert "Round 2" in msg


def test_probe_fast_mode_hint(tmp_path):
    """fast 模式进行中 → 验收提示（编码完成后 /specpowers-apply）。"""
    _write_state(tmp_path, stage="ready", mode="fast", feature="demo")
    msg = probe_resume(tmp_path)
    assert "fast 优化模式进行中" in msg
    assert "/specpowers-apply" in msg


def test_probe_adopt_when_state_ready_but_changes_exist(tmp_path):
    """state 已回 ready 但 change 未归档 → 接管提示（跨机协作场景）。"""
    _write_state(tmp_path, stage="ready", mode="full", feature="")
    _make_change(tmp_path, "demo")
    msg = probe_resume(tmp_path)
    assert "未归档的 change" in msg
    assert "demo" in msg
    assert "/specpowers-propose" in msg


def test_probe_adopt_when_state_missing(tmp_path):
    """本机无 state.json（新 clone）但工件已提交 → 接管提示。"""
    _make_change(tmp_path, "shared-feature")
    msg = probe_resume(tmp_path)
    assert "shared-feature" in msg


def test_probe_survives_corrupt_state(tmp_path):
    """state.json 损坏 → 不抛异常（有活跃 change 时降级为接管提示）。"""
    (tmp_path / ".specpowers").mkdir()
    (tmp_path / ".specpowers" / "state.json").write_text("{broken", encoding="utf-8")
    assert probe_resume(tmp_path) == ""
    _make_change(tmp_path, "demo")
    assert "demo" in probe_resume(tmp_path)


def test_active_changes_filters_and_sorts(tmp_path):
    """active_changes：archive 快照与无工件目录排除；多 change 按名排序。"""
    _make_change(tmp_path, "beta")
    _make_change(tmp_path, "alpha", artifact="tasks.md")
    _make_change(tmp_path, "gamma", artifact="specs")
    # archive 快照目录 → 排除
    (tmp_path / "openspec" / "changes" / "archive" / "old").mkdir(parents=True)
    # 无任何三件套工件的目录 → 排除
    (tmp_path / "openspec" / "changes" / "empty-dir").mkdir()
    assert active_changes(tmp_path) == ["alpha", "beta", "gamma"]


def test_active_changes_empty_when_no_dir(tmp_path):
    """无 openspec/changes 目录 → 空列表。"""
    assert active_changes(tmp_path) == []
