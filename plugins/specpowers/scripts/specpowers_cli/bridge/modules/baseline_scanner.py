"""Baseline scanner — scan project structure and persist to baseline.json.

Scans:
1. git ls-tree HEAD → top_dirs
2. Dependency files → deps
3. src/ first-level directory patterns → src_patterns

Output baseline.json:
{
    "git_ref": "abc1234",
    "scanned_at": "2025-01-01T00:00:00",
    "top_dirs": ["src", "docs", ...],
    "deps": {"npm": "package.json", "maven": "pom.xml", ...},
    "src_patterns": ["controller", "service", "model", ...],
    "constitution_hash": "sha256..."
}
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from specpowers_cli.bridge.core.fs_state import atomic_write_json
from specpowers_cli.bridge.core.git_util import (
    ls_tree_head, git_ref_of, run_git, RANGE_TIMEOUT,
)
from specpowers_cli.bridge.modules.dep_manifest import DEPENDENCY_REGISTRY


def _get_baseline_path(root: Path) -> Path:
    return root / ".specpowers" / "baseline.json"


def _compute_constitution_hash(root: Path) -> str:
    """Compute SHA-256 hash of .specpowers/constitution.md."""
    constitution_path = root / ".specpowers" / "constitution.md"
    if not constitution_path.exists():
        return ""
    with open(constitution_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _scan_deps(root: Path) -> dict[str, str]:
    """Scan for dependency manifest files."""
    deps = {}
    for name, pattern in DEPENDENCY_REGISTRY.items():
        if "*" in pattern:
            # Glob pattern
            matches = list(root.glob(pattern))
            if matches:
                # Use relative path of first match
                deps[name] = str(matches[0].relative_to(root))
        else:
            path = root / pattern
            if path.exists():
                deps[name] = pattern
    return deps


def _scan_src_patterns(root: Path) -> list[str]:
    """Scan src/ first-level directories for naming patterns.

    契约：收集 src/ 的「一级」子目录名。structure_gate 用 diff 路径的
    parts[1]（src 下一级）与之比对，两侧深度必须一致——原实现错误地收集
    二级目录名，平铺/嵌套布局下门禁对每次 src 变更都会误报 new_src_pattern。
    """
    src_dir = root / "src"
    if not src_dir.exists() or not src_dir.is_dir():
        return []

    patterns = set()
    for item in src_dir.iterdir():
        if item.is_dir():
            try:
                patterns.add(item.name)
            except PermissionError:
                continue

    return sorted(patterns)


def _check_large_repo(root: Path) -> bool:
    """Check if repo is large enough to trigger degradation.

    用 git ls-files 统计版本控制内的文件数，避免 rglob 全量遍历大目录
    （rglob 恰恰在大仓库场景下会卡死，与检测目的背道而驰）。
    """
    # 顶层目录计数改用 -r 递归列出全部目录节点：
    # 非 -d 的 ls-tree 只列顶层（恒 <1000），该信号原实现永远不触发
    try:
        output = run_git(["ls-tree", "-r", "-d", "--name-only", "HEAD"], cwd=root)
        lines = output.split("\n") if output else []
        if len(lines) > 1000:
            return True
    except Exception:
        pass

    # 用 git ls-files 统计跟踪文件数（远快于 rglob 全量遍历磁盘）
    try:
        output = run_git(["ls-files"], timeout=RANGE_TIMEOUT, cwd=root)
        if output:
            file_count = len(output.split("\n"))
            if file_count > 10000:
                return True
    except Exception:
        pass

    return False


def scan(root: Path) -> dict:
    """Run baseline scan and persist to baseline.json.

    Returns:
        The baseline dict that was written.

    大仓库（>10k 文件或 >1000 目录）仅打印一次降级提示，
    SPECPOWERS_SCAN_DEPTH=shallow 可静音该提示（当前实现不改变扫描行为）。
    """
    is_large = _check_large_repo(root)
    if is_large:
        scan_depth = os.environ.get("SPECPOWERS_SCAN_DEPTH", "")
        if scan_depth != "shallow":
            print(
                "[WARN] Large repository detected (>10k files or >1000 dirs). "
                "Consider: export SPECPOWERS_SCAN_DEPTH=shallow for faster scanning.",
                file=sys.stderr,
            )

    # 1. Top directories
    top_dirs = ls_tree_head(root)
    if not top_dirs:
        # Fallback: list filesystem
        top_dirs = sorted([
            item.name for item in root.iterdir()
            if item.is_dir() and not item.name.startswith(".")
        ])

    # 2. Dependencies
    deps = _scan_deps(root)

    # 3. Source patterns
    src_patterns = _scan_src_patterns(root)

    # 4. Metadata
    git_ref = git_ref_of(root)
    constitution_hash = _compute_constitution_hash(root)
    scanned_at = datetime.now(timezone.utc).isoformat()

    baseline = {
        "git_ref": git_ref,
        "scanned_at": scanned_at,
        "top_dirs": top_dirs,
        "deps": deps,
        "src_patterns": src_patterns,
        "constitution_hash": constitution_hash,
    }

    # Persist：复用 fs_state.atomic_write_json（tempfile + rename + Windows 占用重试），
    # 防崩溃留下半截 JSON；Windows 上杀毒/索引器短暂占用目标文件是已知痛点，
    # 裸 os.replace 会间歇性抛 WinError 5（fs_state 已踩坑并修好，此处保持同源）
    baseline_path = _get_baseline_path(root)
    atomic_write_json(baseline_path, baseline)

    return baseline


def load_baseline(root: Path) -> dict:
    """Load baseline.json. Returns empty dict if not found.

    文件损坏（手工编辑出错/写盘中断残留）时显式报错并指引重建，
    与 fs_state.load_state 对 state.json 的处理对齐；
    裸 json.load 会让 gate 命令直接以 traceback 崩溃。
    """
    baseline_path = _get_baseline_path(root)
    if not baseline_path.exists():
        return {}
    try:
        with open(baseline_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        from specpowers_cli.bridge.core.errors import FatalError
        raise FatalError(
            f"baseline.json is corrupted: {e}. "
            f"Run 'specpowers baseline' (or /specpowers-baseline) to re-scan."
        )
    if not isinstance(data, dict):
        from specpowers_cli.bridge.core.errors import FatalError
        raise FatalError(
            "baseline.json is corrupted: top level must be a JSON object. "
            "Run 'specpowers baseline' (or /specpowers-baseline) to re-scan."
        )
    return data


def constitution_changed(root: Path) -> bool:
    """Check if constitution.md has changed since last baseline scan."""
    baseline = load_baseline(root)
    if not baseline:
        return True  # No baseline = treat as changed

    old_hash = baseline.get("constitution_hash", "")
    new_hash = _compute_constitution_hash(root)
    return old_hash != new_hash
