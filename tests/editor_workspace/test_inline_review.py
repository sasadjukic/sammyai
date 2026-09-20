"""Exercise actual tab widgets, controller, and file history without an LLM."""

import os
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QMessageBox

from test_main_window_multifile import FakeRuntimeServices, _project_components
from editing.change_sets import FileChangeRequest
from editing.review_session import HunkState
from sammyai import TextEditor
from sammyai_core.agent_workflows import AgentRunResult, AgentType
from sammyai_core.file_tools import FileToolError, SafeFileTools


@pytest.fixture
def review_window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    paths, database, service, project = _project_components(tmp_path)
    runtime = FakeRuntimeServices(service)
    runtime.file_tools = SafeFileTools(service)
    window = TextEditor(services=runtime, app_paths=paths)
    window.popup_review_fallback = False
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Cancel)
    yield window, project.root_path
    window.review_controller.cancel_all()
    for session in window.editor_workspace.dirty_sessions():
        window.editor_workspace.mark_clean(session.session_id)
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    database.close()
    app.processEvents()


def start(window, root, contents=None):
    contents = contents or {"one.md": ("old\nkeep\nlast\n", "new\nextra\nkeep\nend\n")}
    requests = []
    for name, (before, after) in contents.items():
        if before is not None:
            (root / name).write_bytes(before.encode("utf-8"))
        requests.append(FileChangeRequest.delete(name) if after is None else FileChangeRequest.write(name, after))
    source = window.file_tools.prepare_change_set(requests, description="Revise the scene")
    batch = window.review_controller.start_change_set(source, agent_id="run", chat_session_id="origin-chat")
    return batch


def test_hunk_controls_keep_real_buffer_clean_and_stay_on_origin_tab(review_window):
    window, root = review_window
    batch = start(window, root)
    review = batch.reviews[0]
    workspace = window.editor_workspace
    view = workspace.review_for_session(review.target_document_id)
    editor = workspace.editor_for_session(review.target_document_id)
    assert editor.isReadOnly()
    assert not editor.document().isModified()
    assert editor.toPlainText() == "old\nkeep\nlast\n"
    assert not view.apply_button.isEnabled()
    view.accept_button.click()
    view.next_button.click()
    view.reject_button.click()
    assert "ACCEPTED" in view.view.toPlainText()
    assert "REJECTED" in view.view.toPlainText()
    assert view.apply_button.isEnabled()
    assert review.originating_session_id == "origin-chat"
    other = workspace.new_document()
    window.editor.insertPlainText("Other tab")
    window.chat_manager.create_session("other-chat")
    view.apply_button.click()
    assert workspace.active_session() is other
    assert window.editor.toPlainText() == "Other tab"
    assert (root / "one.md").read_bytes() == b"new\nextra\nkeep\nlast\n"
    assert editor.toPlainText() == "new\nextra\nkeep\nlast\n"
    assert not editor.isReadOnly()
    window._undo_last_change_set()
    assert (root / "one.md").read_bytes() == b"old\nkeep\nlast\n"
    window._redo_last_change_set()
    assert (root / "one.md").read_bytes() == b"new\nextra\nkeep\nlast\n"


def test_multi_file_decisions_apply_atomically_and_keep_crlf(review_window):
    window, root = review_window
    batch = start(window, root, {
        "one.md": ("a\r\nb\r\n", "A\r\nb\r\n"),
        "two.txt": ("old\n", "new\n"),
        "empty.txt": (None, ""),
        "delete.md": ("obsolete", None),
    })
    for review in batch.reviews[:-1]:
        window.editor_workspace.review_for_session(review.target_document_id).accept_all_button.click()
    assert not window.review_controller.apply(batch.id)
    assert (root / "one.md").read_bytes() == b"a\r\nb\r\n"
    batch.reviews[-1].decide_all(HunkState.ACCEPTED)
    assert window.review_controller.apply(batch.id)
    assert (root / "one.md").read_bytes() == b"A\r\nb\r\n"
    assert (root / "empty.txt").read_bytes() == b""
    assert not (root / "delete.md").exists()
    window._undo_last_change_set()
    assert (root / "one.md").read_bytes() == b"a\r\nb\r\n"
    assert (root / "delete.md").read_bytes() == b"obsolete"
    assert not (root / "empty.txt").exists()


@pytest.mark.parametrize("mutation", ["disk", "buffer", "project", "delete", "undo-buffer"])
def test_conflicts_block_all_writes_and_leave_review_cancelable(review_window, mutation):
    window, root = review_window
    batch = start(window, root, {"one.md": ("old", "new"), "two.md": ("two", "changed")})
    for review in batch.reviews:
        review.decide_all(HunkState.ACCEPTED)
    editor = window.editor_workspace.editor_for_session(batch.reviews[0].target_document_id)
    if mutation == "disk":
        (root / "one.md").write_bytes(b"external")
    elif mutation in {"buffer", "undo-buffer"}:
        cursor = QTextCursor(editor.document())
        cursor.insertText("writer ")
        if mutation == "undo-buffer":
            editor.document().undo()
    elif mutation == "delete":
        (root / "one.md").unlink()
    else:
        window.project_service.close_project()
    assert not window.review_controller.apply(batch.id)
    assert (root / "two.md").read_bytes() == b"two"
    widget = window.editor_workspace.review_for_session(batch.reviews[0].target_document_id)
    assert "Conflict:" in widget.status_label.text()
    assert not widget.apply_button.isEnabled()
    widget.cancel_button.click()
    assert not editor.isReadOnly()
    assert not window.review_controller.batches


def test_dirty_background_tab_blocks_review_before_other_tabs_open(review_window):
    window, root = review_window
    (root / "one.md").write_bytes(b"one")
    (root / "two.md").write_bytes(b"two")
    window._open_file_path(root / "two.md")
    window.editor.insertPlainText("dirty ")
    window.editor_workspace.new_document()
    source = window.file_tools.prepare_change_set([
        FileChangeRequest.write("one.md", "new one"),
        FileChangeRequest.write("two.md", "new two"),
    ], description="Both")
    with pytest.raises(FileToolError, match="unsaved"):
        window.review_controller.start_change_set(source)
    assert not window.editor_workspace.sessions_for_path(root / "one.md")
    assert not window.review_controller.batches


def test_cancel_and_reject_all_remove_only_unwritten_create_tabs(review_window):
    window, root = review_window
    batch = start(window, root, {"new.md": (None, "New draft"), "one.md": ("old", "new")})
    for review in batch.reviews:
        review.decide_all(HunkState.REJECTED)
    assert window.review_controller.apply(batch.id)
    assert not (root / "new.md").exists()
    assert not window.editor_workspace.sessions_for_path(root / "new.md")
    assert window.editor_workspace.sessions_for_path(root / "one.md")
    assert not window.file_tools.can_undo
    assert (root / "one.md").read_bytes() == b"old"


def test_dbe_draft_review_retains_qt_undo_and_checks_external_file(review_window):
    window, root = review_window
    window.editor.insertPlainText("Original draft")
    origin = window.editor_workspace.active_session()
    window._show_dbe_diff({"session_id": origin.session_id, "original": "Original draft", "modified": "Revised draft", "user_request": "Revise", "chat_session_id": "chat"})
    view = window.editor_workspace.review_for_session(origin.session_id)
    assert view is not None
    assert view.apply_button.text() == "Apply to Draft"
    view.accept_all_button.click()
    view.apply_button.click()
    assert window.editor.toPlainText() == "Revised draft"
    window.editor.undo()
    assert window.editor.toPlainText() == "Original draft"
    window.editor.redo()
    assert window.editor.toPlainText() == "Revised draft"


def test_saved_dbe_uses_safe_file_history_and_origin_after_switch(review_window):
    window, root = review_window
    (root / "one.md").write_bytes(b"old\r\n")
    window._open_file_path(root / "one.md")
    origin = window.editor_workspace.active_session()
    window.editor_workspace.new_document()
    window._show_dbe_diff({"session_id": origin.session_id, "original": "old\n", "modified": "new\n", "user_request": "Revise"})
    batch = window.review_controller.batch_for_document(origin.session_id)
    assert batch.change_set is not None
    batch.reviews[0].decide_all(HunkState.ACCEPTED)
    assert window.review_controller.apply(batch.id)
    assert (root / "one.md").read_bytes() == b"new\r\n"
    assert window.file_tools.can_undo


def test_save_replace_close_and_history_are_guarded_while_reviewing(review_window):
    window, root = review_window
    batch = start(window, root)
    origin = batch.reviews[0].target_document_id
    assert not window.save_file()
    assert not window.save_file_as()
    assert not window.close_file()  # fixture chooses Cancel
    assert not window.close()
    assert window.runtime_services.shutdown_calls == 0
    assert window._current_document_conflicts_with(batch.change_set)
    with pytest.raises(ValueError, match="review"):
        window._ensure_file_operation_has_no_unsaved_conflict(root / "one.md")
    window.search_widget.search_input.setText("old")
    window.search_widget.replace_input.setText("oops")
    window._replace_all()
    assert window.editor.toPlainText().startswith("old")
    window.editor_workspace.close_document(origin)
    assert not window.review_controller.batches


def test_agent_result_routes_inline_and_keeps_origin_metadata(review_window):
    window, root = review_window
    (root / "one.md").write_bytes(b"old")
    source = window.file_tools.prepare_change_set([FileChangeRequest.write("one.md", "new")], description="Revise")
    result = AgentRunResult("agent-run", AgentType.EDITOR, "A proposal", (), 1, source, window.file_tools.preview(source), originating_session_id="original-chat")
    window._handle_agent_run_result(result)
    review = next(iter(window.review_controller.batches.values())).reviews[0]
    assert review.originating_session_id == "original-chat"
    assert review.originating_agent_id == "agent-run"
    assert (root / "one.md").read_bytes() == b"old"


def test_inline_apply_failure_rolls_back_without_losing_review(review_window, monkeypatch):
    window, root = review_window
    batch = start(window, root, {"one.md": ("one", "new"), "two.md": ("two", "new")})
    for review in batch.reviews:
        review.decide_all(HunkState.ACCEPTED)
    calls = []
    def fail_second(source, target):
        calls.append(target)
        if len(calls) == 2:
            raise OSError("Simulated failure")
        os.replace(source, target)
    monkeypatch.setattr(window.file_tools, "_replace", fail_second)
    assert not window.review_controller.apply(batch.id)
    assert (root / "one.md").read_bytes() == b"one"
    assert (root / "two.md").read_bytes() == b"two"
    assert window.review_controller.batches
    assert not window.file_tools.can_undo


def test_theme_tokens_and_controls_are_accessible(review_window):
    from ui.inline_review import review_color
    window, root = review_window
    app = QApplication.instance()
    previous = app.styleSheet()
    try:
        app.setStyleSheet(Path("ui/styles/dark_theme.qss").read_text(encoding="utf-8"))
        batch = start(window, root)
        view = window.editor_workspace.review_for_session(batch.reviews[0].target_document_id)
        assert review_color("Addition", "background-color") == "#193c2b"
        assert review_color("Deletion", "color") == "#f2b8bd"
        for button in (view.accept_button, view.reject_button, view.accept_all_button, view.reject_all_button, view.previous_button, view.next_button, view.apply_button, view.cancel_button):
            assert button.text() and button.toolTip() and button.accessibleName()
        assert "−   old" in view.view.toPlainText()
        assert "+   new" in view.view.toPlainText()
    finally:
        app.setStyleSheet(previous)


def test_find_and_copy_review_text_preserve_the_current_hunk_layer(review_window):
    window, root = review_window
    batch = start(window, root)
    view = window.editor_workspace.review_for_session(batch.reviews[0].target_document_id)
    window._on_search_text_changed("new")
    assert window.current_matches
    assert window.editor_workspace.active_text_surface() is view.view
    window._on_copy()
    assert QApplication.clipboard().text() == "new"
    assert view.decorations.layers["review-current"]
    assert view.decorations.layers["search"]
    assert window.editor.decorations.layers.get("search", []) == []
    view.accept_button.click()
    assert not window.current_matches  # hidden search was invalidated after redraw


def test_second_proposal_does_not_replace_pending_decisions(review_window):
    window, root = review_window
    batch = start(window, root)
    batch.reviews[0].decide_all(HunkState.REJECTED)
    with pytest.raises(FileToolError, match="existing review"):
        window.review_controller.start_change_set(batch.change_set)
    assert window.review_controller.batches[batch.id] is batch
    assert batch.reviews[0].final_change() is None


def test_dirty_saved_draft_cannot_apply_over_external_modification(review_window):
    window, root = review_window
    path = root / "one.md"
    path.write_bytes(b"saved")
    window._open_file_path(path)
    window.editor.insertPlainText("unsaved ")
    batch = window._start_editor_review(window.editor.toPlainText(), "proposal", "Revise")
    assert batch.change_set is None
    path.write_bytes(b"external")
    batch.reviews[0].decide_all(HunkState.ACCEPTED)
    assert not window.review_controller.apply(batch.id)
    assert window.editor.toPlainText() == "unsaved saved"
    assert path.read_bytes() == b"external"


def test_project_switch_cancel_preserves_current_project_and_review(review_window):
    window, root = review_window
    batch = start(window, root)
    other = root.parent / "other"
    other.mkdir()
    window._open_project_path(other)  # fixture chooses Cancel
    assert window.project_service.active_project.root_path == root
    assert batch.id in window.review_controller.batches


def test_cancel_then_reopen_has_no_proposal_markers_or_pending_decisions(review_window):
    window, root = review_window
    batch = start(window, root)
    batch.reviews[0].decide_all(HunkState.ACCEPTED)
    window.review_controller.cancel_all()
    document_id = batch.reviews[0].target_document_id
    window.editor_workspace.close_document(document_id)
    window._open_file_path(root / "one.md")
    assert window.editor.toPlainText() == "old\nkeep\nlast\n"
    assert not window.review_controller.batches
    assert "@@" not in window.editor.toPlainText()


def test_dbe_result_does_not_follow_save_as_during_model_request(review_window):
    window, root = review_window
    window.editor.insertPlainText("Draft")
    session = window.editor_workspace.active_session()
    window.editor_workspace.assign_path(session.session_id, root / "renamed.md")
    window._show_dbe_diff({
        "session_id": session.session_id, "original": "Draft", "modified": "New",
        "user_request": "Revise", "document_path": None,
    })
    assert not window.review_controller.batches
    assert window.editor.toPlainText() == "Draft"


def test_cancel_crlf_review_does_not_make_undo_to_clean_dirty(review_window):
    window, root = review_window
    batch = start(window, root, {"one.md": ("old\r\n", "new\r\n")})
    window.review_controller.cancel(batch.id)
    session = window.editor_workspace.active_session()
    window.editor.insertPlainText("edit ")
    window.editor.undo()
    assert not window.editor_workspace.is_modified(session.session_id)


@pytest.mark.parametrize("mode", ["file", "clipboard", "patch"])
def test_manual_comparisons_route_through_inline_review(review_window, monkeypatch, mode):
    window, root = review_window
    window.editor.insertPlainText("old\n")
    proposed = "new\n"
    if mode == "clipboard":
        QApplication.clipboard().setText(proposed)
        window._compare_with_clipboard()
    else:
        path = root / ("source.patch" if mode == "patch" else "source.txt")
        path.write_text(str(window.diff_manager.generate_diff("old\n", proposed)) if mode == "patch" else proposed, encoding="utf-8")
        monkeypatch.setattr(window, "_open_file_dialog", lambda *a: str(path))
        (window._apply_diff_from_file if mode == "patch" else window._compare_with_file)()
    batch = next(iter(window.review_controller.batches.values()))
    assert window.editor.toPlainText() == "old\n"
    batch.reviews[0].decide_all(HunkState.ACCEPTED)
    assert window.review_controller.apply(batch.id)
    assert window.editor.toPlainText() == proposed
    window.editor.undo()
    assert window.editor.toPlainText() == "old\n"


def test_agent_request_rejects_proposal_prepared_in_another_project(review_window, monkeypatch):
    from dataclasses import replace
    from types import SimpleNamespace
    window, root = review_window
    source = window.file_tools.prepare_change_set([FileChangeRequest.write("new.md", "draft")], description="Create")
    source = replace(source, project_id="different-project")
    result = AgentRunResult("run", AgentType.WRITER, "Proposal", (), 1, source, window.file_tools.preview(source))
    window.agent_workflows = SimpleNamespace(run=lambda *a, **k: result)
    window.llm_client = SimpleNamespace(system_prompt="test")
    monkeypatch.setattr(window.task_runner, "submit", lambda fn, **kwargs: fn())
    results = []
    window.agent_run_completed.connect(results.append)
    window._handle_normal_chat("Write a chapter")
    assert results and results[0].change_set is None
    assert "project changed" in results[0].notices[0]
    assert not window.review_controller.batches
    assert not (root / "new.md").exists()
