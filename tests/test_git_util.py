"""Tests for bridge.core.git_util — safe git subprocess wrapper."""

import tempfile
import subprocess
from pathlib import Path

# package installed via pip - no sys.path needed

from specpowers_cli.bridge.core.git_util import (
    git_exists, is_git_repo, git_ref_of, diff_stat,
    ls_tree_head, monthly_avg_commits, is_detached_head,
)
from specpowers_cli.bridge.dispatcher import normalize_feature


def _create_temp_git_repo(tmp_path: Path) -> Path:
    """在 pytest tmp_path 下创建带提交的临时 git 仓库。

    tmp_path 由 pytest 自动管理，测试结束自动清理。
    """
    root = tmp_path / "git-util-repo"
    root.mkdir()

    subprocess.run(["git", "init"], cwd=str(root), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(root), capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(root), capture_output=True
    )

    (root / "README.md").write_text("# Test")
    subprocess.run(["git", "add", "-A"], cwd=str(root), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial commit"],
        cwd=str(root), capture_output=True, check=True
    )

    (root / "src").mkdir(exist_ok=True)
    (root / "src" / "main.py").write_text("print('hello')")
    subprocess.run(["git", "add", "-A"], cwd=str(root), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "add src/main.py"],
        cwd=str(root), capture_output=True, check=True
    )

    return root


def test_init():
    """Test basic imports and module initialization."""
    assert True


def test_git_exists():
    """git should be available in test environment."""
    result = git_exists()
    assert result is True, "git should be installed"


def test_is_git_repo(tmp_path):
    """A git repo should be detected as such."""
    root = _create_temp_git_repo(tmp_path)
    result = is_git_repo(root)
    assert result is True, "temp git repo should be detected"


def test_is_not_git_repo():
    """Temp directory (non-git) should not be detected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = is_git_repo(Path(tmpdir))
        assert result is False, "non-git dir should not be detected"


def test_git_ref_of(tmp_path):
    """Should return a valid short hash."""
    root = _create_temp_git_repo(tmp_path)
    ref = git_ref_of(root)
    assert len(ref) >= 7, f"git ref should be at least 7 chars, got: '{ref}'"
    assert len(ref) <= 40, f"git ref too long: {ref}"


def test_ls_tree_head(tmp_path):
    """Should return list of top-level directories."""
    root = _create_temp_git_repo(tmp_path)
    dirs = ls_tree_head(root)
    assert isinstance(dirs, list)
    # Our temp repo has 'src' directory
    assert "src" in dirs, f"Expected 'src' in {dirs}"


def test_diff_stat(tmp_path):
    """Should return diff stat string."""
    root = _create_temp_git_repo(tmp_path)
    result = diff_stat(root, "HEAD~1")
    assert isinstance(result, str)
    assert len(result) > 0, "diff stat should not be empty"


def test_monthly_avg_commits(tmp_path):
    """Should return a positive integer."""
    root = _create_temp_git_repo(tmp_path)
    result = monthly_avg_commits(root)
    assert isinstance(result, int)
    assert result >= 0


def test_normalize_feature():
    """Test feature name normalization."""
    assert normalize_feature("") == "unnamed"
    assert normalize_feature("   ") == "unnamed"
    assert normalize_feature("fix login button") == "fix-login-button"
    assert normalize_feature("修复登录按钮") != ""
    assert len(normalize_feature("a" * 100)) <= 45


def test_is_detached_head_normal_branch(tmp_path):
    """正常分支状态下应返回 False（不是 detached HEAD）。

    回归：原实现逻辑反转，恒返回 False，无法区分 detached 与非 detached。
    作者：005819 | 协作：GLM-5.2
    """
    root = _create_temp_git_repo(tmp_path)
    assert is_detached_head(root) is False


def test_is_detached_head_detached(tmp_path):
    """进入 detached HEAD 后应返回 True。

    回归测试：原实现用 try/except 判断，但 detached HEAD 时
    `git rev-parse --abbrev-ref HEAD` 返回 "HEAD"（exit 0，不报错），
    导致恒走 try 分支 return False，门禁完全失效。
    作者：005819 | 协作：GLM-5.2
    """
    root = _create_temp_git_repo(tmp_path)
    head_ref = git_ref_of(root)
    # 进入 detached HEAD：checkout 具体 commit
    subprocess.run(
        ["git", "checkout", "-q", head_ref],
        cwd=str(root), capture_output=True, check=True,
    )
    assert is_detached_head(root) is True
