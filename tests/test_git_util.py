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
    """在 pytest tmp_path 下创建带两次提交的临时 git 仓库（模板复制 + 一次追加提交）。

    tmp_path 由 pytest 自动管理，测试结束自动清理。
    """
    from tests._gitrepo import create_git_repo, commit_all

    root = create_git_repo(tmp_path / "git-util-repo")
    # 保持原结构语义：第二个提交新增 src/main.py（供 diff_stat HEAD~1 与
    # ls-tree 目录用例消费），与模板自带的 README 提交共同构成两提交历史
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
    commit_all(root, "add src/main.py")

    return root


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


# ---- diff_name_only（v2.3.0，任务级修改范围比对依赖）----

def test_diff_name_only_working_tree(tmp_path):
    """未提交改动（已跟踪文件）相对 HEAD 的文件清单。"""
    from tests._gitrepo import commit_all

    from specpowers_cli.bridge.core.git_util import diff_name_only

    root = _create_temp_git_repo(tmp_path)
    (root / "README.md").write_text("# changed", encoding="utf-8")
    assert diff_name_only(root) == ["README.md"]


def test_diff_name_only_base_range(tmp_path):
    """base..HEAD 提交区间的文件清单（与 diff_stat 同口径）。"""
    from specpowers_cli.bridge.core.git_util import diff_name_only

    root = _create_temp_git_repo(tmp_path)
    # _create_temp_git_repo 构造两提交历史：README + src/main.py
    files = diff_name_only(root, "HEAD~1")
    assert "src/main.py" in files


def test_diff_name_only_chinese_path_not_escaped(tmp_path):
    """回归：core.quotepath=off 保证中文路径原样输出。

    git 默认 quotepath 会把中文路径转义为反斜杠八进制串并加引号，
    修改范围前缀比对将全部失效。
    作者：005819 | 协作：GLM-5.3
    """
    from tests._gitrepo import commit_all

    from specpowers_cli.bridge.core.git_util import diff_name_only

    root = _create_temp_git_repo(tmp_path)
    (root / "src" / "订单服务.java").write_text("class X {}", encoding="utf-8")
    commit_all(root, "add chinese path")
    files = diff_name_only(root, "HEAD~1")
    assert "src/订单服务.java" in files


def test_diff_name_only_empty_when_clean(tmp_path):
    """无改动时返回空列表。"""
    from specpowers_cli.bridge.core.git_util import diff_name_only

    root = _create_temp_git_repo(tmp_path)
    assert diff_name_only(root) == []
