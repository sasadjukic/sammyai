from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from test_main_window_multifile import FakeRuntimeServices, TrackingRag, _project_components
from sammyai import TextEditor


@pytest.fixture
def window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    paths, database, service, project = _project_components(tmp_path)
    editor = TextEditor(services=FakeRuntimeServices(service, TrackingRag()), app_paths=paths)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    yield editor, project
    editor.close()
    editor.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    database.close()
    app.processEvents()


def test_new_context_menu_and_action_states_leave_legacy_dbe_available(window):
    editor, project = window
    assert [action.text() for action in editor.advanced_menu.actions()] == [
        "Persistent Memory", "Project Context", "", "Enable Legacy DBE Mode",
    ]
    assert [action.text() for action in editor.project_context_menu.actions()] == [
        "Import Reference File...", "Indexed Files...", "",
        "Rebuild Active Project Index...", "Context Index Statistics...", "Reset Entire Context Index...",
    ]
    assert editor.import_reference_action.isEnabled()
    assert editor.inspect_context_action.isEnabled()
    editor._close_project()
    assert not editor.import_reference_action.isEnabled()
    assert editor.inspect_context_action.isEnabled()
    editor._open_project_path(project.root_path)
    assert editor.import_reference_action.isEnabled()


def test_import_action_copies_and_schedules_only_project_sync(window, tmp_path, monkeypatch):
    editor, project = window
    source = tmp_path / "external.md"
    source.write_bytes(b"Research notes")
    syncs = []
    editor.context_engine = object()
    monkeypatch.setattr(editor, "_open_file_dialog", lambda *a: str(source))
    monkeypatch.setattr(editor, "_schedule_project_context_sync", lambda project, **kwargs: syncs.append(project.id))
    editor.import_reference_action.trigger()
    assert (project.root_path / "References" / "external.md").read_bytes() == b"Research notes"
    assert source.read_bytes() == b"Research notes"
    assert syncs == [project.id]
    assert "Synchronizing project context" in editor.statusBar().currentMessage()


def test_cancel_and_project_switch_during_file_picker_do_not_import(window, tmp_path, monkeypatch):
    editor, project = window
    monkeypatch.setattr(editor, "_open_file_dialog", lambda *a: None)
    editor._import_project_reference()
    assert not (project.root_path / "References").exists()
    source = tmp_path / "external.md"
    source.write_bytes(b"Research")
    def switch_project(*args):
        editor._close_project()
        return str(source)
    monkeypatch.setattr(editor, "_open_file_dialog", switch_project)
    editor._import_project_reference()
    assert not (project.root_path / "References").exists()


def test_inspector_does_not_invalidate_or_reset_index(window, monkeypatch):
    import sammyai
    editor, _project = window
    editor.context_engine = SimpleNamespace(invalidate_index_state=lambda: pytest.fail("Inspection must not invalidate context"))
    opened = []
    monkeypatch.setattr(sammyai, "ContextIndexDialog", lambda *a: SimpleNamespace(exec=lambda: opened.append(a)))
    editor.inspect_context_action.trigger()
    assert opened[0][:2] == (editor.rag_system, editor.project_service)
