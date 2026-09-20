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
        assert state["fallback_used"] is False
        assert state["fallback_count"] == 0


def test_save_and_load_state():
    """Saving then loading should round-trip."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".specpowers").mkdir(exist_ok=True)

        state = {"stage": "propose", "mode": "full", "fallback_used": False,
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

        state = init_state(root)
        assert state["stage"] == "init"
        assert state["mode"] == "full"

        # File should exist
        assert (root / ".specpowers" / "state.json").exists()


def test_reset_state_preserves_fallback_count():
    """reset_state resets to ready but keeps fallback_count."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".specpowers").mkdir(exist_ok=True)

        # Save with fallback_count = 3
        state = {"stage": "apply", "mode": "fast", "fallback_used": True,
                 "fallback_count": 3, "feature": "test", "last_archive_ref": "abc123"}
        save_state(root, state)

        new_state = reset_state(root)
        assert new_state["stage"] == "ready"
        assert new_state["fallback_count"] == 3
        assert new_state["fallback_used"] is False
        assert new_state["feature"] == ""


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
        state = {"stage": "apply", "mode": "full", "fallback_used": False,
                 "fallback_count": 0, "feature": "x" * 1000, "last_archive_ref": "a" * 40}
        save_state(root, state)

        # Load should be identical
        loaded = load_state(root)
        assert loaded["feature"] == "x" * 1000
        assert len(loaded["feature"]) == 1000


if __name__ == "__main__":
    test_load_state_default()
    test_save_and_load_state()
    test_init_state()
    test_reset_state_preserves_fallback_count()
    test_delete_state()
    test_atomic_write_corruption_resistance()
    print("All fs_state tests passed!")


# ---- 非 dict 顶层类型拒绝（损坏 state 防御回归）----

def test_load_state_rejects_non_dict_json():
    """顶层为合法 JSON 但非对象（数组）时显式拒绝，不得静默混入。"""
    import pytest
    from specpowers_cli.bridge.core.errors import FatalError

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".specpowers").mkdir(exist_ok=True)
        (root / ".specpowers" / "state.json").write_text('["stage", "ready"]', encoding="utf-8")
        with pytest.raises(FatalError):
            load_state(root)


# ---- iteration_count 字段（多轮迭代：docs/auto-iteration-plan.md）----

def test_default_state_has_iteration_count():
    """DEFAULT_STATE 与 load 默认值都应含 iteration_count=0（首轮语义）。"""
    assert DEFAULT_STATE["iteration_count"] == 0
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".specpowers").mkdir(exist_ok=True)
        assert load_state(root)["iteration_count"] == 0


def test_reset_state_clears_iteration_count():
    """reset 放弃当前 feature → iteration_count 清零（新需求从首轮开始），fallback_count 仍保留。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".specpowers").mkdir(exist_ok=True)

        state = {"stage": "apply", "mode": "full", "fallback_used": False,
                 "fallback_count": 2, "feature": "iter-feat", "last_archive_ref": "",
                 "iteration_count": 3}
        save_state(root, state)

        new_state = reset_state(root)
        assert new_state["stage"] == "ready"
        assert new_state["iteration_count"] == 0
        assert new_state["fallback_count"] == 2


# ---- v2.0.0 旧阶段名惰性迁移回归 ----

def test_load_state_migrates_legacy_stages(tmp_path):
    """v1.x 旧阶段名读出即归一为新名（不写回，下次 save 自然落盘新值）。"""
    from specpowers_cli.bridge.core.fs_state import load_state, _get_state_path

    cases = {
        "constitution": "init",
        "brainstorm": "explore",
        "specify": "propose",
        "plan": "propose",
        "build": "apply",
        "ready": "ready",
        "archive": "archive",
    }
    for old, new in cases.items():
        root = tmp_path / f"migrate-{old}"
        (root / ".specpowers").mkdir(parents=True)
        _get_state_path(root).write_text(
            json.dumps({"stage": old, "mode": "full", "feature": "f1"}), encoding="utf-8",
        )
        assert load_state(root)["stage"] == new, f"{old} should map to {new}"


def test_load_state_unknown_stage_passthrough(tmp_path):
    """未知 stage 值原样返回（交由状态机校验拒绝），不静默改写。"""
    from specpowers_cli.bridge.core.fs_state import load_state, _get_state_path

    root = tmp_path / "migrate-unknown"
    (root / ".specpowers").mkdir(parents=True)
    _get_state_path(root).write_text(
        json.dumps({"stage": "galaxy", "mode": "full"}), encoding="utf-8",
    )
    assert load_state(root)["stage"] == "galaxy"


def test_load_state_fills_design_doc_default(tmp_path):
    """v1.x state 无 design_doc key 时按 DEFAULT_STATE 补默认空串。"""
    from specpowers_cli.bridge.core.fs_state import load_state, _get_state_path

    root = tmp_path / "migrate-designdoc"
    (root / ".specpowers").mkdir(parents=True)
    _get_state_path(root).write_text(
        json.dumps({"stage": "propose", "mode": "full"}), encoding="utf-8",
    )
    assert load_state(root)["design_doc"] == ""
