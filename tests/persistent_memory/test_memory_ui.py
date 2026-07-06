from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from sammyai_core.database import ProjectDatabase
from sammyai_core.memory import (
    ConversationSummaryDraft,
    MemoryKind,
    MemoryRepository,
    ProjectMemoryService,
    SuggestedMemory,
)
from sammyai_core.paths import AppPaths
from sammyai_core.projects import ProjectRepository, ProjectService
from ui.memory_management import (
    MemoryManagementDialog,
    SummaryReviewDialog,
)


def test_memory_management_and_summary_review_render(tmp_path):
    app = QApplication.instance() or QApplication([])
    paths = AppPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        log_dir=tmp_path / "logs",
    ).ensure_created()
    database = ProjectDatabase(paths.project_database_path)
    database.migrate()
    project_service = ProjectService(
        ProjectRepository(database),
        paths,
    )
    root = tmp_path / "novel"
    root.mkdir()
    project = project_service.open_project(root)
    service = ProjectMemoryService(MemoryRepository(database), project_service)
    service.create_memory(
        MemoryKind.CHARACTER,
        "Mara's fear",
        "Mara is afraid of open water.",
    )

    manager = MemoryManagementDialog(service)
    assert manager.memory_table.rowCount() == 1
    manager.memory_table.selectRow(0)
    app.processEvents()
    assert "open water" in manager.memory_detail.toPlainText()

    draft = ConversationSummaryDraft(
        project_id=project.id,
        session_id="session",
        title="Session summary",
        content="A concise summary.",
        message_count=2,
        suggested_memories=(
            SuggestedMemory(
                MemoryKind.PLOT,
                "Reveal",
                "The map is forged.",
            ),
        ),
    )
    review = SummaryReviewDialog(draft)
    assert review.suggestions_table.rowCount() == 1
    assert review.suggestions_table.item(0, 0).checkState() == Qt.Checked
    assert review.selected_memory_indices() == (0,)
    review.suggestions_table.item(0, 3).setText("The map is a forgery.")
    assert (
        review.reviewed_draft().suggested_memories[0].content
        == "The map is a forgery."
    )

    review.close()
    manager.close()
    app.processEvents()
    database.close()
