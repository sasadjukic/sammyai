"""SQLite connection management and schema migrations for SammyAI."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
from threading import RLock


class MigrationError(RuntimeError):
    """Raised when the on-disk schema cannot be migrated safely."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]

    @property
    def checksum(self) -> str:
        content = "\n".join(statement.strip() for statement in self.statements)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


MIGRATIONS = (
    Migration(
        version=1,
        name="create_projects",
        statements=(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL CHECK (length(trim(name)) > 0),
                root_path TEXT NOT NULL,
                root_key TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_opened_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE project_settings (
                project_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (project_id, key),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE INDEX projects_last_opened_idx
            ON projects(last_opened_at DESC)
            """,
        ),
    ),
    Migration(
        version=2,
        name="create_application_state",
        statements=(
            """
            CREATE TABLE application_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        ),
    ),
    Migration(
        version=3,
        name="create_project_files",
        statements=(
            """
            CREATE TABLE project_files (
                project_id TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                relative_key TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                modified_ns INTEGER NOT NULL,
                indexed_at TEXT,
                sync_status TEXT NOT NULL,
                last_error TEXT,
                PRIMARY KEY (project_id, relative_path),
                UNIQUE (project_id, relative_key),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE INDEX project_files_status_idx
            ON project_files(project_id, sync_status)
            """,
        ),
    ),
    Migration(
        version=4,
        name="create_persistent_memory",
        statements=(
            """
            CREATE TABLE memories (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL CHECK (length(trim(title)) > 0),
                content TEXT NOT NULL CHECK (length(trim(content)) > 0),
                content_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0
                    CHECK (confidence >= 0.0 AND confidence <= 1.0),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_used_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id)
                    ON DELETE CASCADE,
                UNIQUE (project_id, kind, content_hash)
            )
            """,
            """
            CREATE TABLE memory_provenance (
                id TEXT PRIMARY KEY,
                memory_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_ref TEXT,
                source_label TEXT NOT NULL,
                excerpt TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (memory_id) REFERENCES memories(id)
                    ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE conversation_summaries (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                title TEXT NOT NULL CHECK (length(trim(title)) > 0),
                content TEXT NOT NULL CHECK (length(trim(content)) > 0),
                content_hash TEXT NOT NULL,
                message_count INTEGER NOT NULL CHECK (message_count >= 0),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id)
                    ON DELETE CASCADE,
                UNIQUE (project_id, session_id, message_count)
            )
            """,
            """
            CREATE INDEX memories_project_status_idx
            ON memories(project_id, status, kind, updated_at DESC)
            """,
            """
            CREATE INDEX memory_provenance_memory_idx
            ON memory_provenance(memory_id, created_at)
            """,
            """
            CREATE INDEX conversation_summaries_project_idx
            ON conversation_summaries(project_id, updated_at DESC)
            """,
        ),
    ),
)

LATEST_SCHEMA_VERSION = MIGRATIONS[-1].version


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectDatabase:
    """Owns SammyAI's SQLite connection and applies ordered migrations."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._connection: sqlite3.Connection | None = None
        self._lock = RLock()

    @property
    def connection(self) -> sqlite3.Connection:
        with self._lock:
            if self._connection is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                connection = sqlite3.connect(
                    self.path,
                    check_same_thread=False,
                )
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("PRAGMA busy_timeout = 5000")
                connection.execute("PRAGMA journal_mode = WAL")
                self._connection = connection
            return self._connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self.connection
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        """Serialize reads with writes on the shared cross-thread connection."""
        with self._lock:
            yield self.connection

    def migrate(self, target_version: int | None = None) -> int:
        target = LATEST_SCHEMA_VERSION if target_version is None else target_version
        if target < 0 or target > LATEST_SCHEMA_VERSION:
            raise MigrationError(f"Unsupported schema target version: {target}")

        connection = self.connection
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        connection.commit()

        applied_rows = connection.execute(
            "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
        applied = {row["version"]: row for row in applied_rows}
        current = max(applied, default=0)
        if current > target:
            raise MigrationError(
                f"Database is already at version {current}; "
                f"it cannot be downgraded to {target}"
            )

        known_versions = {migration.version for migration in MIGRATIONS}
        unknown_versions = set(applied) - known_versions
        if unknown_versions:
            raise MigrationError(
                f"Database contains unknown migration versions: "
                f"{sorted(unknown_versions)}"
            )

        for migration in MIGRATIONS:
            existing = applied.get(migration.version)
            if existing is not None:
                if (
                    existing["name"] != migration.name
                    or existing["checksum"] != migration.checksum
                ):
                    raise MigrationError(
                        f"Migration {migration.version} does not match "
                        "the recorded schema history"
                    )
                continue

            if migration.version > target:
                break

            with self.transaction() as transaction:
                for statement in migration.statements:
                    transaction.execute(statement)
                transaction.execute(
                    """
                    INSERT INTO schema_migrations(version, name, checksum, applied_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        migration.version,
                        migration.name,
                        migration.checksum,
                        _utc_now_text(),
                    ),
                )

        return self.current_version

    @property
    def current_version(self) -> int:
        row = self.connection.execute(
            "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
        ).fetchone()
        return int(row["version"])

    def close(self) -> None:
        with self._lock:
            if self._connection is None:
                return
            try:
                self._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                self._connection.close()
                self._connection = None

    def __enter__(self) -> "ProjectDatabase":
        self.migrate()
        return self

    def __exit__(self, exception_type, exception, traceback) -> None:
        self.close()
