from pathlib import Path
from types import SimpleNamespace

from sammyai_core.context_engine import (
    ProjectContextEngine,
    ProjectFileRepository,
)
from sammyai_core.database import ProjectDatabase
from sammyai_core.paths import AppPaths
from sammyai_core.projects import ProjectRepository, ProjectService


class FakeRAG:
    def __init__(self):
        self.indexed = []
        self.removed = []
        self.context_calls = []
        self.context_text = "Mara keeps the brass key in the observatory."

    def index_file(self, path, force_reindex=False, **metadata):
        self.indexed.append((str(Path(path).resolve()), force_reindex, metadata))
        return True

    def remove_file(self, path):
        self.removed.append(str(Path(path).resolve()))

    def get_context(self, query, **kwargs):
        self.context_calls.append((query, kwargs))
        return SimpleNamespace(
            chunks=[object()] if self.context_text else [],
            format_for_llm=lambda: self.context_text,
        )


class FakeMemory:
    def build_context(self, query, max_tokens):
        assert query == "What does Mara fear?"
        assert max_tokens <= 800
        return SimpleNamespace(
            text="[Character] Mara: Mara fears open water.",
            memory_ids=("memory-1",),
            summary_ids=("summary-1",),
        )


def make_engine(tmp_path, *, max_context_tokens=4_000):
    paths = AppPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        log_dir=tmp_path / "logs",
    ).ensure_created()
    database = ProjectDatabase(paths.project_database_path)
    database.migrate()
    project_repository = ProjectRepository(database)
    project_service = ProjectService(project_repository, paths)
    root = tmp_path / "novel"
    root.mkdir()
    project = project_service.open_project(root)
    rag = FakeRAG()
    file_repository = ProjectFileRepository(database)
    engine = ProjectContextEngine(
        project_service,
        file_repository,
        rag,
        max_context_tokens=max_context_tokens,
    )
    return database, project, file_repository, rag, engine


def test_project_sync_uses_hashes_and_removes_deleted_files(tmp_path):
    database, project, repository, rag, engine = make_engine(tmp_path)
    chapter = project.root_path / "chapter.md"
    notes = project.root_path / "notes.txt"
    ignored = project.root_path / "cover.png"
    chapter.write_text("First draft", encoding="utf-8")
    notes.write_text("Blue door", encoding="utf-8")
    ignored.write_bytes(b"not context")

    try:
        first = engine.sync_active_project()
        second = engine.sync_active_project()
        chapter.write_text("Second draft", encoding="utf-8")
        notes.unlink()
        third = engine.sync_active_project()

        assert (first.added, first.updated, first.removed) == (2, 0, 0)
        assert second.unchanged == 2
        assert (third.added, third.updated, third.removed) == (0, 1, 1)
        assert len(rag.indexed) == 3
        assert rag.indexed[0][2]["project_id"] == project.id
        assert rag.indexed[0][2]["content_hash"]
        assert rag.removed == [str(notes.resolve())]

        records = repository.list_for_project(project.id)
        assert [record.relative_path for record in records] == ["chapter.md"]
        assert records[0].sync_status == "indexed"
        assert records[0].content_hash == rag.indexed[-1][2]["content_hash"]
    finally:
        database.close()


def test_project_index_can_be_forced_and_invalidated(tmp_path):
    database, project, repository, rag, engine = make_engine(tmp_path)
    chapter = project.root_path / "chapter.md"
    chapter.write_text("Stable draft", encoding="utf-8")

    try:
        engine.sync_active_project()
        forced = engine.sync_project(project, force_reindex=True)
        engine.invalidate_index_state()
        pending = repository.list_for_project(project.id)
        restored = engine.sync_active_project()

        assert forced.updated == 1
        assert pending[0].sync_status == "pending"
        assert restored.updated == 1
        assert len(rag.indexed) == 3
    finally:
        database.close()


def test_file_references_are_resolved_and_rag_is_project_scoped(tmp_path):
    database, project, _repository, rag, engine = make_engine(tmp_path)
    chapter = project.root_path / "chapters" / "chapter one.md"
    chapter.parent.mkdir()
    chapter.write_text("The lighthouse lens is cracked.", encoding="utf-8")

    try:
        result = engine.build_context(
            'Compare @"chapters/chapter one.md" with the outline.',
            cin_context="The ending should remain unresolved.",
        )

        assert result.referenced_files == ("chapters/chapter one.md",)
        assert result.complete_referenced_files == (
            "chapters/chapter one.md",
        )
        assert "lighthouse lens" in result.system_messages[0]
        assert "ending should remain unresolved" in result.system_messages[1]
        assert rag.context_calls[-1][1]["project_id"] == project.id
        assert result.total_tokens <= result.max_tokens
    finally:
        database.close()


def test_ambiguous_basename_requires_a_relative_path(tmp_path):
    database, project, _repository, _rag, engine = make_engine(tmp_path)
    for directory in ("draft", "notes"):
        path = project.root_path / directory / "scene.md"
        path.parent.mkdir()
        path.write_text(directory, encoding="utf-8")

    try:
        references = engine.resolve_file_references("Review @scene.md")

        assert len(references) == 1
        assert references[0].path is None
        assert "ambiguous" in references[0].error
        assert "draft/scene.md" in references[0].error
        assert "notes/scene.md" in references[0].error
    finally:
        database.close()


def test_explicit_file_content_is_truncated_to_context_budget(tmp_path):
    database, project, _repository, rag, engine = make_engine(
        tmp_path,
        max_context_tokens=60,
    )
    rag.context_text = ""
    chapter = project.root_path / "chapter.md"
    chapter.write_text("ocean " * 1_000, encoding="utf-8")

    try:
        result = engine.build_context("Review @chapter.md")

        assert result.truncated is True
        assert result.total_tokens <= 60
        assert "Context truncated" in result.system_messages[0]
        assert result.complete_referenced_files == ()
    finally:
        database.close()


def test_persistent_memory_is_injected_before_semantic_rag(tmp_path):
    database, _project, repository, rag, engine = make_engine(tmp_path)
    engine.memory_service = FakeMemory()

    try:
        result = engine.build_context("What does Mara fear?")

        assert "persistent project memory" in result.system_messages[0]
        assert "Mara fears open water" in result.system_messages[0]
        assert "retrieved from project files" in result.system_messages[1]
        assert result.memory_ids == ("memory-1",)
        assert result.summary_ids == ("summary-1",)
    finally:
        database.close()
