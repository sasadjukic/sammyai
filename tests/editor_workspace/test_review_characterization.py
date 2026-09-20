"""Protect the existing buffer review contract before migrating its UI."""

from PySide6.QtWidgets import QApplication, QMessageBox

from test_main_window_multifile import FakeRuntimeServices, _project_components
from sammyai import TextEditor


def test_reviewed_buffer_edit_keeps_origin_and_single_step_undo(tmp_path):
    app = QApplication.instance() or QApplication([])
    paths, database, service, _ = _project_components(tmp_path)
    window = TextEditor(services=FakeRuntimeServices(service), app_paths=paths)
    try:
        origin = window.editor_workspace.active_session()
        origin_editor = window.editor
        origin_editor.insertPlainText("Original draft")
        window.editor_workspace.new_document()
        window.editor.insertPlainText("Other draft")
        assert window._apply_reviewed_editor_change(
            "Original draft", "Reviewed draft", session_id=origin.session_id
        )
        assert window.editor.toPlainText() == "Other draft"
        origin_editor.undo()
        assert origin_editor.toPlainText() == "Original draft"
        origin_editor.redo()
        assert origin_editor.toPlainText() == "Reviewed draft"
    finally:
        for session in window.editor_workspace.dirty_sessions():
            window.editor_workspace.mark_clean(session.session_id)
        window.close()
        database.close()
        app.processEvents()


def test_reviewed_buffer_edit_refuses_stale_snapshot(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    paths, database, service, _ = _project_components(tmp_path)
    window = TextEditor(services=FakeRuntimeServices(service), app_paths=paths)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    try:
        window.editor.insertPlainText("New writer text")
        assert not window._apply_reviewed_editor_change("Old text", "AI text")
        assert window.editor.toPlainText() == "New writer text"
    finally:
        window.editor_workspace.mark_clean(window.editor_workspace.active_session().session_id)
        window.close()
        database.close()
        app.processEvents()
