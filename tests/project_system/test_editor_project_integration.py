from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from llm.chat_manager import ChatManager
from sammyai import TextEditor
from sammyai_core.database import ProjectDatabase
from sammyai_core.paths import AppPaths
from sammyai_core.projects import ProjectRepository, ProjectService


class FakeRuntimeServices:
    def __init__(self, project_database, project_service):
        self.project_database = project_database
        self.project_service = project_service
        self.project_error = None
        self.rag_system = None
        self.rag_error = None
        self.chat_manager = ChatManager()
        self.chat_manager.create_session("project-ui")
        self.llm_config = SimpleNamespace(
            model_key="test-model",
            temperature=0.9,
            top_p=0.9,
            seed=None,
        )
        self.llm_client = None
        self.llm_error = "No test LLM configured"

    def shutdown(self):
        self.project_database.close()


def test_editor_restores_project_and_opens_tree_file(tmp_path):
    app = QApplication.instance() or QApplication([])
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
    chapter = root / "chapter-01.md"
    chapter.write_text("# Chapter One\n", encoding="utf-8")

    editor = TextEditor(
        services=FakeRuntimeServices(database, service),
        app_paths=paths,
    )

    assert editor.project_explorer.project.id == project.id
    assert editor.close_project_action.isEnabled()
    assert "Test" not in editor.windowTitle()
    assert project.name in editor.windowTitle()
    editor._populate_recent_projects_menu()
    assert editor.recent_projects_menu.actions()[0].text() == project.name

    editor._open_file_path(chapter)
    assert editor.editor.toPlainText() == "# Chapter One\n"
    assert editor.current_file == str(chapter.resolve())

    assert editor._apply_reviewed_editor_change(
        "# Chapter One\n",
        "# Revised Chapter\n",
    )
    assert editor.editor.toPlainText() == "# Revised Chapter\n"
    editor._on_undo()
    assert editor.editor.toPlainText() == "# Chapter One\n"

    editor._close_project()
    assert service.active_project is None
    assert editor.project_explorer.project is None
    assert editor.project_dock.isHidden()

    editor.close()
    app.processEvents()
