"""Tests for path_resolver — OpenSpec change 产物的动态路径解析。

验证：
- change 产物（proposal/spec/tasks）路径解析正确
- ensure_feature_locked feature 锁定（空值兜底）
"""

from pathlib import Path

from specpowers_cli.bridge.modules.path_resolver import (
    ensure_feature_locked,
)


def test_ensure_feature_locked_returns_existing():
    """有 feature 时原样返回。"""
    state = {"feature": "my-feature"}
    assert ensure_feature_locked(state) == "my-feature"


def test_ensure_feature_locked_empty_defaults_unnamed():
    """空 feature 返回 unnamed。"""
    assert ensure_feature_locked({}) == "unnamed"
    assert ensure_feature_locked({"feature": ""}) == "unnamed"
    assert ensure_feature_locked({"feature": "   "}) == "unnamed"


# ---- OpenSpec change 产物路径（路径 A）----

from specpowers_cli.bridge.modules.path_resolver import (
    resolve_change_dir,
    resolve_change_proposal,
    resolve_change_spec,
    resolve_change_tasks,
    resolve_openspec_change,
    resolve_openspec_archive_dir,
)


def test_resolve_change_dir(tmp_path):
    """change 目录解析到 openspec/changes/<feature>。"""
    p = resolve_change_dir(tmp_path, "login")
    assert p == tmp_path / "openspec" / "changes" / "login"


def test_resolve_change_proposal(tmp_path):
    """proposal.md 解析到 openspec/changes/<feature>/proposal.md。"""
    p = resolve_change_proposal(tmp_path, "login")
    assert p == tmp_path / "openspec" / "changes" / "login" / "proposal.md"


def test_resolve_change_spec(tmp_path):
    """delta spec 解析到 openspec/changes/<feature>/specs/<capability>/spec.md。"""
    p = resolve_change_spec(tmp_path, "login", "auth")
    assert p == tmp_path / "openspec" / "changes" / "login" / "specs" / "auth" / "spec.md"


def test_resolve_change_spec_capability_defaults_to_feature(tmp_path):
    """capability 为空时回退到 feature slug。"""
    p = resolve_change_spec(tmp_path, "login", "")
    assert "specs" in str(p)
    assert p.parent.name == "login"


def test_resolve_change_tasks(tmp_path):
    """tasks.md 解析到 openspec/changes/<feature>/tasks.md。"""
    p = resolve_change_tasks(tmp_path, "login")
    assert p == tmp_path / "openspec" / "changes" / "login" / "tasks.md"


def test_resolve_openspec_archive_dir(tmp_path):
    """归档目录解析到 openspec/changes/archive/。"""
    p = resolve_openspec_archive_dir(tmp_path)
    assert p == tmp_path / "openspec" / "changes" / "archive"


def test_resolve_change_spec_chinese_capability(tmp_path):
    """中文 capability 作为目录名（迭代场景）。"""
    p = resolve_change_spec(tmp_path, "登录-oauth", "登录")
    assert p == tmp_path / "openspec" / "changes" / "登录-oauth" / "specs" / "登录" / "spec.md"
