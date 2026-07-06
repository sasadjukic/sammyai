import pytest

from sammyai_core.database import ProjectDatabase
from sammyai_core.memory import (
    ConversationSummaryDraft,
    MemoryDuplicateError,
    MemoryError,
    MemoryKind,
    MemoryRepository,
    MemoryStatus,
    ProjectMemoryService,
    ProvenanceType,
    SuggestedMemory,
)
from sammyai_core.paths import AppPaths
from sammyai_core.projects import ProjectRepository, ProjectService


@pytest.fixture
def memory_components(tmp_path):
    paths = AppPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        log_dir=tmp_path / "logs",
    ).ensure_created()
    database = ProjectDatabase(paths.project_database_path)
    database.migrate()
    project_service = ProjectService(ProjectRepository(database), paths)
    root = tmp_path / "novel"
    root.mkdir()
    project = project_service.open_project(root)
    repository = MemoryRepository(database)
    service = ProjectMemoryService(repository, project_service)
    try:
        yield database, project, repository, service
    finally:
        database.close()


def test_memory_crud_preserves_provenance(memory_components):
    _database, _project, repository, service = memory_components
    memory = service.create_memory(
        MemoryKind.CHARACTER,
        "Mara's fear",
        "Mara is afraid of open water.",
        confidence=0.95,
        source_type=ProvenanceType.FILE,
        source_ref="characters/mara.md",
        source_label="characters/mara.md",
        excerpt="She never steps onto the exposed deck.",
    )

    assert memory.provenance[0].source_type == ProvenanceType.FILE
    assert memory.provenance[0].source_ref == "characters/mara.md"

    archived = service.update_memory(
        memory.id,
        kind=memory.kind,
        title="Mara's ocean fear",
        content=memory.content,
        confidence=memory.confidence,
        status=MemoryStatus.ARCHIVED,
    )
    assert archived.status == MemoryStatus.ARCHIVED
    assert archived.provenance[-1].source_label == "Manual edit"
    assert service.list_memories(status=MemoryStatus.ACTIVE) == []

    service.delete_memory(memory.id)
    assert repository.get_memory(memory.id) is None


def test_duplicate_memory_is_rejected(memory_components):
    _database, _project, _repository, service = memory_components
    service.create_memory(
        MemoryKind.PLOT,
        "Midpoint",
        "The crew discovers the captain forged the map.",
    )

    with pytest.raises(MemoryDuplicateError):
        service.create_memory(
            MemoryKind.PLOT,
            "Different title",
            "The crew discovers the captain forged the map.",
        )


def test_approved_summary_saves_selected_memories_with_provenance(
    memory_components,
):
    _database, project, _repository, service = memory_components
    draft = ConversationSummaryDraft(
        project_id=project.id,
        session_id="session-1",
        title="Planning the midpoint",
        content="The crew will discover that the map is forged.",
        message_count=8,
        suggested_memories=(
            SuggestedMemory(
                MemoryKind.DECISION,
                "Forged map reveal",
                "At the midpoint, the crew learns the map is forged.",
                0.9,
            ),
            SuggestedMemory(
                MemoryKind.PREFERENCE,
                "Avoid flashbacks",
                "The author does not want flashbacks in this story.",
                0.8,
            ),
        ),
    )

    summary, memories = service.save_summary_draft(draft, (0,))

    assert summary.session_id == "session-1"
    assert len(memories) == 1
    assert {
        source.source_type for source in memories[0].provenance
    } == {ProvenanceType.SUMMARY, ProvenanceType.CHAT}
    assert len(service.list_summaries()) == 1


def test_invalid_selected_memory_does_not_partially_save_summary(
    memory_components,
):
    _database, project, _repository, service = memory_components
    draft = ConversationSummaryDraft(
        project_id=project.id,
        session_id="session-invalid",
        title="Invalid bundle",
        content="This should remain unsaved.",
        message_count=2,
        suggested_memories=(
            SuggestedMemory(
                MemoryKind.OTHER,
                "",
                "Missing title",
            ),
        ),
    )

    with pytest.raises(MemoryError, match="title and content"):
        service.save_summary_draft(draft, (0,))

    assert service.list_summaries() == []


def test_memory_context_is_bounded_relevant_and_tracks_usage(
    memory_components,
):
    _database, _project, repository, service = memory_components
    mara = service.create_memory(
        MemoryKind.CHARACTER,
        "Mara and the sea",
        "Mara is afraid of open water.",
    )
    service.create_memory(
        MemoryKind.WORLD,
        "City currency",
        "The city uses brass tokens as currency.",
    )
    archived = service.create_memory(
        MemoryKind.PLOT,
        "Discarded ending",
        "Mara abandons the ship.",
    )
    service.update_memory(
        archived.id,
        kind=archived.kind,
        title=archived.title,
        content=archived.content,
        confidence=archived.confidence,
        status=MemoryStatus.ARCHIVED,
    )

    context = service.build_context(
        "Why does Mara avoid the water?",
        max_tokens=100,
    )

    assert "afraid of open water" in context.text
    assert "abandons the ship" not in context.text
    assert context.total_tokens <= 100
    assert mara.id in context.memory_ids
    assert repository.get_memory(mara.id).last_used_at is not None


def test_memory_is_isolated_between_projects(memory_components, tmp_path):
    _database, first_project, _repository, service = memory_components
    service.create_memory(
        MemoryKind.WORLD,
        "Harbor law",
        "Ships must extinguish lanterns before midnight.",
    )
    second_root = tmp_path / "second-novel"
    second_root.mkdir()
    second_project = service.project_service.open_project(second_root)

    assert second_project.id != first_project.id
    assert service.list_memories() == []
    assert service.build_context("harbor law").text == ""

    service.project_service.open_registered_project(first_project.id)
    assert len(service.list_memories()) == 1
