from pathlib import Path

from sammyai_core.document_session import (
    DocumentSession,
    normalize_document_path,
)


def test_document_session_tracks_clean_and_dirty_transitions(tmp_path):
    path = tmp_path / "chapter.md"
    session = DocumentSession.from_path(path, "First draft")

    assert session.path == path.resolve()
    assert session.display_name == "chapter.md"
    assert session.format_id == "markdown"
    assert not session.is_modified

    session.update_content("Second draft")
    assert session.is_modified

    session.update_content("First draft")
    assert not session.is_modified

    session.update_content("Final draft")
    session.mark_clean()
    assert session.clean_snapshot == "Final draft"
    assert not session.is_modified


def test_untitled_sessions_have_stable_unique_ids_and_can_be_named(tmp_path):
    first = DocumentSession.untitled(1)
    second = DocumentSession.untitled(2)

    assert first.display_name == "Untitled 1"
    assert second.display_name == "Untitled 2"
    assert first.session_id != second.session_id

    target = tmp_path / "notes.txt"
    first.assign_path(target)
    assert first.path == target.resolve()
    assert first.display_name == "notes.txt"
    assert first.format_id == "plain_text"


def test_path_normalization_does_not_require_an_existing_file(tmp_path):
    nested = tmp_path / "drafts" / ".." / "chapter.md"

    assert normalize_document_path(nested) == normalize_document_path(
        Path(tmp_path) / "chapter.md"
    )

