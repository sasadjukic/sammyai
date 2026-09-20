import pytest

from editing.change_sets import FileChange, FileChangeKind, content_hash
from editing.review_session import HunkState, ReviewSession


def make_review(before, after, kind=FileChangeKind.UPDATE):
    change = FileChange(
        "chapter.md", kind, before, after,
        content_hash(before) if before is not None else None,
        content_hash(after) if after is not None else None,
    )
    return ReviewSession("source", "document", "/chapter.md", change)


@pytest.mark.parametrize("before,after", [
    ("", "First line"), ("Last line\n", ""),
    ("a\r\nb\r\n", "a\r\nnew\r\nb\r\n"),
    ("same\n", "same"), ("😀 café\n", "😀 story\n"),
    ("one\ntwo\nthree\n", "new\ntwo\nend\nextra\n"),
])
def test_accept_and_reject_preserve_exact_content(before, after):
    review = make_review(before, after)
    review.decide_all(HunkState.ACCEPTED)
    assert review.final_content() == after
    review.decide_all(HunkState.REJECTED)
    assert review.final_content() == before
    assert review.final_change() is None


def test_stable_ids_and_mixed_decisions_do_not_shift_later_ranges():
    before = "first\nkeep\nlast\n"
    after = "first revised\ninserted\nkeep\nlast revised\n"
    review = make_review(before, after)
    assert [h.id for h in review.hunks] == [h.id for h in make_review(before, after).hunks]
    assert len(review.hunks) == 2
    with pytest.raises(ValueError, match="pending"):
        review.final_content()
    review.decide(review.hunks[1].id, HunkState.ACCEPTED)
    review.decide(review.hunks[0].id, HunkState.REJECTED)
    assert review.final_content() == "first\nkeep\nlast revised\n"
    review.decide(review.hunks[0].id, HunkState.ACCEPTED)
    assert review.final_content() == after
    assert review.final_change().before_hash == content_hash(before)


@pytest.mark.parametrize("before,after,kind", [
    (None, "", FileChangeKind.CREATE),
    (None, "new\n", FileChangeKind.CREATE),
    ("", None, FileChangeKind.DELETE),
    ("old\n", None, FileChangeKind.DELETE),
])
def test_file_existence_changes_require_an_explicit_decision(before, after, kind):
    review = make_review(before, after, kind)
    assert len(review.hunks) == 1
    review.decide_all(HunkState.REJECTED)
    assert review.final_change() is None
    review.decide_all(HunkState.ACCEPTED)
    assert review.final_change().kind == kind
    assert review.final_change().after_content == after


def test_snapshot_is_immutable_and_unknown_hunk_is_rejected():
    from dataclasses import FrozenInstanceError
    review = make_review("a", "b")
    with pytest.raises(FrozenInstanceError):
        review.change = None
    with pytest.raises(KeyError):
        review.decide("missing", HunkState.ACCEPTED)


def test_long_repetitive_document_still_synthesizes_exact_snapshots():
    original = "A familiar line.\n\n" * 10000
    proposed = original[:20] + "New opening.\n" + original[20:-20] + "New ending.\n" + original[-20:]
    review = make_review(original, proposed)
    review.decide_all(HunkState.ACCEPTED)
    assert review.final_content() == proposed
    review.decide_all(HunkState.REJECTED)
    assert review.final_content() == original
