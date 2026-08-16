from datetime import datetime, timezone

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import QApplication

from sammyai_core.projects import Project
from ui.project_explorer import ProjectExplorer


def make_project(root):
    now = datetime.now(timezone.utc)
    return Project(
        id="project-1",
        name="Test Novel",
        root_path=root,
        created_at=now,
        updated_at=now,
        last_opened_at=now,
    )


def test_explorer_roots_tree_and_emits_activated_files(tmp_path):
    app = QApplication.instance() or QApplication([])
    chapter = tmp_path / "chapter-01.md"
    chapter.write_text("# Chapter 1", encoding="utf-8")
    subdirectory = tmp_path / "notes"
    subdirectory.mkdir()

    explorer = ProjectExplorer()
    explorer.set_project(make_project(tmp_path))
    activated = []
    explorer.file_activated.connect(activated.append)

    explorer._on_activated(explorer.model.index(str(subdirectory)))
    assert activated == []

    explorer._on_activated(explorer.model.index(str(chapter)))
    assert activated == [str(chapter)]
    assert explorer.project_name_label.text() == "Test Novel"
    assert explorer.tree.rootIndex() == explorer.model.index(str(tmp_path))

    explorer.clear_project()
    assert explorer.project is None
    assert explorer.tree.isHidden()
    explorer.close()
    app.processEvents()


def test_file_context_menu_is_scoped_and_routes_file_actions(tmp_path):
    app = QApplication.instance() or QApplication([])
    chapter = tmp_path / "chapter-01.md"
    chapter.write_text("# Chapter 1", encoding="utf-8")
    notes = tmp_path / "notes"
    notes.mkdir()

    explorer = ProjectExplorer()
    explorer.set_project(make_project(tmp_path))
    copied = []
    pasted = []
    renamed = []
    deleted = []
    explorer.copy_requested.connect(copied.append)
    explorer.paste_requested.connect(lambda source, target: pasted.append((source, target)))
    explorer.rename_requested.connect(renamed.append)
    explorer.delete_requested.connect(deleted.append)

    def action(menu, text):
        return next(item for item in menu.actions() if item.text() == text)

    try:
        assert explorer.tree.contextMenuPolicy() == Qt.CustomContextMenu
        assert explorer.contextMenuPolicy() != Qt.CustomContextMenu

        file_menu = explorer._build_context_menu(explorer.model.index(str(chapter)))
        assert action(file_menu, "Copy").isEnabled()
        assert not action(file_menu, "Paste").isEnabled()
        assert action(file_menu, "Rename").isEnabled()
        assert action(file_menu, "Delete").isEnabled()

        action(file_menu, "Copy").trigger()
        action(file_menu, "Rename").trigger()
        action(file_menu, "Delete").trigger()
        assert copied == [str(chapter)]
        assert renamed == [str(chapter)]
        assert deleted == [str(chapter)]

        explorer.set_copied_file(chapter)
        file_menu = explorer._build_context_menu(explorer.model.index(str(chapter)))
        action(file_menu, "Paste").trigger()
        assert pasted[-1] == (str(chapter), str(tmp_path))

        directory_menu = explorer._build_context_menu(
            explorer.model.index(str(notes))
        )
        assert not action(directory_menu, "Copy").isEnabled()
        assert action(directory_menu, "Paste").isEnabled()
        assert not action(directory_menu, "Rename").isEnabled()
        assert not action(directory_menu, "Delete").isEnabled()
        action(directory_menu, "Paste").trigger()
        assert pasted[-1] == (str(chapter), str(notes))

        root_menu = explorer._build_context_menu(QModelIndex())
        assert action(root_menu, "Paste").isEnabled()
        action(root_menu, "Paste").trigger()
        assert pasted[-1] == (str(chapter), str(tmp_path))

        explorer.clear_project()
        assert explorer.copied_file is None
    finally:
        explorer.close()
        app.processEvents()
