"""Tests for archive_auditor — openspec 归档编排 + 重复归档检测。

回归覆盖：
- prepare_openspec_archive 在 openspec CLI 不可用时应抛 FatalError（原 bug：
  FatalError 未导入，抛 NameError 而非预期的 FatalError）
- is_feature_archived 空 feature 防护

作者：005819 | 协作：GLM-5.2
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from specpowers_cli.bridge.modules import archive_auditor
from specpowers_cli.bridge.adapters import openspec
from specpowers_cli.bridge.core.errors import FatalError


def _create_temp_git_repo(tmp_path: Path) -> Path:
    """在 pytest tmp_path 下创建带提交的临时 git 仓库（会话级模板复制，约 10ms）。"""
    from tests._gitrepo import create_git_repo

    return create_git_repo(tmp_path / "archive-repo")


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


# ---- scenario_coverage：场景覆盖核查（v2.3.0，规范即验收标尺）----

def _make_change(root: Path, feature: str, spec_bodies: dict, tasks_md: str | None):
    """构造 openspec/changes/<feature>/ 目录：spec_bodies = {capability: spec 正文}。"""
    change = root / "openspec" / "changes" / feature
    for capability, body in spec_bodies.items():
        spec_dir = change / "specs" / capability
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "spec.md").write_text(body, encoding="utf-8")
    if tasks_md is not None:
        (change / "tasks.md").write_text(tasks_md, encoding="utf-8")
    return change


_SPEC_FULL = """## ADDED Requirements

### Requirement: order-flow
The system SHALL 处理订单流。

#### Scenario: 正常下单
- **WHEN** 用户提交有效订单
- **THEN** 订单创建成功

#### Scenario: 库存不足
- **WHEN** 商品库存为 0
- **THEN** 返回库存不足错误
"""


def test_scenario_coverage_full_covered(tmp_path):
    """每个 Scenario 都被任务「场景引用」行覆盖 → pass。"""
    tasks = (
        "### Task 1: 下单\n\n- [ ] 实现内容：x\n"
        "- 场景引用：正常下单——WHEN 用户提交有效订单 THEN 订单创建成功\n\n"
        "### Task 2: 库存\n\n- [ ] 实现内容：y\n"
        "- 场景引用：库存不足——WHEN 商品库存为 0 THEN 返回库存不足错误\n"
    )
    _make_change(tmp_path, "order", {"order": _SPEC_FULL}, tasks)
    result = archive_auditor.scenario_coverage(tmp_path, "order")
    assert result["status"] == "pass"
    assert result["total"] == 2 and result["covered"] == 2
    assert result["uncovered"] == []


def test_scenario_coverage_partial(tmp_path):
    """部分场景未被引用 → partial + 未覆盖清单。"""
    tasks = (
        "### Task 1: 下单\n\n- [ ] 实现内容：x\n"
        "- 场景引用：正常下单——WHEN 用户提交有效订单 THEN 订单创建成功\n"
    )
    _make_change(tmp_path, "order", {"order": _SPEC_FULL}, tasks)
    result = archive_auditor.scenario_coverage(tmp_path, "order")
    assert result["status"] == "partial"
    assert result["covered"] == 1 and result["total"] == 2
    assert result["uncovered"] == ["库存不足"]


def test_scenario_coverage_no_scenarios_fast(tmp_path):
    """fast 模式 delta 为验收清单（无 #### Scenario）→ pass 跳过。"""
    _make_change(tmp_path, "fast-fix", {"fast-fix": "## 验收清单\n\n- [ ] 编译通过\n"}, "### Task 1: fix\n")
    result = archive_auditor.scenario_coverage(tmp_path, "fast-fix")
    assert result["status"] == "pass" and result["total"] == 0


def test_scenario_coverage_change_dir_missing(tmp_path):
    """change 目录不存在（异常前置态）→ pass 跳过，不抛异常。"""
    result = archive_auditor.scenario_coverage(tmp_path, "ghost")
    assert result["status"] == "pass"


def test_scenario_coverage_tasks_missing(tmp_path):
    """有场景但 tasks.md 缺失 → no_tasks（异常产物提示，不阻断）。"""
    _make_change(tmp_path, "order", {"order": _SPEC_FULL}, None)
    result = archive_auditor.scenario_coverage(tmp_path, "order")
    assert result["status"] == "no_tasks"
    assert result["total"] == 2 and result["covered"] == 0


def test_scenario_coverage_multi_capability(tmp_path):
    """多 capability 场景聚合核查。"""
    spec_b = "## ADDED Requirements\n\n### Requirement: pay\nSHALL 支付。\n\n#### Scenario: 支付成功\n- **WHEN** 余额充足\n- **THEN** 扣款\n"
    tasks = (
        "### Task 1: 下单\n\n- 场景引用：正常下单 WHEN 用户提交有效订单 THEN 订单创建成功\n\n"
        "### Task 2: 支付\n\n- 场景引用：支付成功 WHEN 余额充足 THEN 扣款\n\n"
        "### Task 3: 库存\n\n- 场景引用：库存不足 WHEN 商品库存为 0 THEN 返回库存不足错误\n"
    )
    _make_change(tmp_path, "combo", {"order": _SPEC_FULL, "pay": spec_b}, tasks)
    result = archive_auditor.scenario_coverage(tmp_path, "combo")
    assert result["status"] == "pass" and result["total"] == 3


def test_scenario_coverage_loose_fallback(tmp_path):
    """宽松兜底：场景名不在「场景引用」行字段但在 tasks 正文出现 → 算覆盖。"""
    tasks = "### Task 1: 下单\n\n- [ ] 覆盖「正常下单」与「库存不足」两个场景的完整链路\n"
    _make_change(tmp_path, "order", {"order": _SPEC_FULL}, tasks)
    result = archive_auditor.scenario_coverage(tmp_path, "order")
    assert result["status"] == "pass"
