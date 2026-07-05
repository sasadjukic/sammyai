import pytest

from editing.change_sets import EditConflict, TextEdit, apply_text_edits


def test_structured_text_edits_apply_against_one_source_snapshot():
    original = "Mara enters.\nThe door is blue.\n"
    color_start = original.index("blue")
    revised = apply_text_edits(
        original,
        (
            TextEdit(0, 4, "Ilya", expected_text="Mara"),
            TextEdit(
                color_start,
                color_start + 4,
                "red",
                expected_text="blue",
            ),
        ),
    )

    assert revised == "Ilya enters.\nThe door is red.\n"


def test_structured_text_edits_reject_overlap_and_stale_expected_text():
    with pytest.raises(EditConflict, match="overlap"):
        apply_text_edits(
            "abcdef",
            (TextEdit(1, 4, "x"), TextEdit(3, 5, "y")),
        )

    with pytest.raises(EditConflict, match="expected text"):
        apply_text_edits(
            "abcdef",
            (TextEdit(1, 3, "x", expected_text="stale"),),
        )
