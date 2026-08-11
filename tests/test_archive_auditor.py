"""Tests for archive_auditor — openspec 归档编排 + 重复归档检测。

回归覆盖：
- prepare_openspec_archive 在 openspec CLI 不可用时应抛 FatalError（原 bug：
  FatalError 未导入，抛 NameError 而非预期的 FatalError）
- is_feature_archived 空 feature 防护

作者：005819 | 协作：GLM-5.2
"""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from specpowers_cli.bridge.modules import archive_auditor
from specpowers_cli.bridge.adapters import openspec
from specpowers_cli.bridge.core.errors import FatalError


def _create_temp_git_repo(tmp_path: Path) -> Path:
    """在 pytest tmp_path 下创建带提交的临时 git 仓库。

    tmp_path 由 pytest 自动管理，测试结束自动清理，无需手动删除。
    """
    root = tmp_path / "archive-repo"
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


def test_prepare_openspec_archive_raises_fatalerror_when_cli_unavailable(tmp_path):
    """回归：openspec CLI 不可用时 prepare_openspec_archive 应抛 FatalError。

    原 bug：archive_auditor.py 未导入 FatalError，调用 raise FatalError(...) 时
    抛 NameError 而非 FatalError，导致 facade 的统一异常处理（依赖 exit_code 属性）
    无法识别为致命错误，返回码和错误信息均不正确。

    作者：005819 | 协作：GLM-5.2
    """
    root = _create_temp_git_repo(tmp_path)

    # mock openspec 源模块的 is_openspec_available（archive_auditor 函数内延迟导入）
    with patch.object(openspec, "is_openspec_available", return_value=False):
        # 应抛 FatalError（exit_code=2），而非 NameError
        with pytest.raises(FatalError) as exc_info:
            archive_auditor.prepare_openspec_archive(root, "test-feature", {})

    # 验证是 FatalError 类型（有 exit_code 属性 = 2）
    assert exc_info.value.exit_code == 2
    assert "openspec" in str(exc_info.value).lower()


def test_prepare_openspec_archive_not_nameerror(tmp_path):
    """回归补充：确保修复后不再抛 NameError。

    原 bug 的直接症状是 NameError: name 'FatalError' is not defined，
    此测试确保该症状不再出现（FatalError 已正确导入）。
    """
    root = _create_temp_git_repo(tmp_path)

    with patch.object(openspec, "is_openspec_available", return_value=False):
        try:
            archive_auditor.prepare_openspec_archive(root, "test-feature", {})
            pytest.fail("应抛异常但未抛")
        except NameError as e:
            pytest.fail(f"不应再抛 NameError（FatalError 未导入的旧 bug）: {e}")
        except FatalError:
            pass  # 预期行为


def test_is_feature_archived_empty_and_whitespace():
    """空/空白 feature 应返回 False，避免匹配所有 specpowers commit。"""
    # 此函数不依赖 git 仓库，空 feature 在 log_grep_feature 调用前就短路返回
    assert archive_auditor.is_feature_archived(Path("/nonexistent"), "") is False
    assert archive_auditor.is_feature_archived(Path("/nonexistent"), "   ") is False
