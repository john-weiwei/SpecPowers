"""Structure gate — extract signals from build diff vs baseline.

Three signal types:
1. New top-level directories not in baseline
2. Unknown dependencies introduced
3. New architecture layer patterns outside baseline
"""

from pathlib import Path

from bridge.modules.baseline_scanner import load_baseline


def extract_signals(tree_diff: str, baseline: dict) -> list[str]:
    """Extract structure gate signals from a git diff.

    Args:
        tree_diff: Output of git diff --stat (or similar).
        baseline: The baseline dict from baseline.json.

    Returns:
        List of signal strings describing deviations.
        Empty list = clean, no structure violations.
    """
    if not baseline:
        return []

    signals = []
    top_dirs = set(baseline.get("top_dirs", []))
    known_deps = set(baseline.get("deps", {}).keys())
    src_patterns = set(baseline.get("src_patterns", []))

    if not tree_diff:
        return signals

    diff_lines = tree_diff.split("\n")

    # Parse file paths from diff
    new_files = set()
    for line in diff_lines:
        line = line.strip()
        if not line:
            continue
        # git diff --stat format: "path/to/file | N +++---"
        parts = line.split("|")
        if parts:
            filepath = parts[0].strip()
            new_files.add(filepath)

    # 1. New top-level directories
    for fp in new_files:
        top_dir = fp.split("/")[0]
        if top_dir not in top_dirs and not top_dir.startswith("."):
            signals.append(f"new_top_dir:{top_dir}")

    # 2. Check for unknown dependency changes
    dep_files = {"package.json", "pom.xml", "build.gradle", "build.gradle.kts",
                 "requirements.txt", "setup.py", "pyproject.toml", "go.mod",
                 "Cargo.toml", "composer.json", "build.sbt", "Gemfile"}
    for fp in new_files:
        fname = fp.split("/")[-1] if "/" in fp else fp
        if fname in dep_files:
            # Dependencies changed — check what was added
            dep_type = _guess_dep_type(fname)
            if dep_type and dep_type not in known_deps:
                signals.append(f"new_dep:{dep_type}")

    # 3. New architecture patterns in src/
    for fp in new_files:
        parts = fp.split("/")
        if len(parts) >= 2 and parts[0] == "src":
            second_level = parts[1]
            if second_level not in src_patterns:
                signals.append(f"new_src_pattern:{second_level}")

    return signals


def _guess_dep_type(filename: str) -> str | None:
    """Guess dependency type from filename."""
    mapping = {
        "package.json": "npm",
        "pom.xml": "maven",
        "build.gradle": "gradle",
        "build.gradle.kts": "gradle",
        "requirements.txt": "pip",
        "setup.py": "pip",
        "pyproject.toml": "pip",
        "go.mod": "go",
        "Cargo.toml": "rust",
        "composer.json": "composer",
        "build.sbt": "sbt",
        "Gemfile": "ruby",
    }
    return mapping.get(filename)


def record_decision(root: Path, result: str, signals: list[str],
                    confidence: str, git_ref: str) -> int:
    """Record a structure gate decision to audit.log.

    Args:
        root: Project root.
        result: Gate result ("pass" / "escalate" / "reject").
        signals: Extracted signals.
        confidence: Confidence level ("高" / "中" / "低").
        git_ref: Current HEAD ref.

    Returns:
        Sequence number of the log entry.
    """
    from bridge.modules.sampling_auditor import log_audit
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).isoformat()
    return log_audit(root, ts, "build", result, signals, confidence, git_ref)
