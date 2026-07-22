"""Tests for baseline_scanner module."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge.modules.baseline_scanner import (
    load_baseline, constitution_changed, git_ref_stale,
)


def test_load_baseline_empty():
    """Loading baseline from non-existent path returns empty dict."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        result = load_baseline(root)
        assert result == {}, f"Expected empty dict, got {result}"


def test_constitution_changed_no_baseline():
    """If no baseline exists, constitution is 'changed'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        result = constitution_changed(root)
        assert result is True


def test_constants():
    """Test DEPENDENCY_FILES constant is defined."""
    from bridge.modules.baseline_scanner import DEPENDENCY_FILES
    assert isinstance(DEPENDENCY_FILES, dict)
    assert "npm" in DEPENDENCY_FILES
    assert DEPENDENCY_FILES["npm"] == "package.json"
    assert "go" in DEPENDENCY_FILES
    assert DEPENDENCY_FILES["go"] == "go.mod"


def test_baseline_json_structure():
    """Test that scan produces correct structure on the real project."""
    from bridge.modules.baseline_scanner import scan

    # spec-power root is 2 levels up from tests/ (specpowers/tests -> specpowers -> spec-power)
    # Run from project root so git commands work
    original_cwd = Path.cwd()
    root = Path(__file__).parent.parent.parent  # spec-power root
    import os
    os.chdir(str(root))
    try:
        # Run scan
        baseline = scan(root)
    finally:
        os.chdir(str(original_cwd))

    assert "git_ref" in baseline
    assert "scanned_at" in baseline
    assert "top_dirs" in baseline
    assert "deps" in baseline
    assert "src_patterns" in baseline
    assert "constitution_hash" in baseline

    assert isinstance(baseline["top_dirs"], list)


def test_baseline_persistence():
    """Test that scan persists to disk."""
    from bridge.modules.baseline_scanner import scan, load_baseline
    import os
    root = Path(__file__).parent.parent.parent
    original_cwd = Path.cwd()
    os.chdir(str(root))
    try:
        baseline = scan(root)
        loaded = load_baseline(root)
    finally:
        os.chdir(str(original_cwd))

    assert loaded["git_ref"] == baseline["git_ref"]
    assert loaded["constitution_hash"] == baseline["constitution_hash"]


if __name__ == "__main__":
    test_load_baseline_empty()
    test_constitution_changed_no_baseline()
    test_constants()
    test_baseline_json_structure()
    test_baseline_persistence()
    print("All baseline_scanner tests passed!")
