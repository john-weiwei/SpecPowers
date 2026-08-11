"""Tests for merge_check_detect — uses temp git repos."""

import subprocess
from pathlib import Path

import pytest

from specpowers_cli.bridge.modules.archive_auditor import merge_check_detect, is_feature_archived
from specpowers_cli.bridge.core.git_util import git_ref_of


def _create_temp_git_repo(tmp_path: Path) -> Path:
    """在 pytest tmp_path 下创建一个带两次提交的临时 git 仓库。

    tmp_path 由 pytest 自动管理，测试结束后自动清理，无需手动删除。
    """
    root = tmp_path / "test-repo"
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

    (root / "file.txt").write_text("commit 1")
    subprocess.run(["git", "add", "-A"], cwd=str(root), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(root), capture_output=True, check=True
    )

    (root / "file.txt").write_text("commit 2")
    subprocess.run(["git", "add", "-A"], cwd=str(root), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "second"],
        cwd=str(root), capture_output=True, check=True
    )

    return root


def test_merge_check_detect_single_branch(tmp_path):
    """Single branch should not detect merge."""
    root = _create_temp_git_repo(tmp_path)
    ref = git_ref_of(root)
    result = merge_check_detect(root, ref)
    assert result is False  # same ref = 0 commits in range


def test_merge_check_detect_with_none_ref(tmp_path):
    """With None ref, should check full history."""
    root = _create_temp_git_repo(tmp_path)
    result = merge_check_detect(root, None)
    assert isinstance(result, bool)
    # Single author, no merge commits → should be False
    assert result is False


def test_is_feature_archived_nonexistent(tmp_path):
    """Non-existent feature should not be archived."""
    root = _create_temp_git_repo(tmp_path)
    result = is_feature_archived(root, "nonexistent-feature-xyz-12345")
    assert result is False


def test_is_feature_archived_empty_feature(tmp_path):
    """空 feature 应返回 False，避免匹配所有 specpowers commit。"""
    root = _create_temp_git_repo(tmp_path)
    assert is_feature_archived(root, "") is False
    assert is_feature_archived(root, "   ") is False


def test_is_feature_archived_exact_match(tmp_path):
    """已归档 feature 名精确匹配（正常场景）。"""
    root = _create_temp_git_repo(tmp_path)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "specpowers(full): 用户登录 — archive"],
        cwd=str(root), capture_output=True, check=True,
    )
    assert is_feature_archived(root, "用户登录") is True


def test_is_feature_archived_no_substring_false_positive(tmp_path):
    """子串误匹配修复：'用户登录' 不应匹配到 '用户登录-oauth' 的 commit。

    迭代场景核心保护：团队 B 的 feature '用户登录-oauth' 不应被
    '用户登录' 的归档检测误判为已归档（二者是不同迭代）。
    """
    root = _create_temp_git_repo(tmp_path)
    # 模拟已归档 v2（用户登录-oauth）
    subprocess.run(
        ["git", "commit", "--allow-empty",
         "-m", "specpowers(full): 用户登录-oauth — archive"],
        cwd=str(root), capture_output=True, check=True,
    )
    # 查 v1 名（用户登录）应返回 False（只有 v2 的 commit，不是 v1）
    assert is_feature_archived(root, "用户登录") is False
    # 查 v2 名（用户登录-oauth）应返回 True
    assert is_feature_archived(root, "用户登录-oauth") is True


def test_is_feature_archived_english_no_substring_false_positive(tmp_path):
    """英文 feature 子串保护：'login' 不应匹配 'login-oauth'。"""
    root = _create_temp_git_repo(tmp_path)
    subprocess.run(
        ["git", "commit", "--allow-empty",
         "-m", "specpowers(fast): login-oauth — v2"],
        cwd=str(root), capture_output=True, check=True,
    )
    assert is_feature_archived(root, "login") is False
    assert is_feature_archived(root, "login-oauth") is True
