from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QMessageBox,
)

from llm.chat_manager import ChatManager
from sammyai import TextEditor
from sammyai_core.database import ProjectDatabase
from sammyai_core.paths import AppPaths
from sammyai_core.projects import ProjectRepository, ProjectService
from ui.chat_panel import GENERIC_WELCOME_MESSAGES


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


def test_editor_restores_project_and_opens_tree_file(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    paths = AppPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        log_dir=tmp_path / "logs",
    ).ensure_created()
    database = ProjectDatabase(paths.project_database_path)
    database.migrate()
    repository = ProjectRepository(database)
    service = ProjectService(repository, paths)
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
    metadata = root / ".git"
    metadata.mkdir()
    config = metadata / "config"
    config.write_text("protected", encoding="utf-8")
    with pytest.raises(ValueError, match="Protected project metadata"):
        editor._active_project_file(config)
    editor._populate_recent_projects_menu()
    assert editor.recent_projects_menu.actions()[0].text() == project.name

    editor._create_chat_panel()
    assert editor.chat_panel.empty_title.full_text == (
        f"How can I help with {project.name}?"
    )

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

    context_syncs = []
    monkeypatch.setattr(
        editor,
        "_sync_after_file_tool_change",
        lambda: context_syncs.append(True),
    )
    editor._copy_project_file(str(chapter))
    assert editor.project_explorer.copied_file == chapter
    editor._paste_project_file(str(chapter), str(root))
    copied_chapter = root / "chapter-01 copy.md"
    assert copied_chapter.read_text(encoding="utf-8") == "# Chapter One\n"
    editor._paste_project_file(str(chapter), str(root))
    second_copy = root / "chapter-01 copy 2.md"
    assert second_copy.read_text(encoding="utf-8") == "# Chapter One\n"

    rename_results = iter(
        (("temporary.md", True), ("chapter-renamed.md", True))
    )
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        staticmethod(lambda *args, **kwargs: next(rename_results)),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *args, **kwargs: QMessageBox.Yes),
    )
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda *args, **kwargs: warnings.append(args[2])),
    )

    editor._rename_project_file(str(copied_chapter))
    temporary = root / "temporary.md"
    assert temporary.is_file()
    assert not copied_chapter.exists()
    editor._delete_project_file(str(temporary))
    assert not temporary.exists()

    editor._rename_project_file(str(chapter))
    renamed_chapter = root / "chapter-renamed.md"
    assert renamed_chapter.is_file()
    assert editor.current_file == str(renamed_chapter)

    editor.editor.document().setModified(True)
    editor._delete_project_file(str(renamed_chapter))
    assert renamed_chapter.is_file()
    assert warnings[-1].startswith("The selected file has unsaved edits")

    editor.editor.document().setModified(False)
    editor._delete_project_file(str(renamed_chapter))
    assert not renamed_chapter.exists()
    assert editor.current_file is None
    assert len(context_syncs) == 6

    editor._close_project()
    assert service.active_project is None
    assert editor.project_explorer.project is None
    assert editor.project_dock.isHidden()
    assert editor.chat_panel.empty_title.full_text in GENERIC_WELCOME_MESSAGES

    missing_root = tmp_path / "missing-project"
    relocated_root = tmp_path / "relocated-project"
    missing_root.mkdir()
    missing_project = service.open_project(missing_root)
    missing_root.rmdir()
    relocated_root.mkdir()

    editor._populate_recent_projects_menu()
    missing_action = next(
        action
        for action in editor.recent_projects_menu.actions()
        if action.text() == f"{missing_project.name} (missing)"
    )
    assert [action.text() for action in missing_action.menu().actions()] == [
        f"Last location: {missing_root.resolve()}",
        "",
        "Locate Moved Folder...",
        "Remove from SammyAI...",
    ]
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *args, **kwargs: str(relocated_root)),
    )
    missing_action.menu().actions()[2].trigger()
    assert service.active_project.id == missing_project.id
    assert service.active_project.root_path == relocated_root.resolve()

    session_id = editor.chat_manager.get_active_session().session_id
    assert editor.chat_manager.get_session_metadata("project_id") == missing_project.id
    editor._close_project()
    relocated_root.rmdir()
    editor._populate_recent_projects_menu()
    missing_action = next(
        action
        for action in editor.recent_projects_menu.actions()
        if action.text() == f"{missing_project.name} (missing)"
    )
    missing_action.menu().actions()[3].trigger()

    assert repository.get(missing_project.id) is None
    assert editor.chat_manager.get_session(session_id) is None
    assert not paths.project_data_dir(missing_project.id).exists()
    assert not paths.project_cache_dir(missing_project.id).exists()
    assert all(
        missing_project.name not in action.text()
        for action in editor.recent_projects_menu.actions()
    )

    editor.close()
    app.processEvents()
