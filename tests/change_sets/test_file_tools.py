import os

import pytest

from editing.change_sets import FileChangeRequest, TextEdit
from sammyai_core.database import ProjectDatabase
from sammyai_core.file_tools import (
    ChangeApplyError,
    ChangeConflictError,
    SafeFileTools,
    UnsafePathError,
)
from sammyai_core.paths import AppPaths
from sammyai_core.projects import ProjectRepository, ProjectService


@pytest.fixture
def file_tools(tmp_path):
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
    tools = SafeFileTools(project_service)
    try:
        yield project, tools
    finally:
        database.close()


def test_prepare_preview_apply_undo_and_redo(file_tools):
    project, tools = file_tools
    chapter = project.root_path / "chapter.md"
    original = "Mara enters.\nThe door is blue.\n"
    chapter.write_bytes(original.encode("utf-8"))
    start = original.index("blue")

    change_set = tools.prepare_change_set(
        [
            FileChangeRequest.edit(
                "chapter.md",
                [TextEdit(start, start + 4, "red", expected_text="blue")],
            ),
            FileChangeRequest.write("notes/new-ending.txt", "The bell rings.\n"),
        ],
        description="Revise the entrance",
    )
    preview = tools.preview(change_set)

    assert preview.additions >= 2
    assert preview.deletions >= 1
    assert {file.relative_path for file in preview.files} == {
        "chapter.md",
        "notes/new-ending.txt",
    }

    tools.apply(change_set)
    assert chapter.read_text(encoding="utf-8").endswith("door is red.\n")
    assert (project.root_path / "notes" / "new-ending.txt").is_file()
    assert tools.can_undo

    tools.undo_last()
    assert chapter.read_text(encoding="utf-8") == original
    assert not (project.root_path / "notes" / "new-ending.txt").exists()
    assert tools.can_redo

    tools.redo_last()
    assert chapter.read_text(encoding="utf-8").endswith("door is red.\n")
    assert (project.root_path / "notes" / "new-ending.txt").is_file()


def test_apply_rejects_content_changed_after_review(file_tools):
    project, tools = file_tools
    chapter = project.root_path / "chapter.md"
    chapter.write_text("Draft one\n", encoding="utf-8")
    change_set = tools.prepare_change_set(
        [FileChangeRequest.write("chapter.md", "Draft two\n")],
        description="Revise draft",
    )
    chapter.write_text("Writer changed this\n", encoding="utf-8")

    with pytest.raises(ChangeConflictError, match="content changed"):
        tools.apply(change_set)

    assert chapter.read_text(encoding="utf-8") == "Writer changed this\n"


def test_delete_is_reviewable_and_undo_restores_file(file_tools):
    project, tools = file_tools
    notes = project.root_path / "obsolete.txt"
    notes.write_bytes(b"Old notes\n")
    change_set = tools.prepare_change_set(
        [FileChangeRequest.delete("obsolete.txt")],
        description="Remove obsolete notes",
    )

    preview = tools.preview(change_set)
    assert preview.deletions == 1

    tools.apply(change_set)
    assert not notes.exists()

    tools.undo_last()
    assert notes.read_bytes() == b"Old notes\n"


def test_undo_rejects_external_changes(file_tools):
    project, tools = file_tools
    chapter = project.root_path / "chapter.md"
    chapter.write_text("Before\n", encoding="utf-8")
    change_set = tools.prepare_change_set(
        [FileChangeRequest.write("chapter.md", "After\n")],
        description="Update chapter",
    )
    tools.apply(change_set)
    chapter.write_text("External revision\n", encoding="utf-8")

    with pytest.raises(ChangeConflictError, match="content changed"):
        tools.undo_last()

    assert chapter.read_text(encoding="utf-8") == "External revision\n"
    assert tools.can_undo


def test_multi_file_failure_rolls_back_prior_replacements(
    file_tools,
    monkeypatch,
):
    project, tools = file_tools
    first = project.root_path / "first.md"
    second = project.root_path / "second.md"
    first.write_text("First original\n", encoding="utf-8")
    second.write_text("Second original\n", encoding="utf-8")
    change_set = tools.prepare_change_set(
        [
            FileChangeRequest.write("first.md", "First changed\n"),
            FileChangeRequest.write("second.md", "Second changed\n"),
        ],
        description="Update both chapters",
    )
    replacements = 0

    def fail_second_replace(source, target):
        nonlocal replacements
        replacements += 1
        if replacements == 2:
            raise OSError("simulated replace failure")
        os.replace(source, target)

    monkeypatch.setattr(tools, "_replace", fail_second_replace)

    with pytest.raises(ChangeApplyError, match="simulated replace failure"):
        tools.apply(change_set)

    assert first.read_text(encoding="utf-8") == "First original\n"
    assert second.read_text(encoding="utf-8") == "Second original\n"
    assert not list(project.root_path.glob(".*.sammyai-*"))


@pytest.mark.parametrize(
    "relative_path",
    (
        "../outside.md",
        ".git/config.txt",
        "image.png",
        "C:/absolute.md",
    ),
)
def test_file_tools_reject_unsafe_or_unsupported_paths(
    file_tools,
    relative_path,
):
    _project, tools = file_tools

    with pytest.raises(UnsafePathError):
        tools.prepare_change_set(
            [FileChangeRequest.write(relative_path, "blocked")],
            description="Unsafe write",
        )
