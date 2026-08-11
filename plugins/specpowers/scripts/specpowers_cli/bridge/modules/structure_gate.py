"""Structure gate — extract signals from build diff vs baseline.

Three signal types:
1. New top-level directories not in baseline
2. Unknown dependencies introduced
3. New architecture layer patterns outside baseline

信号去重：同一 new_top_dir/new_dep/new_src_pattern 只报一次，避免
大量文件变更时产生重复噪声。
"""

from pathlib import Path

from specpowers_cli.bridge.modules.baseline_scanner import load_baseline
from specpowers_cli.bridge.modules.dep_manifest import guess_dep_type


def extract_signals(tree_diff: str, baseline: dict) -> list[str]:
    """Extract structure gate signals from a git diff.

    Args:
        tree_diff: Output of git diff --stat (or similar).
        baseline: The baseline dict from baseline.json.

    Returns:
        List of signal strings describing deviations（已去重）。
        Empty list = clean, no structure violations.
    """
    if not baseline:
        return []

    # 用 set 收集信号，避免同名信号因多文件变更而重复
    signals: set[str] = set()
    top_dirs = set(baseline.get("top_dirs", []))
    known_deps = set(baseline.get("deps", {}).keys())
    src_patterns = set(baseline.get("src_patterns", []))

    if not tree_diff:
        return []

    diff_lines = tree_diff.split("\n")

    # 从 diff 解析文件路径
    # git diff --stat 输出格式：
    #   " path/to/file | N +++---"   ← 文件行（含 | 分隔）
    #   " N files changed, ..."      ← 汇总行（无 | 分隔）
    # 用 "|" 是否存在区分，避免把汇总行误当文件路径解析（否则会污染 new_top_dir 信号）
    new_files = set()
    for line in diff_lines:
        line = line.strip()
        if not line or "|" not in line:
            continue
        filepath = line.split("|")[0].strip()
        if not filepath:
            continue
        new_files.add(filepath)

    # 1. 新增顶层目录
    for fp in new_files:
        top_dir = fp.split("/")[0]
        if top_dir not in top_dirs and not top_dir.startswith("."):
            signals.add(f"new_top_dir:{top_dir}")

    # 2. 未知的依赖文件变更（依赖清单统一来自 dep_manifest）
    for fp in new_files:
        fname = fp.split("/")[-1] if "/" in fp else fp
        dep_type = guess_dep_type(fname)
        if dep_type and dep_type not in known_deps:
            signals.add(f"new_dep:{dep_type}")

    # 3. src/ 下出现新的架构层目录
    for fp in new_files:
        parts = fp.split("/")
        if len(parts) >= 2 and parts[0] == "src":
            second_level = parts[1]
            if second_level not in src_patterns:
                signals.add(f"new_src_pattern:{second_level}")

    return sorted(signals)
