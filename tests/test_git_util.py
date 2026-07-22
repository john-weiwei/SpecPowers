"""Tests for bridge.core.git_util — safe git subprocess wrapper."""

import os
import sys
import tempfile
import subprocess
from pathlib import Path

# Add bridge to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.core.git_util import (
    git_exists, is_git_repo, git_ref_of, diff_stat,
    ls_tree_head, monthly_avg_commits,
)
from bridge.dispatcher import normalize_feature


def _create_temp_git_repo():
    """Create a temporary git repo for testing with a few commits."""
    tmpdir = tempfile.mkdtemp()
    root = Path(tmpdir)

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


def test_is_git_repo():
    """A git repo should be detected as such."""
    root = _create_temp_git_repo()
    result = is_git_repo(root)
    assert result is True, "temp git repo should be detected"


def test_is_not_git_repo():
    """Temp directory (non-git) should not be detected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = is_git_repo(Path(tmpdir))
        assert result is False, "non-git dir should not be detected"


def test_git_ref_of():
    """Should return a valid short hash."""
    root = _create_temp_git_repo()
    ref = git_ref_of(root)
    assert len(ref) >= 7, f"git ref should be at least 7 chars, got: '{ref}'"
    assert len(ref) <= 40, f"git ref too long: {ref}"


def test_ls_tree_head():
    """Should return list of top-level directories."""
    root = _create_temp_git_repo()
    dirs = ls_tree_head(root)
    assert isinstance(dirs, list)
    # Our temp repo has 'src' directory
    assert "src" in dirs, f"Expected 'src' in {dirs}"

