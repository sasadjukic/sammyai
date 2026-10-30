"""Closing a project releases its tabs without discarding unsaved work."""

import pytest
from PySide6.QtWidgets import QMessageBox

from test_inline_review import review_window, start
from test_main_window_multifile import TrackingRag
from test_selection_actions import prepare
from sammyai_core.selection_actions import SelectionAction


def open_file(window, path, content="Original"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    window._open_file_path(path)
    return window.editor_workspace.active_session()


def test_close_project_removes_all_project_tabs_and_resets_editor_context(review_window):
    window, root = review_window
    workspace = window.editor_workspace
    initial = workspace.active_session()
    window.rag_system = TrackingRag()
    first = open_file(window, root / "one.md")
    second = open_file(window, root / "chapters" / "two.md")
    workspace.close_document(initial.session_id)
    assert window.rag_system.active_files == {str(second.path)}
    window._create_chat_panel()
    window.editor.selectAll()
    window.chat_panel.set_selection_reference(window.selection_actions.capture(second.session_id), pinned=True)

    window._close_project()

    assert window.project_service.active_project is None
    assert workspace.session(first.session_id) is None
    assert workspace.session(second.session_id) is None
    assert len(workspace.sessions()) == 1
    assert workspace.active_session().path is None
    assert not window.editor.toPlainText()
    assert window.current_file is None
    assert window._status_word.text() == "Words: 0"
    assert window._status_pos.text() == "Ln 1, Col 1"
    assert not window.rag_system.active_files
    assert not window.close_project_action.isEnabled()
    assert window.project_explorer.project is None
    assert window.project_dock.isHidden()
    assert root.name not in window.windowTitle()
    assert window.chat_panel.selection_reference is None
    assert (root / "one.md").read_bytes() == b"Original"


def test_close_preserves_unrelated_files_and_unsaved_untitled_drafts(review_window, tmp_path):
    window, root = review_window
    scratch = window.editor_workspace.active_session()
    window.editor.insertPlainText("Unsaved scratch")
    outside = open_file(window, tmp_path / "novel-backup" / "notes.md")
    window.editor.insertPlainText("Unsaved outside ")
    project_tab = open_file(window, root / "one.md")

    window._close_project()

    assert window.project_service.active_project is None
    assert window.editor_workspace.session(project_tab.session_id) is None
    assert set(s.session_id for s in window.editor_workspace.sessions()) == {scratch.session_id, outside.session_id}
    assert scratch.content == "Unsaved scratch"
    assert outside.content == "Unsaved outside Original"
    assert scratch.is_modified and outside.is_modified


@pytest.mark.parametrize("choice,expected", [(QMessageBox.Save, "Changed Original"), (QMessageBox.Discard, "Original")])
def test_project_close_resolves_dirty_background_tabs(review_window, monkeypatch, choice, expected):
    window, root = review_window
    dirty = open_file(window, root / "dirty.md")
    window.editor.insertPlainText("Changed ")
    open_file(window, root / "active.md")
    prompts = []
    def choose(*args, **kwargs):
        prompts.append(args[2])
        return choice
    monkeypatch.setattr(QMessageBox, "warning", choose)

    window._close_project()

    assert window.project_service.active_project is None
    assert window.editor_workspace.session(dirty.session_id) is None
    assert (root / "dirty.md").read_text(encoding="utf-8") == expected
    assert len(prompts) == 1 and "dirty.md" in prompts[0]


def test_cancel_later_dirty_prompt_keeps_every_tab_and_discarded_buffer(review_window, monkeypatch):
    window, root = review_window
    project = window.project_service.active_project
    clean = open_file(window, root / "clean.md")
    first = open_file(window, root / "one.md")
    window.editor.insertPlainText("One ")
    second = open_file(window, root / "two.md")
    window.editor.insertPlainText("Two ")
    sessions = window.editor_workspace.sessions()
    choices = iter([QMessageBox.Discard, QMessageBox.Cancel])
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: next(choices))

    window._close_project()

    assert window.project_service.active_project.id == project.id
    assert window.editor_workspace.sessions() == sessions
    assert window.editor_workspace.session(clean.session_id) is clean
    assert first.content == "One Original" and first.is_modified
    assert second.content == "Two Original" and second.is_modified
    assert window.close_project_action.isEnabled()
    assert (root / "one.md").read_bytes() == b"Original"


def test_failed_save_aborts_project_close(review_window, monkeypatch):
    window, root = review_window
    project = window.project_service.active_project
    tab = open_file(window, root / "one.md")
    window.editor.insertPlainText("Unsaved ")
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Save)
    errors = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: errors.append(a[2]))
    def fail(*args):
        raise OSError("Cannot write test file")
    monkeypatch.setattr(window.document_service, "write_text", fail)

    window._close_project()

    assert window.project_service.active_project.id == project.id
    assert window.editor_workspace.session(tab.session_id) is tab
    assert tab.is_modified and tab.content == "Unsaved Original"
    assert errors == ["Cannot write test file"]


def test_close_retains_layout_for_reopen_and_does_not_carry_tabs_to_next_project(review_window, tmp_path):
    window, root = review_window
    service = window.project_service
    project = service.active_project
    first = open_file(window, root / "one.md")
    second = open_file(window, root / "two.md")
    window.editor_workspace.activate_document(first.session_id)

    window._close_project()

    assert service.get_project_setting(project.id, "editor_open_paths") == ["one.md", "two.md"]
    assert service.get_project_setting(project.id, "editor_active_path") == "one.md"
    other = tmp_path / "next-project"
    other.mkdir()
    window._open_project_path(other)
    assert all(s.path is None for s in window.editor_workspace.sessions())
    window._close_project()
    window._open_registered_project(project.id)
    assert {s.path for s in window.editor_workspace.sessions() if s.path} == {first.path, second.path}
    assert window.current_file == str(first.path)


def test_canceling_pending_review_keeps_project_and_tabs(review_window):
    window, root = review_window
    project = window.project_service.active_project
    batch = start(window, root)
    sessions = window.editor_workspace.sessions()

    window._close_project()  # fixture answers Cancel

    assert window.project_service.active_project.id == project.id
    assert window.editor_workspace.sessions() == sessions
    assert window.review_controller.batches[batch.id] is batch


def test_discarding_pending_review_closes_tabs_without_applying_or_restoring_unsaved_proposals(review_window, monkeypatch):
    window, root = review_window
    project = window.project_service.active_project
    start(window, root, {"one.md": ("Original", "Proposed"), "new.md": (None, "New proposal")})
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Discard)

    window._close_project()

    assert window.project_service.active_project is None
    assert not window.review_controller.batches
    assert all(s.path is None for s in window.editor_workspace.sessions())
    assert (root / "one.md").read_bytes() == b"Original"
    assert not (root / "new.md").exists()
    assert window.project_service.get_project_setting(project.id, "editor_open_paths") == ["one.md"]


def test_cancel_dirty_close_leaves_other_pending_review_untouched(review_window):
    window, root = review_window
    batch = start(window, root)
    dirty = open_file(window, root / "dirty.md")
    window.editor.insertPlainText("Unsaved ")

    window._close_project()

    assert window.project_service.active_project is not None
    assert window.review_controller.batches[batch.id] is batch
    assert window.editor_workspace.session(dirty.session_id) is dirty


def test_close_cancels_running_selection_request_and_ignores_late_reply(review_window, monkeypatch):
    window, root = review_window
    tab = open_file(window, root / "one.md", "Before.\nOld passage.\nAfter.")
    snapshot, _, workers = prepare(
        window, monkeypatch, '{"kind":"replacement","text":"New passage."}', deferred=True,
    )
    window.selection_actions.start(snapshot, SelectionAction.REWRITE)
    pending = window.selection_actions.pending
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Discard)

    window._close_project()
    workers.pop()()

    assert window.project_service.active_project is None
    assert window.editor_workspace.session(tab.session_id) is None
    assert window.selection_actions.pending is None
    assert pending.canceled.is_set()
    assert not window.review_controller.batches
    assert all(s.path is None for s in window.editor_workspace.sessions())
    assert (root / "one.md").read_bytes() == b"Before.\nOld passage.\nAfter."
    assert window.trace_service.detail(pending.identity.request_id)["request"]["outcome"] == "canceled"
