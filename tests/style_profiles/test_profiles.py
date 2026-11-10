from dataclasses import FrozenInstanceError
import json
import sqlite3

import pytest

from sammyai_core.database import ProjectDatabase
from sammyai_core.diagnostics import RequestTraceService
from sammyai_core.projects import ProjectRepository
from sammyai_core.style_profiles import (
    STYLE_SETTING, StyleProfileError, StyleProfileRepository, StyleProfileService, StyleSelection,
)


@pytest.fixture
def profiles(tmp_path):
    db = ProjectDatabase(tmp_path / "profiles.sqlite3")
    db.migrate()
    projects = ProjectRepository(db)
    (tmp_path / "first").mkdir()
    (tmp_path / "second").mkdir()
    first = projects.create("First", tmp_path / "first")
    second = projects.create("Second", tmp_path / "second")
    service = StyleProfileService(StyleProfileRepository(db))
    yield service, projects, first.id, second.id
    db.close()


def test_schema_5_upgrade_preserves_every_existing_table(tmp_path):
    path = tmp_path / "upgrade.sqlite3"
    db = ProjectDatabase(path)
    db.migrate(target_version=5)
    (tmp_path / "novel").mkdir()
    project = ProjectRepository(db).create("Novel", tmp_path / "novel")
    ProjectRepository(db).set_setting(project.id, "custom", {"keep": True})
    with db.transaction() as connection:
        connection.execute("INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            "memory", project.id, "style", "Old style", "Keep this preference", "hash", "approved", 1.0, "now", "now", None))
    RequestTraceService(db).begin("old-chat", project.id, agent="writer")
    # Compare all existing tables and rows, including migration checksums.
    tables = [row[0] for row in db.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    before = {table: [tuple(row) for row in db.connection.execute(f'SELECT * FROM "{table}"')] for table in tables}
    db.close()
    upgraded = ProjectDatabase(path)
    try:
        assert upgraded.migrate() == upgraded.migrate() == 6
        for table, rows in before.items():
            after = [tuple(row) for row in upgraded.connection.execute(f'SELECT * FROM "{table}"')]
            assert (after[:5] if table == "schema_migrations" else after) == rows
    finally:
        upgraded.close()


def test_scope_resolution_explicit_none_and_restart(profiles):
    service, projects, first, second = profiles
    global_style = service.repository.create("Global", "Use concrete details.")
    local = service.repository.create("Local", "Use spare prose.", project_id=first)
    service.select(None, StyleSelection("profile", global_style.id))
    assert service.resolve(first).snapshot.id == global_style.id
    service.select(first, StyleSelection())
    assert service.resolve(first).snapshot is None
    service.select(first, StyleSelection("profile", local.id))
    assert service.resolve(first).snapshot.id == local.id
    assert service.resolve(second).snapshot.id == global_style.id
    for scope in (None, second):
        with pytest.raises(StyleProfileError):
            service.select(scope, StyleSelection("profile", local.id))
    with pytest.raises(StyleProfileError):
        service.select(None, StyleSelection("inherit"))
    reloaded = StyleProfileService(StyleProfileRepository(service.repository.database))
    assert reloaded.resolve(first).snapshot.id == local.id
    assert {p.id for p in service.repository.list(second)} == {global_style.id}
    service.select(first, StyleSelection("inherit"))
    assert service.resolve(first).snapshot.id == global_style.id


@pytest.mark.parametrize("mutation", ["archive", "delete"])
def test_lifecycle_clears_explicit_selections_atomically_but_keeps_snapshots(profiles, mutation):
    service, projects, first, second = profiles
    profile = service.repository.create("Original", "Keep rhythm.", "An approved example. 😀")
    for scope in (None, first, second):
        service.select(scope, StyleSelection("profile", profile.id))
    snapshot = service.resolve(first).snapshot
    getattr(service.repository, mutation)(profile.id, expected_revision=profile.revision)
    for scope in (None, first, second):
        result = service.resolve(scope)
        assert result.snapshot is None and result.selection == StyleSelection()
    assert snapshot.instructions == "Keep rhythm."
    with pytest.raises(FrozenInstanceError):
        snapshot.instructions = "Changed"
    if mutation == "archive":
        archived = service.repository.get(profile.id)
        assert not service.repository.list()
        assert service.repository.list(include_archived=True)[0].id == profile.id
        service.repository.archive(profile.id, expected_revision=archived.revision, archived=False)
        assert service.resolve().snapshot is None  # Restore does not reactivate.


def test_optimistic_updates_duplicate_and_content_hash(profiles):
    service, projects, first, second = profiles
    original = service.repository.create("Voice", "  Line one.\nLine two.  ", "😀 A sample.")
    saved = service.repository.update(original.id, expected_revision=1, name="Renamed", instructions=original.instructions, examples=original.examples)
    assert saved.revision == 2
    assert original.snapshot().content_hash == saved.snapshot().content_hash
    assert saved.instructions == original.instructions
    with pytest.raises(StyleProfileError):
        service.repository.update(original.id, expected_revision=1, name="Stale", instructions="lost update")
    copied = service.duplicate(original.id, project_id=first)
    assert copied.id != original.id and copied.project_id == first and copied.revision == 1
    assert copied.snapshot().content_hash == original.snapshot().content_hash
    projects.delete(first)
    assert service.repository.get(copied.id) is None
    assert service.repository.get(original.id) is not None


@pytest.mark.parametrize("payload", ["bad json", '{}', '{"mode":"profile","profile_id":"missing"}', '{"mode":"none","profile_id":"unexpected"}'])
def test_invalid_persisted_selection_is_off_without_fallback(profiles, payload):
    service, projects, first, second = profiles
    profile = service.repository.create("Default", "Default style")
    service.select(None, StyleSelection("profile", profile.id))
    with service.repository.database.transaction() as db:
        db.execute("INSERT INTO project_settings VALUES (?,?,?,?)", (first, STYLE_SETTING, payload, "now"))
    result = service.resolve(first)
    assert result.snapshot is None and result.notice and result.selection.mode == "none"
    assert service.resolve(first).notice == ""


def test_corrupt_global_selection_cannot_use_a_project_profile(profiles):
    service, projects, first, second = profiles
    local = service.repository.create("Private", "Private instructions", project_id=first)
    projects.set_application_state(STYLE_SETTING, StyleSelection("profile", local.id).to_json())
    result = service.resolve(first)
    assert result.snapshot is None and result.notice
    assert service.resolve(second).snapshot is None


@pytest.mark.parametrize("field,value", [("name", " "), ("name", "x" * 121), ("instructions", ""),
    ("instructions", "x" * 6001), ("examples", "x" * 3001), ("examples", "bad\x00text")],
    ids=["blank-name", "long-name", "blank-instructions", "long-instructions", "long-examples", "null-character"])
def test_validation_never_truncates_or_creates_partial_profiles(profiles, field, value):
    service, *_ = profiles
    values = {"name": "Style", "instructions": "Valid instructions", "examples": ""}
    values[field] = value
    with pytest.raises(StyleProfileError):
        service.repository.create(**values)
    assert service.repository.list() == []


def test_failed_selection_cleanup_rolls_back_archive(profiles):
    service, projects, first, second = profiles
    profile = service.repository.create("Style", "Instructions")
    service.select(first, StyleSelection("profile", profile.id))
    with service.repository.database.transaction() as db:
        db.execute("CREATE TRIGGER reject_setting BEFORE UPDATE ON project_settings BEGIN SELECT RAISE(ABORT, 'test failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        service.repository.archive(profile.id, expected_revision=1)
    assert service.repository.get(profile.id).revision == 1
    assert service.resolve(first).snapshot.id == profile.id
