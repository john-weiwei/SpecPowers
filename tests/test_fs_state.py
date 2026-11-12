"""Tests for fs_state module — atomic state read/write."""

import json
import sys
import tempfile
from pathlib import Path

# package installed via pip - no sys.path needed

from specpowers_cli.bridge.core.fs_state import (
    load_state, save_state, init_state, reset_state, delete_state, DEFAULT_STATE,
)


def test_load_state_default():
    """Loading state from non-existent path returns defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        # Create .specpowers dir
        (root / ".specpowers").mkdir(exist_ok=True)
        state = load_state(root)
        assert state["stage"] == "init"
        assert state["mode"] == "full"
        # v2.8.0 schema 2：死字段 fallback_used 已清除，视图带结构版本标识
        assert "fallback_used" not in state
        assert state["schema"] == 2
        assert state["fallback_count"] == 0


def test_save_and_load_state():
    """Saving then loading should round-trip."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".specpowers").mkdir(exist_ok=True)

        state = {"stage": "propose", "mode": "full",
                 "fallback_count": 0, "feature": "test-feature", "last_archive_ref": ""}
        save_state(root, state)

        loaded = load_state(root)
        assert loaded["stage"] == "propose"
        assert loaded["feature"] == "test-feature"


def test_init_state():
    """init_state creates state.json with defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".specpowers").mkdir(exist_ok=True)

        raw = init_state(root)
        # v2.8.0：init_state 返回顶层全局结构（features 映射），无 stage 键
        assert raw["schema"] == 2
        assert raw["features"] == {}
        # 顶层存在但无活跃需求 → 视图 stage=ready（空转态）
        assert load_state(root)["stage"] == "ready"

        # File should exist
        assert (root / ".specpowers" / "state.json").exists()


def test_reset_state_preserves_fallback_count():
    """reset_state resets to ready but keeps fallback_count."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".specpowers").mkdir(exist_ok=True)

        # Save with fallback_count = 3
        state = {"stage": "apply", "mode": "fast",
                 "fallback_count": 3, "feature": "test", "last_archive_ref": "abc123"}
        save_state(root, state)

        new_state = reset_state(root)
        assert new_state["stage"] == "ready"
        assert new_state["fallback_count"] == 3
        assert new_state["feature"] == ""
        # v2.8.0：reset 清空 features 映射（多活跃全清语义）
        assert load_state(root)["feature"] == ""


def test_delete_state():
    """delete_state removes state.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".specpowers").mkdir(exist_ok=True)

        init_state(root)
        assert (root / ".specpowers" / "state.json").exists()

        delete_state(root)
        assert not (root / ".specpowers" / "state.json").exists()


def test_atomic_write_corruption_resistance():
    """Test that atomic write doesn't leave half-written state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".specpowers").mkdir(exist_ok=True)

        # Write a large state
        state = {"stage": "apply", "mode": "full",
                 "fallback_count": 0, "feature": "x" * 1000, "last_archive_ref": "a" * 40}
        save_state(root, state)

        # Load should be identical
        loaded = load_state(root)
        assert loaded["feature"] == "x" * 1000
        assert len(loaded["feature"]) == 1000


