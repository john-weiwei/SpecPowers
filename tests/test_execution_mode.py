"""执行方式（execution_mode）确定性层测试 — v3.0 状态机推导化版。

覆盖 build 阶段执行方式记录的完整链路（v3.0 落点从 state.json 换为
change 目录 meta 的 execution_mode 字段）：
- validate_execution_mode：合法值/非法值/fast 模式约束兜底（签名不变）
- set_execution_mode(root, slug, mode)：写 meta execution_mode；
  fast 判定从 meta.mode 读（缺省 full）
- execution_mode 生命周期：随 change 目录生灭（无全局 state 写点）
- facade record-execution-mode 子命令：单活跃缺省前台 / 多活跃未指名拒绝 /
  --feature 指名 / fast 拒绝，通过 main() 端到端

背景：build.md 第二步声明「记录执行方式」，fast 模式禁 worktree/subagent
的约束从纯 prompt 自律升级为确定性层硬校验。v3.0 起 execution_mode 天然
随目录生灭——meta 不含该键即「无执行方式」，等价旧版 reset 后清空语义。

作者：005819 | 协作：GLM-5.3 | 日期：2026-11-17
"""

from pathlib import Path
import shutil

import pytest

from specpowers_cli.bridge.modules.mode_controller import (
    validate_execution_mode, set_execution_mode,
    VALID_EXECUTION_MODES, FAST_FORBIDDEN_MODES,
)
from tests.helpers_v3 import make_change, make_triple, read_meta_of


# ---------- validate_execution_mode 单元测试 ----------

def test_validate_all_four_modes_pass_in_full():
    """full 模式下四种执行方式均合法。"""
    for mode in VALID_EXECUTION_MODES:
        ok, hint = validate_execution_mode(mode, "full")
        assert ok is True, f"{mode} 应在 full 模式合法，hint={hint}"
        assert hint == ""


def test_validate_unknown_mode_rejected():
    """未知执行方式应被拒。"""
    ok, hint = validate_execution_mode("pair-programming", "full")
    assert ok is False
    assert "未知" in hint or "合法值" in hint


def test_validate_empty_mode_rejected():
    """空执行方式应被拒（避免静默通过）。"""
    ok, hint = validate_execution_mode("", "full")
    assert ok is False


def test_validate_case_insensitive():
    """大小写不敏感：TDD / Conductor 等应被规范化接受。"""
    ok, _ = validate_execution_mode("TDD", "full")
    assert ok is True
    ok, _ = validate_execution_mode(" Conductor ", "full")
    assert ok is True


def test_validate_fast_forbids_worktree_and_subagent():
    """fast 模式禁止 worktree/subagent（核心兜底）。"""
    for mode in FAST_FORBIDDEN_MODES:
        ok, hint = validate_execution_mode(mode, "fast")
        assert ok is False, f"fast 模式应禁止 {mode}"
        assert "fast" in hint


def test_validate_fast_allows_conductor_and_tdd():
    """fast 模式允许 conductor/tdd。"""
    for mode in ("conductor", "tdd"):
        ok, hint = validate_execution_mode(mode, "fast")
        assert ok is True, f"fast 模式应允许 {mode}，hint={hint}"


def test_fast_constraint_hint_mentions_upgrade():
    """fast 禁用 worktree/subagent 的提示应引导用户升级流程。"""
    ok, hint = validate_execution_mode("subagent", "fast")
    assert "升级" in hint or "完整流程" in hint


# ---------- set_execution_mode 单元测试（v3.0：写 meta，第二参数是 slug） ----------

def test_set_execution_mode_writes_meta(tmp_path: Path):
    """set_execution_mode 应把执行方式写入目标需求的 meta。"""
    root = tmp_path
    make_triple(root, "feat-demo")
    assert "execution_mode" not in read_meta_of(root, "feat-demo")  # 前置：尚未记录

    result = set_execution_mode(root, "feat-demo", "tdd")

    assert result == "tdd"  # 返回规范化后的值
    assert read_meta_of(root, "feat-demo")["execution_mode"] == "tdd"


def test_set_execution_mode_normalizes_case(tmp_path: Path):
    """set_execution_mode 应把大写执行方式规范化为小写存盘。"""
    root = tmp_path
    make_triple(root, "feat-demo")

    result = set_execution_mode(root, "feat-demo", "Subagent")

    assert result == "subagent"
    assert read_meta_of(root, "feat-demo")["execution_mode"] == "subagent"


def test_set_execution_mode_rejects_fast_subagent(tmp_path: Path):
    """fast 模式（meta.mode=fast）下选 subagent 应抛 ValueError 且不落盘。"""
    root = tmp_path
    make_triple(root, "feat-demo", meta={"mode": "fast"})

    with pytest.raises(ValueError) as exc_info:
        set_execution_mode(root, "feat-demo", "subagent")
    assert "fast" in str(exc_info.value)
    # 拒绝时 meta 不得留下 execution_mode（部分写入即漂移）
    assert "execution_mode" not in read_meta_of(root, "feat-demo")


def test_set_execution_mode_rejects_unknown(tmp_path: Path):
    """未知执行方式应抛 ValueError（提示含合法值清单）。"""
    root = tmp_path
    make_triple(root, "feat-demo")

    with pytest.raises(ValueError) as exc_info:
        set_execution_mode(root, "feat-demo", "random")
    assert "合法值" in str(exc_info.value)
    assert "execution_mode" not in read_meta_of(root, "feat-demo")


def test_set_execution_mode_reads_mode_from_meta_default_full(tmp_path: Path):
    """fast 判定从 meta.mode 读：无 mode 键时按 full（fast 禁用项也放行）。"""
    root = tmp_path
    # meta 不含 mode 键（三件套齐全的常规需求）
    make_triple(root, "feat-demo")
    # worktree 属 fast 禁用集合——能落盘即证明 current_mode 取的默认 full
    set_execution_mode(root, "feat-demo", "worktree")
    assert read_meta_of(root, "feat-demo")["execution_mode"] == "worktree"


# ---------- execution_mode 生命周期（v3.0：随 change 目录生灭） ----------

def test_meta_without_execution_mode_reads_empty(tmp_path: Path):
    """meta 无 execution_mode 键时读出为空（新需求天然无执行方式）。

    v3.0 无「新需求清空 execution_mode」的独立写点——字段天然随目录
    生灭，未记录过的需求 meta 中就没有该键。
    """
    root = tmp_path
    make_triple(root, "feat-demo", meta={"mode": "fast"})  # meta 存在但无 execution_mode
    meta = read_meta_of(root, "feat-demo")
    assert meta.get("execution_mode", "") == ""


def test_execution_mode_dies_with_change_dir(tmp_path: Path):
    """change 目录删除后执行方式随之消失（无全局 state 残留）。

    等价旧版「reset/archive 清空 execution_mode」语义：v3.0 归档/删除
    目录即需求终结，execution_mode 无法从已消失的目录泄漏到新需求。
    """
    root = tmp_path
    change = make_triple(root, "feat-demo")
    set_execution_mode(root, "feat-demo", "conductor")
    assert read_meta_of(root, "feat-demo")["execution_mode"] == "conductor"

    shutil.rmtree(change)
    assert read_meta_of(root, "feat-demo") == {}


# ---------- facade record-execution-mode 子命令端到端 ----------

def test_facade_record_execution_mode_single_active_defaults_foreground(tmp_path: Path):
    """单活跃需求时 record-execution-mode 缺省写入前台需求 meta。"""
    from specpowers_cli.bridge.facade import main
    root = tmp_path
    make_triple(root, "feat-demo")

    rc = main(["record-execution-mode", "conductor", "--root", str(root)])

    assert rc == 0
    assert read_meta_of(root, "feat-demo")["execution_mode"] == "conductor"


def test_facade_record_execution_mode_multi_active_requires_feature(tmp_path: Path):
    """多活跃需求未指名 --feature 应拒绝退出（防记错需求）。"""
    from specpowers_cli.bridge.facade import main
    root = tmp_path
    make_triple(root, "feat-a")
    make_triple(root, "feat-b")

    rc = main(["record-execution-mode", "tdd", "--root", str(root)])

    assert rc != 0
    # 两需求的 meta 均不得被写入
    assert "execution_mode" not in read_meta_of(root, "feat-a")
    assert "execution_mode" not in read_meta_of(root, "feat-b")


def test_facade_record_execution_mode_feature_option_targets_slug(tmp_path: Path):
    """多活跃时 --feature 指名目标 slug，只写入指定需求的 meta。"""
    from specpowers_cli.bridge.facade import main
    root = tmp_path
    make_triple(root, "feat-a")
    make_triple(root, "feat-b")

    rc = main(["record-execution-mode", "tdd", "--feature", "feat-b", "--root", str(root)])

    assert rc == 0
    assert read_meta_of(root, "feat-b")["execution_mode"] == "tdd"
    assert "execution_mode" not in read_meta_of(root, "feat-a")


def test_facade_record_execution_mode_no_active_rejected(tmp_path: Path):
    """无活跃需求时 record-execution-mode 应拒绝退出。"""
    from specpowers_cli.bridge.facade import main
    root = tmp_path
    (root / ".specpowers").mkdir(exist_ok=True)  # 无任何 change 目录

    rc = main(["record-execution-mode", "tdd", "--root", str(root)])

    assert rc != 0


def test_facade_record_execution_mode_missing_arg(tmp_path: Path):
    """record-execution-mode 无执行方式参数应返回退出码 2。"""
    from specpowers_cli.bridge.facade import main
    root = tmp_path
    make_triple(root, "feat-demo")

    rc = main(["record-execution-mode", "--root", str(root)])

    assert rc == 2


def test_facade_record_execution_mode_fast_rejects_subagent(tmp_path: Path):
    """fast 模式（meta.mode=fast）下 record-execution-mode subagent 应非 0 退出。"""
    from specpowers_cli.bridge.facade import main
    root = tmp_path
    make_triple(root, "feat-demo", meta={"mode": "fast"})

    rc = main(["record-execution-mode", "subagent", "--root", str(root)])

    assert rc != 0
    # 执行方式不应被写入 meta
    assert "execution_mode" not in read_meta_of(root, "feat-demo")
