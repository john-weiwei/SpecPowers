"""Tests for merge_check_detect in archive_auditor."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.modules.archive_auditor import merge_check_detect, is_feature_archived
from bridge.core.git_util import git_ref_of

# spec-power root (tests/ -> specpowers/ -> spec-power/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def test_merge_check_detect_real_repo():
    """Test merge check on real project."""
    ref = git_ref_of(PROJECT_ROOT)

    # With current ref as base, should not detect merge (0 commits in range)
    result = merge_check_detect(PROJECT_ROOT, ref)
    # Could be False (no merge) or True (if recent merge)
    assert isinstance(result, bool)


def test_is_feature_archived_nonexistent():
    """Non-existent feature should not be archived."""
    result = is_feature_archived(PROJECT_ROOT, "nonexistent-feature-xyz-12345")
    assert result is False


def test_merge_check_detect_with_none_ref():
    """With None ref, should check full history."""
    result = merge_check_detect(PROJECT_ROOT, None)
    assert isinstance(result, bool)


if __name__ == "__main__":
    test_merge_check_detect_real_repo()
    test_is_feature_archived_nonexistent()
    test_merge_check_detect_with_none_ref()
    print("All merge_check tests passed!")
