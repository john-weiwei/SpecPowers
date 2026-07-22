"""Tests for checklist validation in mode_controller."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge.modules.mode_controller import validate_checklist, gen_checklist, parse_confirm


def test_validate_checklist_too_short():
    """Less than 3 items should be rejected."""
    ok, hint = validate_checklist(["item1"])
    assert ok is False
    assert "too short" in hint.lower() or "at least 3" in hint.lower()


def test_validate_checklist_too_long():
    """More than 5 items should be rejected."""
    ok, hint = validate_checklist(["a", "b", "c", "d", "e", "f"])
    assert ok is False
    assert "too long" in hint.lower() or "upgrad" in hint.lower()


def test_validate_checklist_valid():
    """3-5 items should pass."""
    ok, hint = validate_checklist(["item1", "item2", "item3"])
    assert ok is True
    assert hint == ""


def test_validate_checklist_boundary_3():
    """Exactly 3 items is valid."""
    ok, _ = validate_checklist(["a", "b", "c"])
    assert ok is True


def test_validate_checklist_boundary_5():
    """Exactly 5 items is valid."""
    ok, _ = validate_checklist(["a", "b", "c", "d", "e"])
    assert ok is True


def test_parse_confirm_fast():
    """Parsing fast confirmation."""
    result = parse_confirm("go_fast")
    assert result["go_fast"] is True
    assert result["run_brainstorm"] is False


def test_parse_confirm_brainstorm():
    """Parsing brainstorm confirmation."""
    result = parse_confirm("run_brainstorm")
    assert result["go_fast"] is False
    assert result["run_brainstorm"] is True


def test_parse_confirm_tdd():
    """Parsing TDD declaration."""
    result = parse_confirm("go_fast with TDD")
    assert result["go_fast"] is True
    assert result["tdd"] is True


def test_parse_confirm_chinese():
    """Parsing Chinese confirmation."""
    result = parse_confirm("确认优化模式")
    assert result["go_fast"] is True


def test_gen_checklist_extraction():
    """Checklist extraction from dialog."""
    dialog = """
    - item one
    - item two
    - item three
    """
    items = gen_checklist("test req", dialog)
    assert len(items) == 3
    assert "item one" in items


if __name__ == "__main__":
    test_validate_checklist_too_short()
    test_validate_checklist_too_long()
    test_validate_checklist_valid()
    test_validate_checklist_boundary_3()
    test_validate_checklist_boundary_5()
    test_parse_confirm_fast()
    test_parse_confirm_brainstorm()
    test_parse_confirm_tdd()
    test_parse_confirm_chinese()
    test_gen_checklist_extraction()
    print("All checklist tests passed!")
