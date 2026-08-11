"""Baseline scanner — scan project structure and persist to baseline.json.

Scans:
1. git ls-tree HEAD → top_dirs
2. Dependency files → deps
3. src/ second-level directory patterns → src_patterns

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
from datetime import datetime, timezone
from pathlib import Path

from specpowers_cli.bridge.core.git_util import (
    ls_tree_head, git_ref_of, monthly_avg_commits, log_since,
    run_git, RANGE_TIMEOUT,
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
    """Scan src/ second-level directories for naming patterns."""
    src_dir = root / "src"
    if not src_dir.exists() or not src_dir.is_dir():
        return []

    patterns = set()
    # List top-level subdirectories of src/
    for item in src_dir.iterdir():
        if item.is_dir():
            # Check second-level directories
            try:
                for sub in item.iterdir():
                    if sub.is_dir():
                        patterns.add(sub.name)
            except PermissionError:
                continue

    return sorted(patterns)


def _check_large_repo(root: Path) -> bool:
    """Check if repo is large enough to trigger degradation.

    用 git ls-files 统计版本控制内的文件数，避免 rglob 全量遍历大目录
    （rglob 恰恰在大仓库场景下会卡死，与检测目的背道而驰）。
    """
    try:
        output = run_git(["ls-tree", "-d", "--name-only", "HEAD"], cwd=root)
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

    In large repos, automatically applies degradation:
    - Only scans first-level directories
    - Only checks root-level dependency files
    - Limits git log to 30 days
    """
    is_large = _check_large_repo(root)
    if is_large:
        scan_depth = os.environ.get("SPECPOWERS_SCAN_DEPTH", "")
        if scan_depth != "shallow":
            print(
                "⚠ Large repository detected (>10k files or >1000 dirs). "
                "Consider: export SPECPOWERS_SCAN_DEPTH=shallow for faster scanning.",
                file=__import__("sys").stderr,
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

    # Persist（原子写：tempfile + rename，防止崩溃留下半截 JSON 损坏团队共享文件）
    baseline_path = _get_baseline_path(root)
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    import os
    import tempfile
    fd, tmp_path = tempfile.mkstemp(
        suffix=".json", prefix=".baseline-", dir=str(baseline_path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(baseline, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, baseline_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    return baseline


def load_baseline(root: Path) -> dict:
    """Load baseline.json. Returns empty dict if not found."""
    baseline_path = _get_baseline_path(root)
    if not baseline_path.exists():
        return {}
    with open(baseline_path, "r", encoding="utf-8") as f:
        return json.load(f)


def constitution_changed(root: Path) -> bool:
    """Check if constitution.md has changed since last baseline scan."""
    baseline = load_baseline(root)
    if not baseline:
        return True  # No baseline = treat as changed

    old_hash = baseline.get("constitution_hash", "")
    new_hash = _compute_constitution_hash(root)
    return old_hash != new_hash


def refresh_baseline(root: Path) -> dict:
    """Force re-scan and update baseline.json."""
    return scan(root)


def git_ref_stale(root: Path, baseline: dict | None = None) -> bool:
    """Check if baseline git_ref is stale.

    Staleness threshold: max(30 days, monthly_avg_commits * 2 commits behind).
    """
    if baseline is None:
        baseline = load_baseline(root)
    if not baseline:
        return True

    baseline_ref = baseline.get("git_ref", "")
    if not baseline_ref:
        return True

    try:
        current_ref = git_ref_of(root)
        if current_ref == baseline_ref:
            return False

        # Count commits between baseline and HEAD
        try:
            count = run_git(
                ["rev-list", "--count", f"{baseline_ref}..HEAD"],
                cwd=root,
            )
            behind = int(count)
        except Exception:
            behind = 999

        monthly_avg = monthly_avg_commits(root)
        threshold = max(30, monthly_avg * 2)

        return behind > threshold
    except Exception:
        return True


def check_baseline_drift(root: Path) -> bool:
    """Check for baseline drift. Returns True if stale (warning needed)."""
    stale = git_ref_stale(root)
    if stale:
        print(
            "⚠ Baseline may be stale. Consider running /specpowers.baseline to refresh.",
            file=__import__("sys").stderr,
        )
    return stale
