"""Automatic empty tabs give way to files without losing intentional drafts."""

import pytest

from test_close_project import open_file
from test_inline_review import review_window


def saved_project(window, parent):
    root = parent / "shelf-life"
    root.mkdir()
    (root / "one.md").write_bytes(b"First file")
    (root / "two.md").write_bytes(b"Second file")
    service = window.project_service
    project = service.repository.create("Shelf Life", root)
    service.set_project_setting(project.id, "editor_open_paths", ["one.md", "two.md"])
    service.set_project_setting(project.id, "editor_active_path", "one.md")
    return project


@pytest.mark.parametrize("route", ["folder", "recent", "switch", "after-close"])
def test_restoring_project_replaces_only_automatic_blank_tab(review_window, tmp_path, route):
    window, outgoing_root = review_window
    project = saved_project(window, tmp_path)
    if route in {"switch", "after-close"}:
        open_file(window, outgoing_root / "outgoing.md")
    if route != "switch":
        window._close_project()
    if route == "recent":
        window._open_registered_project(project.id)
    else:
        window._open_project_path(project.root_path)

    assert [s.path for s in window.editor_workspace.sessions()] == [
        project.root_path / "one.md", project.root_path / "two.md",
    ]
    assert window.current_file == str(project.root_path / "one.md")
    assert window.editor.toPlainText() == "First file"
    assert window.project_service.get_project_setting(project.id, "editor_open_paths") == ["one.md", "two.md"]
    assert window.project_service.get_project_setting(project.id, "editor_active_path") == "one.md"


def test_opening_first_file_replaces_initial_blank(review_window):
    window, root = review_window
    initial = window.editor_workspace.active_session()

    opened = open_file(window, root / "chapter.md")

    assert window.editor_workspace.session(initial.session_id) is None
    assert window.editor_workspace.sessions() == (opened,)
    assert window.current_file == str(opened.path)


@pytest.mark.parametrize("batch", [False, True])
def test_blank_created_after_last_tab_closes_is_replaced_by_next_file(review_window, batch):
    window, root = review_window
    workspace = window.editor_workspace
    original = workspace.active_session()
    window.editor.insertPlainText("Explicitly discarded scratch")
    if batch:
        workspace.close_documents([original.session_id])
    else:
        workspace.close_document(original.session_id)
    blank = workspace.active_session()
    assert blank.path is None and blank.content == ""

    opened = open_file(window, root / "chapter.md")

    assert workspace.sessions() == (opened,)
    assert workspace.session(blank.session_id) is None


@pytest.mark.parametrize("draft_kind", ["text", "whitespace", "cleared", "undone", "new-file", "clean-text"])
def test_project_restore_preserves_intentional_untitled_drafts(review_window, tmp_path, draft_kind):
    window, _ = review_window
    project = saved_project(window, tmp_path)
    workspace = window.editor_workspace
    if draft_kind == "new-file":
        window.new_file()
    draft = workspace.active_session()
    editor = window.editor
    if draft_kind != "new-file":
        editor.insertPlainText(" \n\t" if draft_kind == "whitespace" else "Keep this draft")
    if draft_kind == "cleared":
        editor.selectAll()
        editor.insertPlainText("")
    elif draft_kind == "undone":
        editor.undo()
    elif draft_kind == "clean-text":
        workspace.mark_clean(draft.session_id)
    expected = editor.toPlainText()

    window._open_project_path(project.root_path)

    assert workspace.session(draft.session_id) is draft
    assert [s for s in workspace.sessions() if s.path is None] == [draft]
    assert editor.toPlainText() == expected
    assert window.current_file == str(project.root_path / "one.md")
    if draft_kind == "cleared":
        editor.undo()
        assert editor.toPlainText() == "Keep this draft"
    elif draft_kind == "undone":
        editor.redo()
        assert editor.toPlainText() == "Keep this draft"


def test_empty_named_file_is_not_a_placeholder(review_window, tmp_path):
    window, root = review_window
    workspace = window.editor_workspace
    named = workspace.active_session()
    path = tmp_path / "Untitled 1.md"
    path.write_bytes(b"")
    workspace.assign_path(named.session_id, path)

    opened = open_file(window, root / "chapter.md")

    assert workspace.sessions() == (named, opened)
    assert named.path == path and named.content == ""


@pytest.mark.parametrize("saved_state", ["empty", "missing", "unreadable"])
def test_project_without_restorable_files_keeps_a_blank_editor(review_window, tmp_path, monkeypatch, saved_state):
    window, _ = review_window
    root = tmp_path / "empty-project"
    root.mkdir()
    service = window.project_service
    project = service.repository.create("Empty project", root)
    if saved_state != "empty":
        service.set_project_setting(project.id, "editor_open_paths", ["chapter.md"])
    if saved_state == "unreadable":
        (root / "chapter.md").write_bytes(b"Cannot be read")

        def fail(path):
            raise OSError("Test read failure")

        monkeypatch.setattr(window.document_service, "read_text", fail)

    window._open_registered_project(project.id)

    assert len(window.editor_workspace.sessions()) == 1
    assert window.editor_workspace.active_session().path is None
    assert window.editor.toPlainText() == ""
    assert not window.editor_workspace.dirty_sessions()
    assert window.project_explorer.project.id == project.id


def test_blank_with_pending_review_is_preserved_when_another_file_opens(review_window):
    window, root = review_window
    blank = window.editor_workspace.active_session()
    batch = window._start_editor_review("", "Proposed opening", "Draft opening")
    assert batch is not None

    opened = open_file(window, root / "chapter.md")

    assert window.editor_workspace.sessions() == (blank, opened)
    assert window.review_controller.batches[batch.id] is batch
    assert window.editor_workspace.review_for_session(blank.session_id) is not None
