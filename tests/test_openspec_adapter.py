"""Tests for openspec adapter — _verify_archived 精确匹配回归。"""

from pathlib import Path

from specpowers_cli.bridge.adapters.openspec import _verify_archived


def test_verify_archived_exact_name_match(tmp_path):
    """日期前缀去除后精确比对：login 不得误命中 sso-login 的归档目录。"""
    archive_dir = tmp_path / "openspec" / "changes" / "archive"
    (archive_dir / "2026-09-16-sso-login").mkdir(parents=True)
    (archive_dir / "2026-09-16-login").mkdir()

    result = _verify_archived(tmp_path, "login")
    assert result is not None
    assert result["archivedAs"] == "2026-09-16-login"

    result_sso = _verify_archived(tmp_path, "sso-login")
    assert result_sso is not None
    assert result_sso["archivedAs"] == "2026-09-16-sso-login"


def test_verify_archived_missing_returns_none(tmp_path):
    """归档目录不存在目标 change 时返回 None（触发 FatalError 兜底）。"""
    assert _verify_archived(tmp_path, "no-such-change") is None

    archive_dir = tmp_path / "openspec" / "changes" / "archive"
    (archive_dir / "2026-09-16-other").mkdir(parents=True)
    assert _verify_archived(tmp_path, "no-such-change") is None
