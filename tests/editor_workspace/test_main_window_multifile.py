from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from llm.chat_manager import ChatManager
from sammyai import TextEditor
from sammyai_core.database import ProjectDatabase
from sammyai_core.paths import AppPaths
from sammyai_core.projects import ProjectRepository, ProjectService


class TrackingRag:
    def __init__(self):
        self.active_files = set()

    def mark_active_file(self, path):
        self.active_files.add(str(path))

    def unmark_active_file(self, path):
        self.active_files.discard(str(path))


class FakeRuntimeServices:
    def __init__(self, project_service, rag_system=None):
        self.project_service = project_service
        self.project_error = None
        self.rag_system = rag_system
        self.rag_error = None
        self.context_engine = None
        self.file_tools = None
        self.memory_service = None
        self.chat_manager = ChatManager()
        self.chat_manager.create_session("multi-file-test")
        self.llm_config = SimpleNamespace(
            model_key="test-model",
            temperature=0.9,
            top_p=0.9,
            seed=None,
        )
        self.llm_client = None
        self.llm_error = "No test LLM configured"
        self.shutdown_calls = 0

    def shutdown(self):
        self.shutdown_calls += 1


def _project_components(tmp_path):
    paths = AppPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        log_dir=tmp_path / "logs",
    ).ensure_created()
    database = ProjectDatabase(paths.project_database_path)
    database.migrate()
    service = ProjectService(ProjectRepository(database), paths)
    root = tmp_path / "novel"
    root.mkdir()
    project = service.open_project(root)
    return paths, database, service, project


def test_main_window_switches_active_file_and_protects_dirty_background_tab(
    tmp_path,
):
    app = QApplication.instance() or QApplication([])
    paths, database, service, _project = _project_components(tmp_path)
    rag = TrackingRag()
    first_path = tmp_path / "novel" / "one.md"
    second_path = tmp_path / "novel" / "two.md"
    first_path.write_text("One first document", encoding="utf-8")
    second_path.write_text("Two", encoding="utf-8")
    window = TextEditor(
        services=FakeRuntimeServices(service, rag),
        app_paths=paths,
    )

    try:
        window._open_file_path(first_path)
        first = window.editor_workspace.active_session()
        window.editor.insertPlainText("Changed ")
        window._open_file_path(second_path)
        second = window.editor_workspace.active_session()

        assert window.current_file == str(second_path.resolve())
        assert rag.active_files == {str(second_path.resolve())}
        assert window.editor_workspace.session(first.session_id).content == (
            "Changed One first document"
        )
        assert window._status_word.text() == "Words: 1"

        change_set = SimpleNamespace(
            changes=(SimpleNamespace(relative_path="one.md"),)
        )
        assert window._current_document_conflicts_with(change_set)

        window.editor_workspace.activate_document(first.session_id)
        assert window.editor.toPlainText() == "Changed One first document"
        assert window._status_word.text() == "Words: 4"
        assert rag.active_files == {str(first_path.resolve())}

        window.editor_workspace.activate_document(second.session_id)
        second_path.write_text("Externally updated", encoding="utf-8")
        window.editor_workspace.activate_document(first.session_id)
        window._reload_current_file_if_changed(("two.md",))
        second_editor = window.editor_workspace.editor_for_session(second.session_id)
        assert second_editor.toPlainText() == "Externally updated"
    finally:
        for session in window.editor_workspace.dirty_sessions():
            window.editor_workspace.mark_clean(session.session_id)
        window.close()
        database.close()
        app.processEvents()


def test_dirty_tab_cancel_keeps_document_open(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    paths, database, service, _project = _project_components(tmp_path)
    window = TextEditor(
        services=FakeRuntimeServices(service),
        app_paths=paths,
    )

    try:
        session = window.editor_workspace.active_session()
        window.editor.insertPlainText("Unsaved")
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            staticmethod(lambda *args, **kwargs: QMessageBox.Cancel),
        )

        assert not window.close_file()
        assert window.editor_workspace.session(session.session_id) is session
        assert window.editor.toPlainText() == "Unsaved"

        monkeypatch.setattr(
            QMessageBox,
            "warning",
            staticmethod(lambda *args, **kwargs: QMessageBox.Discard),
        )
        assert window.close_file()
        assert window.editor_workspace.session(session.session_id) is None
    finally:
        window.close()
        database.close()
        app.processEvents()


def test_save_as_names_the_active_tab_and_clears_its_dirty_marker(
    tmp_path,
    monkeypatch,
):
    app = QApplication.instance() or QApplication([])
    paths, database, service, project = _project_components(tmp_path)
    window = TextEditor(
        services=FakeRuntimeServices(service),
        app_paths=paths,
    )
    target = project.root_path / "new-chapter.md"

    try:
        window.editor.insertPlainText("A new chapter")
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            staticmethod(lambda *args, **kwargs: (str(target), "")),
        )

        assert window.save_file_as()
        assert target.read_text(encoding="utf-8") == "A new chapter"
        assert window.current_file == str(target.resolve())
        assert window.editor_workspace.tabs.tabText(
            window.editor_workspace.tabs.currentIndex()
        ) == "new-chapter.md"
        assert not window.editor_workspace.active_session().is_modified
    finally:
        window.close()
        database.close()
        app.processEvents()


def test_canceling_quit_keeps_all_dirty_tabs_and_services_running(
    tmp_path,
    monkeypatch,
):
    app = QApplication.instance() or QApplication([])
    paths, database, service, _project = _project_components(tmp_path)
    runtime = FakeRuntimeServices(service)
    window = TextEditor(services=runtime, app_paths=paths)
    first = window.editor_workspace.active_session()
    window.editor.insertPlainText("First unsaved draft")
    second = window.editor_workspace.new_document()
    window.editor.insertPlainText("Second unsaved draft")
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda *args, **kwargs: QMessageBox.Cancel),
    )

    try:
        assert not window.close()
        assert runtime.shutdown_calls == 0
        assert window.editor_workspace.session(first.session_id) is first
        assert window.editor_workspace.session(second.session_id) is second
    finally:
        for session in window.editor_workspace.dirty_sessions():
            window.editor_workspace.mark_clean(session.session_id)
        window.close()
        database.close()
        app.processEvents()


def test_last_tab_removal_handles_transient_no_active_document_state(tmp_path):
    app = QApplication.instance() or QApplication([])
    paths, database, service, _project = _project_components(tmp_path)
    window = TextEditor(
        services=FakeRuntimeServices(service),
        app_paths=paths,
    )

    try:
        session = window.editor_workspace.active_session()
        window.editor.insertPlainText("Two words")
        assert window._status_word.text() == "Words: 2"
        assert window._status_pos.text() == "Ln 1, Col 10"

        window.editor_workspace.close_document(
            session.session_id,
            ensure_document=False,
        )

        assert window.editor_workspace.active_session() is None
        assert window._status_word.text() == "Words: 0"
        assert window._status_pos.text() == "Ln 1, Col 1"
        assert "No Document" in window.windowTitle()

        replacement = window.editor_workspace.new_document()
        assert replacement.display_name == "Untitled 2"
        assert window.editor_workspace.active_session() is replacement
    finally:
        window.close()
        database.close()
        app.processEvents()


def test_project_restoration_skips_missing_files_and_restores_active_tab(tmp_path):
    app = QApplication.instance() or QApplication([])
    paths, database, service, project = _project_components(tmp_path)
    first_path = project.root_path / "one.md"
    second_path = project.root_path / "two.txt"
    first_path.write_text("One", encoding="utf-8")
    second_path.write_text("Two", encoding="utf-8")
    first_window = TextEditor(
        services=FakeRuntimeServices(service),
        app_paths=paths,
    )
    first_window._open_file_path(first_path)
    first_window._open_file_path(second_path)
    service.set_project_setting(
        project.id,
        "editor_open_paths",
        ["one.md", "missing.md", "two.txt", "../outside.md"],
    )
    service.set_project_setting(project.id, "editor_active_path", "two.txt")

    second_window = TextEditor(
        services=FakeRuntimeServices(service),
        app_paths=paths,
    )
    try:
        restored_paths = {
            session.path
            for session in second_window.editor_workspace.sessions()
            if session.path is not None
        }
        assert restored_paths == {first_path.resolve(), second_path.resolve()}
        assert second_window.current_file == str(second_path.resolve())
    finally:
        second_window.close()
        first_window.close()
        database.close()
        app.processEvents()
