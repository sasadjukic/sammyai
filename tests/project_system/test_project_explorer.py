from datetime import datetime, timezone

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
