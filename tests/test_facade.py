"""Tests for facade — 全局选项解析与子命令分发。

回归覆盖：
- --root <path> 与 --root=<path> 两种形式都能被正确解析
- --root 必须从 requirement 中移除，不能被 " ".join(args) 拼进 feature 名
  （原 bug：explore "需求" --root . 导致 state.feature 变成
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
    """把 state 推进到 ready 并补齐 explore 前置产物，使 explore 合法。"""
    from specpowers_cli.bridge.core.fs_state import save_state, DEFAULT_STATE
    state = dict(DEFAULT_STATE)
    state["stage"] = "ready"
    save_state(root, state)
    # explore 前置检查要求 constitution.md 存在
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


def test_extract_root_without_value_rejected(capsys):
    """--root 出现在末尾无值时：直接报错退出，不得把 "--root" 拼进 requirement。"""
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        _extract_global_options(["需求", "--root"])
    assert exc_info.value.code == 2
    assert "--root requires a path value" in capsys.readouterr().err


def test_extract_root_value_cannot_be_next_option(capsys):
    """--root 后紧跟另一选项时视为缺值：报错退出而非吞参。"""
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        _extract_global_options(["--root", "--force", "需求"])
    assert exc_info.value.code == 2
    assert "--root requires a path value" in capsys.readouterr().err


# ---------- 通过 main() 的回归测试 ----------

def test_explore_root_not_merged_into_feature(tmp_path: Path):
    """回归：explore 带正确参数时 --root 不得污染 feature 名。"""
    root = _create_temp_git_repo(tmp_path)
    _seed_ready_state(root)

    rc = main(["explore", "洗护到家黄牛充值限制", "--root", str(root)])
    assert rc == 0

    feature = load_state(root)["feature"]
    # feature 应等于纯需求 normalize 结果，绝不含 root/--root/路径字符
    assert feature == "洗护到家黄牛充值限制"
    assert "--root" not in feature
    assert "root" not in feature.lower()
    assert "." not in feature


def test_explore_root_equals_form_not_merged_into_feature(tmp_path: Path):
    """回归：--root=<path> 形式同样不得污染 feature 名。"""
    root = _create_temp_git_repo(tmp_path)
    _seed_ready_state(root)

    rc = main(["explore", "--root=" + str(root), "登录模块重构"])
    assert rc == 0

    feature = load_state(root)["feature"]
    assert feature == "登录模块重构"
    assert "--root" not in feature
    assert "root" not in feature.lower()


# ---- gate --base 参数注入拒绝（安全修复回归）----

def test_gate_rejects_option_like_base(tmp_path, capsys):
    """--base 值以 '-' 开头（git 选项注入，如 --output=）必须被拒绝。"""
    root = _create_temp_git_repo(tmp_path)
    rc = main(["gate", "--root", str(root), "--base", "--output=/tmp/evil"])
    assert rc == 2
    assert "invalid --base value" in capsys.readouterr().err


def test_gate_rejects_metachar_base(tmp_path, capsys):
    """--base 值含空格等非法字符时被拒绝。"""
    root = _create_temp_git_repo(tmp_path)
    rc = main(["gate", "--root", str(root), "--base", "HEAD; rm -rf /"])
    assert rc == 2


def test_gate_accepts_normal_ref_base(tmp_path):
    """--base 正常 git ref（如 HEAD~1）照常放行。"""
    root = _create_temp_git_repo(tmp_path)
    # HEAD~1 需要仓库至少 2 个提交，补一个
    (root / "CHANGE.md").write_text("# Change", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(root), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "second"],
        cwd=str(root), capture_output=True, check=True,
    )
    rc = main(["gate", "--root", str(root), "--base", "HEAD~1"])
    assert rc == 0
