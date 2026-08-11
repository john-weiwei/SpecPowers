"""Archive auditor — archive 归档相关校验与执行。

保留的职责（dispatcher 实际在用）：
- is_feature_archived：重复归档检测
- merge_check_detect：合体后校验触发判定
- change_summary_input：生成 diff --stat 供 agent 撰写归档摘要
- prepare_openspec_archive：委托 openspec archive 执行归档
"""

from pathlib import Path

from specpowers_cli.bridge.core.errors import FatalError
from specpowers_cli.bridge.core.git_util import (
    log_merges, log_authors_count, log_grep_feature,
    diff_stat,
)


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
