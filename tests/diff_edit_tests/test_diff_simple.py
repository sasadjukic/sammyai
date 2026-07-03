"""Focused smoke tests for DiffManager."""

import pytest

from editing.diff_manager import DiffConflict, DiffManager


def test_basic_diff():
    manager = DiffManager()
    original = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n"
    modified = "Line 1\nLine 2 modified\nLine 3\nNew Line 3.5\nLine 4\nLine 5\n"

    diff = manager.generate_diff(original, modified)

    assert diff.hunks
    assert manager.apply_diff(original, diff) == modified


def test_diff_stats():
    manager = DiffManager()
    diff = manager.generate_diff(
        "Line 1\nLine 2\nLine 3\n",
        "Line 1\nLine 2 changed\nLine 3\nLine 4\n",
    )

    stats = manager.get_diff_stats(diff)

    assert stats["additions"] > 0
    assert stats["hunks"] > 0


def test_history():
    manager = DiffManager()
    manager.add_to_history("Version 1", "Version 2")
    manager.add_to_history("Version 2", "Version 3")

    assert manager.can_undo()
    assert manager.undo() == "Version 2"
    assert manager.can_redo()
    assert manager.redo() == "Version 3"


def test_conflict_detection():
    manager = DiffManager()
    diff = manager.generate_diff(
        "Line 1\nLine 2\nLine 3\n",
        "Line 1\nLine 2 changed\nLine 3\n",
    )

    with pytest.raises(DiffConflict):
        manager.apply_diff("Completely different\ntext\n", diff, strict=True)
