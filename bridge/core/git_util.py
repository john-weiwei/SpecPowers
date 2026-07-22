"""Safe git subprocess wrapper.

CRITICAL: All git operations MUST use this module. Never call subprocess.run directly.
- Parameters are passed as lists (never string concatenation / shell=True).
- Timeouts are tiered: lightweight ops 30s, range queries 120s.
- All git output uses text=True, capture_output=True.
"""

import os
import subprocess
import sys
from pathlib import Path


# Timeout tiers (seconds)
LIGHT_TIMEOUT = 30   # rev-parse, ls-tree, status
RANGE_TIMEOUT = 120  # log --since, log --grep


def _find_git() -> str:
    """Locate git executable. Raises GitNotFoundError if missing."""
    # Check common locations first
    candidates = ["git"]
    if sys.platform == "win32":
        candidates.extend([
            r"C:\Program Files\Git\bin\git.exe",
            r"C:\Program Files (x86)\Git\bin\git.exe",
        ])

    for candidate in candidates:
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    from bridge.core.errors import GitNotFoundError
    raise GitNotFoundError(
        "git is not installed or not in PATH. Please install git 2.30+."
    )


# Module-level git path cache
_GIT_PATH: str | None = None


def _git_cmd() -> str:
    global _GIT_PATH
    if _GIT_PATH is None:
        _GIT_PATH = _find_git()
    return _GIT_PATH


def run_git(args: list[str], timeout: int = LIGHT_TIMEOUT, cwd: Path | None = None) -> str:
    """Run a git command safely.

    Args:
        args: Git arguments as a list (e.g. ["rev-parse", "HEAD"]).
              Never pass shell=True or string concatenation.
        timeout: Timeout in seconds (LIGHT_TIMEOUT=30 or RANGE_TIMEOUT=120).
        cwd: Working directory. Defaults to current directory.

    Returns:
        stdout of the git command (stripped).

    Raises:
        GitNotFoundError: git not available.
        FatalError: git command failed.
    """
    cmd = [_git_cmd()] + args
    env = os.environ.copy()
    # Ensure English output for parsing
    env["LANG"] = "en_US.UTF-8"
    env["LC_ALL"] = "en_US.UTF-8"

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=timeout,
            cwd=str(cwd) if cwd else None,
            env=env,
        )
    except subprocess.TimeoutExpired:
        from bridge.core.errors import FatalError
        raise FatalError(
            f"git command timed out after {timeout}s: git {' '.join(args)}"
        )
    except FileNotFoundError:
        from bridge.core.errors import GitNotFoundError
        raise GitNotFoundError("git executable not found.")

    if result.returncode != 0:
        from bridge.core.errors import FatalError
        raise FatalError(
            f"git command failed (exit {result.returncode}): git {' '.join(args)}\n"
            f"stderr: {result.stderr.strip()}"
        )

    return result.stdout.strip()


def _run_git_quiet(args: list[str], timeout: int = LIGHT_TIMEOUT, cwd: Path | None = None) -> str | None:
    """Run git command, return None if it fails (no exception)."""
    try:
        return run_git(args, timeout=timeout, cwd=cwd)
    except Exception:
        return None


def git_exists() -> bool:
    """Check if git is available. Returns False instead of raising."""
    try:
        _find_git()
        return True
    except Exception:
        return False


def is_git_repo(root: Path) -> bool:
    """Check if root is inside a git repository."""
    result = _run_git_quiet(["rev-parse", "--git-dir"], cwd=root)
    return result is not None


def is_detached_head(root: Path) -> bool:
    """Check if HEAD is detached."""
    try:
        run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
        return False
    except Exception:
        # If rev-parse --abbrev-ref fails, we're in detached HEAD
        return True


def has_commits(root: Path) -> bool:
    """Check if the repo has at least one commit."""
    result = _run_git_quiet(["rev-list", "-n", "1", "HEAD"], cwd=root)
    return result is not None and len(result) > 0


def git_ref_of(root: Path) -> str:
    """Return HEAD commit short hash."""
    return run_git(["rev-parse", "--short", "HEAD"], cwd=root)


def diff_stat(root: Path, base: str | None = None) -> str:
    """Return git diff --stat output.

    Args:
        root: Repository root.
        base: Base ref for diff (e.g. "HEAD~1"). If None, diff working tree vs HEAD.
    """
    if base:
        return run_git(["diff", "--stat", base, "HEAD"], timeout=RANGE_TIMEOUT, cwd=root)
    else:
        return run_git(["diff", "--stat", "HEAD"], timeout=RANGE_TIMEOUT, cwd=root)


def ls_tree_head(root: Path) -> list[str]:
    """Return top-level directory/file names from git ls-tree HEAD."""
    output = run_git(["ls-tree", "-d", "--name-only", "HEAD"], cwd=root)
    if not output:
        return []
    return [line.strip() for line in output.split("\n") if line.strip()]


def log_since(root: Path, days: int) -> list[str]:
    """Return commit hashes since N days ago."""
    output = run_git(
        ["log", f"--since={days}.days", "--format=%H"],
        timeout=RANGE_TIMEOUT, cwd=root
    )
    if not output:
        return []
    return [line.strip() for line in output.split("\n") if line.strip()]


def log_merges(root: Path, since_ref: str | None = None) -> list[str]:
    """Return merge commits. If since_ref given, only from that ref to HEAD."""
    args = ["log", "--merges", "--format=%H"]
    if since_ref:
        args.append(f"{since_ref}..HEAD")
    output = _run_git_quiet(args, timeout=RANGE_TIMEOUT, cwd=root)
    if not output:
        return []
    return [line.strip() for line in output.split("\n") if line.strip()]


def log_authors_count(root: Path, since_ref: str | None = None) -> int:
    """Count unique authors since a given ref."""
    args = ["log", "--format=%an"]
    if since_ref:
        args.append(f"{since_ref}..HEAD")
    output = run_git(args, timeout=RANGE_TIMEOUT, cwd=root)
    if not output:
        return 0
    authors = {line.strip() for line in output.split("\n") if line.strip()}
    return len(authors)


def log_grep_feature(root: Path, feature: str) -> list[str]:
    """Search for commits with 'specpowers.*<feature>' in message."""
    args = ["log", "--format=%H", f"--grep=specpowers.*{feature}"]
    output = _run_git_quiet(args, timeout=RANGE_TIMEOUT, cwd=root)
    if not output:
        return []
    return [line.strip() for line in output.split("\n") if line.strip()]


def monthly_avg_commits(root: Path) -> int:
    """Estimate monthly average commits (last 90 days / 3)."""
    commits_90d = log_since(root, 90)
    if not commits_90d:
        return 0
    return max(1, len(commits_90d) // 3)


def current_branch(root: Path) -> str | None:
    """Return current branch name, or None if detached."""
    result = _run_git_quiet(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
    if result == "HEAD":
        return None  # detached
    return result
