"""Structure gate — extract signals from build diff vs baseline.

Three signal types:
1. New top-level directories not in baseline
2. Unknown dependencies introduced
3. New architecture layer patterns outside baseline

信号去重：同一 new_top_dir/new_dep/new_src_pattern 只报一次，避免
大量文件变更时产生重复噪声。

任务级修改范围比对（v2.3.0，借鉴 Comet 的任务级路径门禁）：propose 在
tasks.md 顶部注释块声明「修改范围：」路径前缀，apply 门禁比对实际 git diff，
越界文件转人工裁决——把「转人工」从"新结构"细化到"越界改动"。
"""

import re
from pathlib import Path

from specpowers_cli.bridge.modules.baseline_scanner import load_baseline
from specpowers_cli.bridge.modules.dep_manifest import guess_dep_type

# 流水线自身工件的豁免前缀（借鉴 Comet 把流程目录放行的做法）：
# 这些路径的变更属于流水线正常产物，永不判越界
SCOPE_EXEMPT_PREFIXES = ("openspec/", ".specpowers/", "docs/specpowers/")


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
    # 解析规则（按序处理三类边缘格式）：
    #   1. rsplit 取最后一个 "|" 之前的部分 → 兼容文件名本身含 "|"
    #   2. rename 行 → 还原完整新路径（见下方分支说明）
    #   3. git 对特殊字符路径自动加引号 → strip 掉两侧引号
    new_files = set()
    for line in diff_lines:
        line = line.strip()
        if not line or "|" not in line:
            continue
        filepath = line.rsplit("|", 1)[0].strip()
        if not filepath:
            continue
        if "=>" in filepath:
            # rename 行两种形态：
            #   折叠写法 "src/{old => new}/f.py"：完整新路径 = 前缀 + 新段 + 后缀，
            #     原实现取 "=>" 之后丢掉前缀，导致 new_top_dir 误报且 src 层判定失效
            #   整体写法 "old_dir => new_dir"（无公共前后缀）：新路径即 "=>" 之后
            if "{" in filepath and "}" in filepath:
                brace_start = filepath.index("{")
                brace_end = filepath.rindex("}")
                prefix = filepath[:brace_start]
                new_seg = filepath[brace_start + 1:brace_end].split("=>", 1)[1].strip()
                filepath = prefix + new_seg + filepath[brace_end + 1:]
            else:
                filepath = filepath.split("=>", 1)[1].strip()
        filepath = filepath.strip('"')
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
    # 契约：比对对象是 baseline["src_patterns"] = baseline 扫描时 src/ 的
    # 一级子目录名（baseline_scanner._scan_src_patterns 收集 item.name），
    # 两侧深度必须一致，否则平铺/嵌套布局都会误报
    for fp in new_files:
        parts = fp.split("/")
        if len(parts) >= 2 and parts[0] == "src":
            second_level = parts[1]
            if second_level not in src_patterns:
                signals.add(f"new_src_pattern:{second_level}")

    return sorted(signals)


# ---- 任务级修改范围比对（scope gate）----

def _normalize_scope_path(p: str) -> str:
    """归一化路径前缀：统一正斜杠、去引号与首尾斜杠，便于跨平台比对。"""
    return p.strip().strip('"').strip("'").replace("\\", "/").strip("/")


def parse_scope_declaration(tasks_md: str) -> list[str]:
    """解析 tasks.md 顶部注释块内的「修改范围：」声明行。

    契约（prompts/propose.md 第五步）：声明必须写在顶部 HTML 注释块内，
    格式 `修改范围：<逗号/顿号/分号/空白分隔的路径前缀>`。仅扫描注释块
    内部，任务描述等正文出现同名字样不会误匹配。无声明返回空列表。

    作者：005819 | 协作：GLM-5.3
    """
    in_comment = False
    for line in tasks_md.splitlines():
        stripped = line.strip()
        if "<!--" in stripped:
            in_comment = True
        if in_comment:
            match = re.search(r"修改范围[:：]\s*(.*)", stripped)
            if match:
                raw = match.group(1).replace("-->", "").strip()
                parts = re.split(r"[,，;；、\s]+", raw)
                return [_normalize_scope_path(p) for p in parts if _normalize_scope_path(p)]
        if "-->" in stripped:
            in_comment = False
    return []


def evaluate_scope(changed_files: list[str], declared: list[str]) -> dict:
    """比对实际变更文件与声明的修改范围。

    匹配规则（路径分量边界）：声明 `src/order` 匹配 `src/order/**` 与
    `src/order` 自身，但不匹配 `src/orders_x/**`（防止前缀误吞）。豁免
    前缀（SCOPE_EXEMPT_PREFIXES）内的流水线工件永不判越界。

    Returns:
        {"declared": [...], "out_of_scope": [...], "status": "pass"|"out_of_scope"}。
        越界判「转人工」而非「打回」——agent 可能合理扩展影响面，由人裁决。

    作者：005819 | 协作：GLM-5.3
    """
    declared_n = [p for p in (_normalize_scope_path(x) for x in declared) if p]
    out_of_scope: list[str] = []
    for raw in changed_files:
        fp = _normalize_scope_path(raw)
        if not fp:
            continue
        if any(fp == e or fp.startswith(e) for e in SCOPE_EXEMPT_PREFIXES):
            continue
        if any(fp == p or fp.startswith(p + "/") for p in declared_n):
            continue
        out_of_scope.append(fp)
    return {
        "declared": declared_n,
        "out_of_scope": sorted(set(out_of_scope)),
        "status": "pass" if not out_of_scope else "out_of_scope",
    }
