"""Tests for facade — 全局选项解析与子命令分发。

回归覆盖：
- --root <path> 与 --root=<path> 两种形式都能被正确解析
- --root 必须从 requirement 中移除，不能被 " ".join(args) 拼进 feature 名
  （原 bug：brainstorm "需求" --root . 导致 state.feature 变成
  「洗护到家黄牛充值限制---root」一类的脏数据）

作者：005819 | 协作：GLM-5.2
"""

import subprocess
from pathlib import Path

import pytest

from specpowers_cli.bridge.facade import _extract_global_options, main
from specpowers_cli.bridge.core.fs_state import load_state


def _create_temp_git_repo(tmp_path: Path) -> Path:
    """在 pytest tmp_path 下创建带提交的临时 git 仓库。

    tmp_path 由 pytest 自动管理，测试结束自动清理，无需手动删除。
    """
    root = tmp_path / "facade-repo"
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
    subprocess.run(["git", "add", "."], cwd=str(root), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"],
        cwd=str(root), capture_output=True, check=True,
    )
    return root


def _seed_ready_state(root: Path) -> None:
    """把 state 推进到 ready 并补齐 brainstorm 前置产物，使 brainstorm 合法。"""
    from specpowers_cli.bridge.core.fs_state import save_state, DEFAULT_STATE
    state = dict(DEFAULT_STATE)
    state["stage"] = "ready"
    save_state(root, state)
    # brainstorm 前置检查要求 constitution.md 存在
    (root / ".specpowers" / "constitution.md").write_text("# Constitution", encoding="utf-8")


# ---------- _extract_global_options 单元测试 ----------

def test_extract_root_space_form_removes_both_tokens():
    """--root <path> 形式：root 与 path 都从剩余参数移除。"""
    root_arg, remaining = _extract_global_options(["需求", "--root", "."])
    assert root_arg == "."
    assert remaining == ["需求"]


def test_extract_root_equals_form():
    """--root=<path> 形式：等号后作为值。"""
    root_arg, remaining = _extract_global_options(["需求", "--root=./repo"])
    assert root_arg == "./repo"
    assert remaining == ["需求"]


def test_extract_no_root_returns_none_and_unchanged():
    """没有 --root 时，root_arg 为 None 且剩余参数不变。"""
    root_arg, remaining = _extract_global_options(["需求", "更多", "描述"])
    assert root_arg is None
    assert remaining == ["需求", "更多", "描述"]


def test_extract_root_without_value_is_left_untouched():
    """--root 出现在末尾无值时：不算 --root 选项，原样保留（避免静默吞参）。"""
    root_arg, remaining = _extract_global_options(["需求", "--root"])
    assert root_arg is None
    assert remaining == ["需求", "--root"]


# ---------- 通过 main() 的回归测试 ----------

def test_brainstorm_root_not_merged_into_feature(tmp_path: Path):
    """回归：brainstorm 带正确参数时 --root 不得污染 feature 名。"""
    root = _create_temp_git_repo(tmp_path)
    _seed_ready_state(root)

    rc = main(["brainstorm", "洗护到家黄牛充值限制", "--root", str(root)])
    assert rc == 0

    feature = load_state(root)["feature"]
    # feature 应等于纯需求 normalize 结果，绝不含 root/--root/路径字符
    assert feature == "洗护到家黄牛充值限制"
    assert "--root" not in feature
    assert "root" not in feature.lower()
    assert "." not in feature


def test_brainstorm_root_equals_form_not_merged_into_feature(tmp_path: Path):
    """回归：--root=<path> 形式同样不得污染 feature 名。"""
    root = _create_temp_git_repo(tmp_path)
    _seed_ready_state(root)

    rc = main(["brainstorm", "--root=" + str(root), "登录模块重构"])
    assert rc == 0

    feature = load_state(root)["feature"]
    assert feature == "登录模块重构"
    assert "--root" not in feature
    assert "root" not in feature.lower()
