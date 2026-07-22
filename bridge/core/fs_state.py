"""Atomic file state operations for state.json.

Uses temp-file + rename pattern for atomic writes.
state.json structure:
{
    "stage": str,       # constitution|ready|brainstorm|specify|plan|build|archive
    "mode": str,        # full|fast
    "fallback_used": bool,
    "fallback_count": int,
    "feature": str,
    "last_archive_ref": str
}
"""

import json
import os
import tempfile
from pathlib import Path


DEFAULT_STATE = {
    "stage": "constitution",
    "mode": "full",
    "fallback_used": False,
    "fallback_count": 0,
    "feature": "",
    "last_archive_ref": "",
}


def _get_state_path(root: Path) -> Path:
    """Return path to state.json."""
    return root / ".specpowers" / "state.json"


def load_state(root: Path) -> dict:
    """Load state.json. Returns default if not found. Raises FatalError if corrupt."""
    state_path = _get_state_path(root)
    if not state_path.exists():
        return dict(DEFAULT_STATE)

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        from bridge.core.errors import FatalError
        raise FatalError(
            f"state.json is corrupted: {e}. "
            f"Run /specpowers.reset to recover."
        )

    # Merge with defaults to handle missing keys
    result = dict(DEFAULT_STATE)
    result.update(data)
    return result


def save_state(root: Path, state: dict) -> None:
    """Atomically write state.json using temp file + rename.

    Prevents half-written corruption on crash.
    """
    state_path = _get_state_path(root)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in same directory (ensures same filesystem for atomic rename)
    fd, tmp_path = tempfile.mkstemp(
        suffix=".json",
        prefix=".state-",
        dir=str(state_path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        # Atomic rename
        os.replace(tmp_path, state_path)
    except Exception:
        # Clean up temp file on failure
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def init_state(root: Path) -> dict:
    """Initialize state.json with defaults and persist."""
    state = dict(DEFAULT_STATE)
    save_state(root, state)
    return state


def reset_state(root: Path) -> dict:
    """Reset state to ready (preserves fallback_count)."""
    old_state = load_state(root)
    new_state = dict(DEFAULT_STATE)
    new_state["stage"] = "ready"
    new_state["fallback_count"] = old_state.get("fallback_count", 0)
    save_state(root, new_state)
    return new_state


def delete_state(root: Path) -> None:
    """Delete state.json (for full reset)."""
    state_path = _get_state_path(root)
    if state_path.exists():
        state_path.unlink()
