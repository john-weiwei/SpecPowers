"""Archive auditor — archive 归档相关校验与执行。

保留的职责（dispatcher 实际在用）：
- is_feature_archived：重复归档检测
- merge_check_detect：合体后校验触发判定
- change_summary_input：生成 diff --stat 供 agent 撰写归档摘要
- prepare_openspec_archive：委托 openspec archive 执行归档
- scenario_coverage：场景覆盖核查（spec Scenario ↔ tasks 场景引用，v2.3.0）
"""

import re
from pathlib import Path

from specpowers_cli.bridge.core.errors import FatalError
from specpowers_cli.bridge.core.git_util import (
    log_merges, log_authors_count, log_grep_feature,
    diff_stat,
)

# delta spec 中 Scenario 标题的匹配模式（OpenSpec delta 格式：#### Scenario: <名>）
_SCENARIO_HEADING_RE = re.compile(r"^####\s+Scenario:\s*(.+?)\s*$", re.MULTILINE)
# tasks.md 场景引用行（propose 契约固定字段：- 场景引用：<Scenario 名 + WHEN-THEN 原文摘录>）
_SCENARIO_REF_RE = re.compile(r"场景引用[:：](.*)")


def is_feature_archived(root: Path, feature: str) -> bool:
    """Check if a feature already has an archive commit.

    Searches git log for commits containing 'specpowers.*<feature>'.
    空 feature 直接返回 False，避免匹配所有含 specpowers 的 commit。
    """
    if not feature or not feature.strip():
        return False
    commits = log_grep_feature(root, feature)
    return len(commits) > 0


def merge_check_detect(root: Path, last_archive_ref: str | None) -> bool:
    """Detect if post-merge validation is needed.

    Checks two signals:
    1. Merge commits since last_archive_ref
    2. Multiple authors since last_archive_ref

    If last_archive_ref is empty, check the whole history.
    """
    since_ref = last_archive_ref if last_archive_ref else None

    # Signal 1: merge commits
    merges = log_merges(root, since_ref)
    if merges:
        return True

    # Signal 2: multiple authors
    author_count = log_authors_count(root, since_ref)
    if author_count > 1:
        return True

    return False


def change_summary_input(root: Path, base: str | None = None) -> str:
    """Generate git diff --stat as input for natural language summary.

    The agent uses this to produce a 3-5 sentence description.
    """
    return diff_stat(root, base)


def scenario_coverage(root: Path, feature: str) -> dict:
    """核查 delta spec 的每个 Scenario 是否至少被一个任务的「场景引用」覆盖。

    「规范即验收标尺」（OpenSpec 第三原则）的确定性兜底：propose 契约要求
    tasks.md 每个 Task 带「场景引用」字段，propose 第七步自审核为提示词层
    自查，本函数在 archive 归档前把「每个 Scenario 至少被一个任务引用」
    升级为可校验的结构断言。

    匹配规则（宽松，防误报）：Scenario 名出现在任一「场景引用：」行文本中
    即算覆盖；引用行没写全名时再查 tasks.md 全文兜底（迭代轮可能把引用写进
    其他字段或自由措辞）。

    Returns:
        {"total": int, "covered": int, "uncovered": [str], "status": str}。
        status 取值：
        - "pass"      全覆盖（或无 Scenario——fast 模式 delta 为验收清单 /
                      change 尚无 delta，均跳过校验）
        - "partial"   存在未覆盖场景（提示不阻断，archive 只转人工不打回）
        - "no_tasks"  有场景但 tasks.md 缺失（异常产物，同样提示不阻断）

    作者：005819 | 协作：GLM-5.3
    """
    change_dir = root / "openspec" / "changes" / feature
    if not change_dir.exists():
        return {"total": 0, "covered": 0, "uncovered": [], "status": "pass"}

    # 收集全部 capability 的 delta spec 场景名（change 可含多个 capability）
    scenarios: list[str] = []
    for spec_path in sorted(change_dir.glob("specs/*/spec.md")):
        text = spec_path.read_text(encoding="utf-8")
        scenarios.extend(m.strip() for m in _SCENARIO_HEADING_RE.findall(text))
    if not scenarios:
        return {"total": 0, "covered": 0, "uncovered": [], "status": "pass"}

    tasks_path = change_dir / "tasks.md"
    if not tasks_path.exists():
        return {
            "total": len(scenarios), "covered": 0,
            "uncovered": list(scenarios), "status": "no_tasks",
        }

    tasks_text = tasks_path.read_text(encoding="utf-8")
    ref_lines = [m.group(1) for m in _SCENARIO_REF_RE.finditer(tasks_text)]
    uncovered = [
        name for name in scenarios
        if not any(name in line for line in ref_lines) and name not in tasks_text
    ]
    return {
        "total": len(scenarios),
        "covered": len(scenarios) - len(uncovered),
        "uncovered": uncovered,
        "status": "pass" if not uncovered else "partial",
    }


def prepare_openspec_archive(root: Path, feature: str, state: dict,
                             skip_validation: bool = False) -> dict:
    """编排 OpenSpec 归档：调 openspec archive（产物已是 OpenSpec 格式，零转换）。

    full + fast 统一入口，供 dispatcher._handle_archive 调用。
    步骤：
    1. is_openspec_available 校验 CLI 可用（不可用拒绝）
    2. ensure_openspec_workspace 确保目标项目有 openspec/ 目录
    3. archive_change 调 openspec archive <feature> --yes --json 归档

    产物（proposal/specs/tasks）由前面阶段增量写入 openspec/changes/<feature>/，
    本函数只负责归档，无转换。

    归档成功后的产物：
    - openspec/specs/<capability>/spec.md（合并后的主规格）
    - openspec/changes/archive/YYYY-MM-DD-<feature>/（change 快照）

    Args:
        root: 项目根目录。
        feature: feature slug，作为 change 名。
        state: state.json dict（保留参数兼容，路径 A 下不再用于转换）。
        skip_validation: True 则 openspec archive 加 --no-validate。

    Returns:
        openspec archive 的 JSON 结果 dict。

    Raises:
        FatalError: 任一步骤失败（CLI 不可用 / 归档失败）。
    """
    from specpowers_cli.bridge.adapters.openspec import (
        is_openspec_available, ensure_openspec_workspace, archive_change,
    )

    # Duty 5 前置：CLI 不可用直接拒绝（不降级）
    if not is_openspec_available(root):
        raise FatalError(
            "openspec CLI 不可用。归档强依赖 openspec archive 命令，"
            "请确认 openspec 已全局安装（pip/node）并在 PATH 中。"
        )

    # 确保目标项目有 openspec/ 工作区目录
    ensure_openspec_workspace(root)

    # 调用 openspec archive 归档（内置 delta 合并 + change 移动）
    # 产物已是 OpenSpec 格式，无需转换
    archive_result = archive_change(root, feature, skip_validation=skip_validation)

    return archive_result
