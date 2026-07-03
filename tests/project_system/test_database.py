import sqlite3

import pytest

from sammyai_core.database import (
    LATEST_SCHEMA_VERSION,
    MigrationError,
    ProjectDatabase,
)


def test_blank_database_migrates_to_latest_schema(tmp_path):
    database = ProjectDatabase(tmp_path / "sammyai.sqlite3")
    try:
        assert database.migrate() == LATEST_SCHEMA_VERSION

        tables = {
            row["name"]
            for row in database.connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table'
                """
            )
        }
        assert {
            "schema_migrations",
            "projects",
            "project_settings",
            "application_state",
            "project_files",
        }.issubset(tables)

        versions = [
            row["version"]
            for row in database.connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
        assert versions == list(range(1, LATEST_SCHEMA_VERSION + 1))
    finally:
        database.close()


def test_incremental_migration_preserves_existing_project_rows(tmp_path):
    path = tmp_path / "sammyai.sqlite3"
    database = ProjectDatabase(path)
    assert database.migrate(target_version=1) == 1
    database.connection.execute(
        """
        INSERT INTO projects(
            id, name, root_path, root_key,
            created_at, updated_at, last_opened_at
        )
        VALUES ('project-1', 'Novel', '/novel', '/novel', 'now', 'now', 'now')
        """
    )
    database.connection.commit()
    database.close()

    upgraded = ProjectDatabase(path)
    try:
        assert upgraded.migrate() == LATEST_SCHEMA_VERSION
        row = upgraded.connection.execute(
            "SELECT name FROM projects WHERE id = 'project-1'"
        ).fetchone()
        assert row["name"] == "Novel"
    finally:
        upgraded.close()


def test_changed_migration_history_is_rejected(tmp_path):
    database = ProjectDatabase(tmp_path / "sammyai.sqlite3")
    try:
        database.migrate()
        database.connection.execute(
            """
            UPDATE schema_migrations
            SET checksum = 'tampered'
            WHERE version = 1
            """
        )
        database.connection.commit()

        with pytest.raises(MigrationError):
            database.migrate()
    finally:
        database.close()


def test_migration_runner_refuses_downgrades(tmp_path):
    database = ProjectDatabase(tmp_path / "sammyai.sqlite3")
    try:
        database.migrate()
        with pytest.raises(MigrationError):
            database.migrate(target_version=1)
    finally:
        database.close()


def test_transaction_rolls_back_on_error(tmp_path):
    database = ProjectDatabase(tmp_path / "sammyai.sqlite3")
    try:
        database.migrate()
        with pytest.raises(sqlite3.IntegrityError):
            with database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO projects(
                        id, name, root_path, root_key,
                        created_at, updated_at, last_opened_at
                    )
                    VALUES ('bad', '', '/bad', '/bad', 'now', 'now', 'now')
                    """
                )

        count = database.connection.execute(
            "SELECT COUNT(*) AS count FROM projects"
        ).fetchone()["count"]
        assert count == 0
    finally:
        database.close()
