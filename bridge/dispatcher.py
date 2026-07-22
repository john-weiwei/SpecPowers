"""Dispatcher — stage routing, lock management, auto-read enforcement.

Routes each stage command through:
1) Acquire lock
2) Validate state machine transition
3) Enforce required artifact reads
4) Execute stage logic
5) Release lock
"""

import json
import sys
from pathlib import Path
from typing import Any

from bridge.core.errors import (
    FatalError, StateError, ArtifactMissingError,
    ArchiveDuplicateError, RecoverableError,
)
from bridge.core.fs_state import load_state, save_state, init_state, reset_state, delete_state
from bridge.core.lock import acquire_lock, release_lock, force_unlock
from bridge.core.git_util import is_git_repo, has_commits, is_detached_head
from bridge.modules.artifact_registry import required_for


# ---- State machine validation ----

VALID_TRANSITIONS: dict[str, list[str | None]] = {
    "constitution": ["constitution"],  # initial or force
    "ready": ["constitution", "archive"],
    "brainstorm": ["ready"],
    "specify": ["brainstorm", "ready", "build"],
    "plan": ["specify"],
    "build": ["plan", "ready"],
    "archive": ["build"],
}

STAGE_NAMES = ["constitution", "ready", "brainstorm", "specify", "plan", "build", "archive"]


def _validate_transition(from_stage: str, to_stage: str):
    """Validate state machine transition."""
    valid_from = VALID_TRANSITIONS.get(to_stage, [])
    if from_stage not in valid_from and None not in valid_from:
        raise StateError(
            f"Cannot transition from '{from_stage}' to '{to_stage}'. "
            f"Valid from stages: {', '.join(str(v) for v in valid_from)}"
        )


def normalize_feature(raw: str) -> str:
    """Normalize a requirement string into a safe feature slug.

    Rules:
    - Take first 40 characters
    - Remove special characters (keep alphanumeric, spaces, Chinese chars, hyphens)
    - Replace spaces with hyphens
    - Empty input → 'unnamed'
    - Pure Chinese → truncate without replacing
    """
    if not raw or not raw.strip():
        return "unnamed"

    raw = raw.strip()
    # Take first 40 chars (supports Chinese)
    raw = raw[:40]

    # Check if predominantly Chinese (no replacement needed for spaces→hyphens)
    chinese_count = sum(1 for c in raw if '\u4e00' <= c <= '\u9fff')
    if chinese_count > len(raw) * 0.3:
        # Keep Chinese, only replace ASCII spaces and remove truly special chars
        import re
        result = re.sub(r'[^\w\u4e00-\u9fff\s-]', '', raw)
        result = re.sub(r'\s+', '-', result)
        result = result.strip('-')
        return result or "unnamed"

    # Non-Chinese: normalize
    import re
    result = re.sub(r'[^\w\s-]', '', raw)
    result = re.sub(r'\s+', '-', result)
    result = result.strip('-').lower()
    return result or "unnamed"


def _check_prerequisites(root: Path):
    """Verify git prerequisites before any operation."""
    if not is_git_repo(root):
        raise FatalError(f"'{root}' is not a git repository.")
    if not has_commits(root):
        raise FatalError("Git repository has no commits yet.")
    if is_detached_head(root):
        raise FatalError("Git HEAD is detached. Please checkout a branch first.")


def _run_pre_stage_checks(root: Path, stage: str, mode: str):
    """Run checks before entering a stage."""
    # Enforce auto-read: check required artifacts exist
    artifacts = required_for(stage, mode)
    for art in artifacts:
        art_path = root / art["path"]
        if not art_path.exists():
            raise ArtifactMissingError(
                f"Required artifact '{art['path']}' not found. "
                f"Run the previous stage ({art['producer']}) first."
            )

    # For fast mode build: check code changes exist
    if stage == "build" and mode == "fast":
        from bridge.core.git_util import diff_stat, run_git
        diff = diff_stat(root)  # working tree vs HEAD
        if not diff.strip():
            # Check if there's a recent commit
            try:
                diff2 = run_git(["diff", "--stat", "HEAD~1..HEAD"], cwd=root)
                if not diff2.strip():
                    raise FatalError(
                        "No code changes detected. "
                        "Complete your coding before running /specpowers.build"
                    )
            except Exception:
                raise FatalError(
                    "No code changes detected. "
                    "Complete your coding before running /specpowers.build"
                )


def _check_constitution_conflict(root: Path):
    """Check if constitution command would discard an in-progress feature."""
    state = load_state(root)
    if state.get("stage") != "constitution":
        # Interactive confirmation needed — in CI mode, auto-confirm
        if is_ci_mode():
            print("[CI] Auto-confirming constitution re-generation (would discard feature "
                  f"'{state.get('feature', '')}')", file=sys.stderr)
        else:
            feature = state.get("feature", "")
            raise StateError(
                f"Current feature '{feature}' is in progress (stage: {state.get('stage')}). "
                f"Use --force to discard and rebuild constitution, "
                f"or /specpowers.reset to start fresh."
            )


def is_ci_mode() -> bool:
    """Check if running in CI mode."""
    import os
    return os.environ.get("SPECPOWERS_CI", "").strip() == "1"


def is_verbose() -> bool:
    """Check if verbose logging is enabled."""
    import os
    return os.environ.get("SPECPOWERS_VERBOSE", "").strip() == "1"


def _log_verbose(msg: str):
    """Log verbose message to stderr."""
    if is_verbose():
        print(f"[specpowers] {msg}", file=sys.stderr)


# ---- Stage handlers ----

def _handle_constitution(root: Path, extra: dict) -> int:
    """Handle constitution stage."""
    force = extra.get("force", False)
    state = load_state(root)

    if not force and state.get("stage") != "constitution":
        _check_constitution_conflict(root)

    _log_verbose("Running baseline scanner...")
    from bridge.modules.baseline_scanner import scan, load_baseline

    baseline_path = root / ".specpowers" / "baseline.json"
    if baseline_path.exists() and not force:
        _log_verbose("constitution.md and baseline.json exist, skipping.")
    else:
        if force and baseline_path.exists():
            baseline_path.unlink()
        scan(root)

    # Transition: constitution → ready
    new_state = load_state(root)
    new_state["stage"] = "ready"
    new_state["mode"] = "full"
    new_state["feature"] = ""
    save_state(root, new_state)

    print("Constitution + baseline ready. Stage: ready")
    return 0


def _handle_brainstorm(root: Path, extra: dict) -> int:
    """Handle brainstorm stage."""
    req = extra.get("requirement", "")
    feature = normalize_feature(req)
    state = load_state(root)

    _validate_transition(state["stage"], "brainstorm")

    _check_prerequisites(root)
    _run_pre_stage_checks(root, "brainstorm", "full")

    # Update state
    state["stage"] = "brainstorm"
    state["mode"] = "full"
    state["feature"] = feature
    save_state(root, state)

    print(f"Brainstorm started for feature: {feature}")
    print("Agent should now: explore the requirement, generate brief.md, then continue to /specpowers.specify")
    return 0


def _handle_specify(root: Path, extra: dict) -> int:
    """Handle specify stage."""
    req = extra.get("requirement", "")
    state = load_state(root)
    from_stage = state["stage"]

    _validate_transition(from_stage, "specify")

    # Feature name: use existing from brainstorm or new from requirement
    if from_stage == "brainstorm":
        feature = state.get("feature", normalize_feature(req))
    else:
        feature = normalize_feature(req)

    _check_prerequisites(root)
    _run_pre_stage_checks(root, "specify", "full")

    state["stage"] = "specify"
    state["mode"] = "full"
    state["feature"] = feature
    save_state(root, state)

    print(f"Specify started for feature: {feature}")
    return 0


def _handle_fast(root: Path, extra: dict) -> int:
    """Handle fast mode entry."""
    req = extra.get("requirement", "")
    feature = normalize_feature(req)
    state = load_state(root)

    _validate_transition(state["stage"], "fast")

    _check_prerequisites(root)

    # Check constitution/baseline exist (hard gate for fast mode)
    baseline_path = root / ".specpowers" / "baseline.json"
    if not baseline_path.exists():
        raise FatalError(
            "Baseline not found. Run /specpowers.constitution first."
        )

    state["stage"] = "ready"
    state["mode"] = "fast"
    state["feature"] = feature
    save_state(root, state)

    print(f"Fast mode activated for feature: {feature}")
    print("Agent will now: run small-judgment → confirmation → user codes → /specpowers.build")
    return 0


def _handle_plan(root: Path, extra: dict) -> int:
    """Handle plan stage."""
    state = load_state(root)
    _validate_transition(state["stage"], "plan")

    _check_prerequisites(root)
    _run_pre_stage_checks(root, "plan", "full")

    state["stage"] = "plan"
    save_state(root, state)
    print("Plan stage ready.")
    return 0


def _handle_build(root: Path, extra: dict) -> int:
    """Handle build stage."""
    state = load_state(root)
    mode = state.get("mode", "full")
    from_stage = state["stage"]

    _validate_transition(from_stage, "build")

    _check_prerequisites(root)
    _run_pre_stage_checks(root, "build", mode)

    state["stage"] = "build"
    save_state(root, state)

    if mode == "fast":
        print("Build stage (fast mode). Agent will run: code extraction → structure gate → execute → verify.")
    else:
        print("Build stage (full mode). Agent will run: structure gate → ability pool → execute → verify.")
    return 0


def _handle_archive(root: Path, extra: dict) -> int:
    """Handle archive stage."""
    state = load_state(root)
    force_merge = extra.get("force_merge_check", False)
    mode = state.get("mode", "full")
    feature = state.get("feature", "")

    _validate_transition(state["stage"], "archive")

    # Duplicate check: has this feature already been archived?
    from bridge.modules.archive_auditor import is_feature_archived
    if feature and is_feature_archived(root, feature):
        raise ArchiveDuplicateError(
            f"Feature '{feature}' already has an archive commit. "
            f"Run: git pull && /specpowers.reset to sync."
        )

    _check_prerequisites(root)
    _run_pre_stage_checks(root, "archive", mode)

    from bridge.core.git_util import git_ref_of
    current_ref = git_ref_of(root)

    # Merge check
    from bridge.modules.archive_auditor import merge_check_detect
    should_merge_check = force_merge or merge_check_detect(
        root, state.get("last_archive_ref", "")
    )

    if should_merge_check and mode != "fast":
        print("⚠ Merge check triggered — multi-branch or forced. Agent will run post-merge verification.")

    state["stage"] = "archive"
    save_state(root, state)
    print(f"Archive started for feature: {feature} (mode: {mode})")
    return 0


def _handle_baseline(root: Path, extra: dict) -> int:
    """Handle baseline refresh."""
    _check_prerequisites(root)
    from bridge.modules.baseline_scanner import scan
    scan(root)
    print("Baseline refreshed. Please review and commit baseline.json.")
    return 0


def _handle_reset(root: Path, extra: dict) -> int:
    """Handle reset."""
    state_path = root / ".specpowers" / "state.json"
    lock_path = root / ".specpowers" / ".lock"

    old_state = load_state(root)
    fallback_count = old_state.get("fallback_count", 0)

    # Remove state and lock
    if state_path.exists():
        state_path.unlink()
    if lock_path.exists():
        force_unlock(root)

    # Re-init state (preserving fallback_count)
    new_state = {
        "stage": "ready",
        "mode": "full",
        "fallback_used": False,
        "fallback_count": fallback_count,
        "feature": "",
        "last_archive_ref": "",
    }
    save_state(root, new_state)

    print("State reset to ready. (fallback_count preserved)")
    return 0


# ---- Route table ----

STAGE_HANDLERS = {
    "constitution": _handle_constitution,
    "brainstorm": _handle_brainstorm,
    "specify": _handle_specify,
    "fast": _handle_fast,
    "plan": _handle_plan,
    "build": _handle_build,
    "archive": _handle_archive,
    "baseline": _handle_baseline,
    "reset": _handle_reset,
}


def route(stage: str, mode: str, root: Path, extra: dict | None = None) -> int:
    """Route a stage command to its handler.

    This is the main entry point for all stage operations.
    Called by facade.py command handlers.

    Args:
        stage: Stage name (constitution, brainstorm, specify, fast, plan, build, archive, baseline, reset)
        mode: Operation mode (full or fast)
        root: Project root path
        extra: Additional parameters (requirement, force, force_merge_check, etc.)

    Returns:
        Exit code (0 = success)
    """
    if extra is None:
        extra = {}

    handler = STAGE_HANDLERS.get(stage)
    if handler is None:
        raise ValueError(f"Unknown stage: {stage}")

    # Ensure .specpowers directory exists
    specpowers_dir = root / ".specpowers"
    specpowers_dir.mkdir(parents=True, exist_ok=True)

    # Ensure state.json exists
    state_path = specpowers_dir / "state.json"
    if not state_path.exists():
        init_state(root)

    # Acquire lock (except for reset which bypasses lock)
    if stage != "reset":
        try:
            acquired = acquire_lock(root, timeout=0)
            if not acquired:
                raise FatalError("Could not acquire lock. Another instance may be running.")
        except Exception as e:
            if not isinstance(e, FatalError):
                raise
            raise

    try:
        # Register signal handlers for graceful shutdown
        import signal

        def _signal_handler(signum, frame):
            """Handle SIGINT/SIGTERM: save state + release lock before exit."""
            print("\n[specpowers] Interrupted. Saving state and releasing lock...", file=sys.stderr)
            release_lock(root)
            sys.exit(130)

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        result = handler(root, extra)
        release_lock(root)
        return result

    except Exception:
        release_lock(root)
        raise
