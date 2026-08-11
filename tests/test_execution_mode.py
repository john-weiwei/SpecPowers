"""执行方式（execution_mode）确定性层测试。

覆盖 build 阶段执行方式记录的完整链路：
- validate_execution_mode：合法值/非法值/fast 模式约束兜底
- set_execution_mode：写入 state.json execution_mode 字段
- facade record-execution-mode 子命令：通过 main() 端到端
- DEFAULT_STATE 含 execution_mode 字段；reset/archive 清空

背景：build.md 第二步声明「记录到 state.json（execution_mode 字段）」，
原实现仅在 prompt 声明、无确定性层落地，且 fast 模式禁 worktree/subagent
的约束纯靠 agent 自律。本测试覆盖把两者升级为确定性层硬校验后的行为。

作者：005819 | 协作：GLM-5.2
"""

import subprocess
from pathlib import Path

import pytest

from specpowers_cli.bridge.modules.mode_controller import (
    validate_execution_mode, set_execution_mode,
    VALID_EXECUTION_MODES, FAST_FORBIDDEN_MODES,
)
from specpowers_cli.bridge.core.fs_state import init_state, load_state, save_state


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


# ---------- set_execution_mode 单元测试 ----------

def test_set_execution_mode_writes_state(tmp_path: Path):
    """set_execution_mode 应把执行方式写入 state.json。"""
    root = tmp_path
    (root / ".specpowers").mkdir(exist_ok=True)
    state = init_state(root)

    set_execution_mode(root, state, "tdd")

    loaded = load_state(root)
    assert loaded["execution_mode"] == "tdd"


def test_set_execution_mode_normalizes_case(tmp_path: Path):
    """set_execution_mode 应把大写执行方式规范化为小写存盘。"""
    root = tmp_path
    (root / ".specpowers").mkdir(exist_ok=True)
    state = init_state(root)

    set_execution_mode(root, state, "Subagent")

    assert load_state(root)["execution_mode"] == "subagent"


def test_set_execution_mode_rejects_fast_subagent(tmp_path: Path):
    """fast 模式下 set_execution_mode 选 subagent 应抛 ValueError。"""
    root = tmp_path
    (root / ".specpowers").mkdir(exist_ok=True)
    state = init_state(root)
    state["mode"] = "fast"
    save_state(root, state)

    with pytest.raises(ValueError):
        set_execution_mode(root, state, "subagent")


def test_set_execution_mode_rejects_unknown(tmp_path: Path):
    """未知执行方式应抛 ValueError。"""
    root = tmp_path
    (root / ".specpowers").mkdir(exist_ok=True)
    state = init_state(root)

    with pytest.raises(ValueError):
        set_execution_mode(root, state, "random")


# ---------- DEFAULT_STATE 结构与生命周期清理 ----------

def test_default_state_has_execution_mode():
    """DEFAULT_STATE 必须含 execution_mode 字段（兑现 build.md 承诺）。"""
    from specpowers_cli.bridge.core.fs_state import DEFAULT_STATE
    assert "execution_mode" in DEFAULT_STATE
    assert DEFAULT_STATE["execution_mode"] == ""


def test_init_state_has_empty_execution_mode(tmp_path: Path):
    """init_state 后 execution_mode 应为空串。"""
    root = tmp_path
    (root / ".specpowers").mkdir(exist_ok=True)
    state = init_state(root)
    assert state["execution_mode"] == ""


def test_reset_state_clears_execution_mode(tmp_path: Path):
    """reset_state 应清空 execution_mode（新 feature 不继承旧执行方式）。"""
    from specpowers_cli.bridge.core.fs_state import reset_state
    root = tmp_path
    (root / ".specpowers").mkdir(exist_ok=True)
    state = init_state(root)
    state["execution_mode"] = "subagent"
    save_state(root, state)

    new_state = reset_state(root)
    assert new_state["execution_mode"] == ""


# ---------- facade record-execution-mode 子命令端到端 ----------

def _create_temp_git_repo(tmp_path: Path) -> Path:
    """在 pytest tmp_path 下创建带提交的临时 git 仓库。

    tmp_path 由 pytest 自动管理，测试结束自动清理，无需手动删除。
    """
    root = tmp_path / "exec-mode-repo"
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


def test_facade_record_execution_mode_success(tmp_path: Path):
    """facade record-execution-mode conductor 应成功并写入 state。"""
    from specpowers_cli.bridge.facade import main
    root = _create_temp_git_repo(tmp_path)
    (root / ".specpowers").mkdir(exist_ok=True)
    init_state(root)

    rc = main(["record-execution-mode", "conductor", "--root", str(root)])
    assert rc == 0
    assert load_state(root)["execution_mode"] == "conductor"


def test_facade_record_execution_mode_missing_arg(tmp_path: Path):
    """record-execution-mode 无参数应返回退出码 2。"""
    from specpowers_cli.bridge.facade import main
    root = _create_temp_git_repo(tmp_path)
    (root / ".specpowers").mkdir(exist_ok=True)
    init_state(root)

    rc = main(["record-execution-mode", "--root", str(root)])
    assert rc == 2


def test_facade_record_execution_mode_fast_rejects_subagent(tmp_path: Path):
    """fast 模式下 record-execution-mode subagent 应非 0 退出。"""
    from specpowers_cli.bridge.facade import main
    root = _create_temp_git_repo(tmp_path)
    (root / ".specpowers").mkdir(exist_ok=True)
    state = init_state(root)
    state["mode"] = "fast"
    save_state(root, state)

    rc = main(["record-execution-mode", "subagent", "--root", str(root)])
    assert rc != 0
    # 执行方式不应被写入
    assert load_state(root)["execution_mode"] == ""


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
