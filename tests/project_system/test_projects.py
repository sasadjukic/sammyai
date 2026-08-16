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


def test_relocate_missing_project_preserves_identity_and_managed_state(
    project_components,
    tmp_path,
):
    paths, _, repository, service = project_components
    original_root = tmp_path / "original"
    relocated_root = tmp_path / "relocated"
    original_root.mkdir()
    project = service.open_project(original_root)
    repository.set_setting(project.id, "story", {"format": "novel"})
    original_root.rmdir()
    relocated_root.mkdir()

    relocated = service.relocate_project(project.id, relocated_root)

    assert relocated.id == project.id
    assert relocated.name == project.name
    assert relocated.root_path == relocated_root.resolve()
    assert service.active_project == relocated
    assert repository.get_setting(project.id, "story") == {"format": "novel"}
    assert paths.project_data_dir(project.id).is_dir()
    assert paths.project_cache_dir(project.id).is_dir()


def test_remove_project_purges_registration_and_managed_state_not_source_files(
    project_components,
    tmp_path,
):
    paths, _, repository, service = project_components
    root = tmp_path / "finished-project"
    root.mkdir()
    manuscript = root / "manuscript.md"
    manuscript.write_text("Keep me", encoding="utf-8")
    project = service.open_project(root)
    repository.set_setting(project.id, "story", {"status": "finished"})
    (paths.project_data_dir(project.id) / "state.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (paths.project_cache_dir(project.id) / "cache.bin").write_bytes(b"cache")

    result = service.remove_project(project.id)

    assert result.project.id == project.id
    assert result.cleanup_warnings == ()
    assert repository.get(project.id) is None
    assert repository.get_application_state(ACTIVE_PROJECT_KEY) is None
    assert service.active_project is None
    assert not paths.project_data_dir(project.id).exists()
    assert not paths.project_cache_dir(project.id).exists()
    assert manuscript.read_text(encoding="utf-8") == "Keep me"
