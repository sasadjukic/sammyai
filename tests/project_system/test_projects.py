from pathlib import Path

import pytest

from sammyai_core.database import ProjectDatabase
from sammyai_core.paths import AppPaths
from sammyai_core.projects import (
    ACTIVE_PROJECT_KEY,
    ProjectAlreadyExistsError,
    ProjectDirectoryError,
    ProjectRepository,
    ProjectService,
)


@pytest.fixture
def project_components(tmp_path):
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
    try:
        yield paths, database, repository, service
    finally:
        database.close()


def test_open_project_registers_once_and_persists_settings(
    project_components,
    tmp_path,
):
    _, _, repository, service = project_components
    root = tmp_path / "existing-novel"
    root.mkdir()

    first = service.open_project(root)
    second = service.open_project(root)
    repository.set_setting(
        first.id,
        "story",
        {"medium": "novel", "language": "en-US"},
    )

    assert second.id == first.id
    assert len(repository.list_recent()) == 1
    assert repository.get_setting(first.id, "story") == {
        "medium": "novel",
        "language": "en-US",
    }


def test_create_project_creates_managed_state_directories(
    project_components,
    tmp_path,
):
    paths, _, repository, service = project_components
    root = tmp_path / "new-novel"

    project = service.create_project(root, name="New Novel")

    assert root.is_dir()
    assert project.name == "New Novel"
    assert paths.project_data_dir(project.id).is_dir()
    assert paths.project_cache_dir(project.id).is_dir()
    assert repository.get_application_state(ACTIVE_PROJECT_KEY) == project.id


def test_create_project_refuses_existing_path(project_components, tmp_path):
    _, _, _, service = project_components
    root = tmp_path / "already-exists"
    root.mkdir()

    with pytest.raises(ProjectAlreadyExistsError):
        service.create_project(root)


def test_create_project_refuses_empty_name_without_creating_folder(
    project_components,
    tmp_path,
):
    _, _, _, service = project_components
    root = tmp_path / "empty-name"

    with pytest.raises(ProjectDirectoryError):
        service.create_project(root, name="   ")

    assert not root.exists()


def test_active_project_restores_until_explicitly_closed(
    project_components,
    tmp_path,
):
    paths, _, repository, service = project_components
    root = tmp_path / "restored-novel"
    root.mkdir()
    opened = service.open_project(root)

    restored_service = ProjectService(repository, paths)
    restored = restored_service.restore_active_project()
    assert restored.id == opened.id

    restored_service.close_project()
    next_service = ProjectService(repository, paths)
    assert next_service.restore_active_project() is None


def test_missing_active_project_is_cleared(project_components, tmp_path):
    paths, _, repository, service = project_components
    root = tmp_path / "missing-novel"
    root.mkdir()
    project = service.open_project(root)
    root.rmdir()

    restored_service = ProjectService(repository, paths)

    assert restored_service.restore_active_project() is None
    assert repository.get_application_state(ACTIVE_PROJECT_KEY) is None
    with pytest.raises(ProjectDirectoryError):
        restored_service.open_registered_project(project.id)


def test_recent_projects_are_ordered_by_last_opened(
    project_components,
    tmp_path,
):
    _, _, _, service = project_components
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()

    first = service.open_project(first_root)
    second = service.open_project(second_root)
    service.open_registered_project(first.id)

    recent = service.recent_projects()
    assert [project.id for project in recent[:2]] == [first.id, second.id]
