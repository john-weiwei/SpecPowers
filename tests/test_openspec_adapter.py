"""Tests for openspec adapter — _verify_archived 精确匹配回归 + to_scenario 死函数防回潮。"""

import inspect
from pathlib import Path

from specpowers_cli.bridge.adapters.openspec import _verify_archived
import specpowers_cli.bridge.adapters.openspec as openspec_module


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


def test_to_scenario_dead_code_removed():
    """防回潮：to_scenario 死函数不得回归——brief.md 从不是注册产物，
    其残留 docstring（自称 explore 阶段产出 brief.md 却无路径约定）曾诱导
    模型把 brief.md 写到项目根目录（用户实际踩坑）。explore 产出已由
    设计文档（docs/specpowers/design/）承担。"""
    assert not hasattr(openspec_module, "to_scenario")
    source = Path(inspect.getsourcefile(openspec_module)).read_text(encoding="utf-8")
    assert "def to_scenario" not in source
    # brief 参数形态不得回归（模块 docstring 的历史注记文字除外，不查裸 "brief"）
    assert "brief: " not in source
    assert "brief=" not in source
