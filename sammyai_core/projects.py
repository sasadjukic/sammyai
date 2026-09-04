"""Project domain model, persistence repository, and application service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

from .database import ProjectDatabase
from .paths import AppPaths


ACTIVE_PROJECT_KEY = "active_project_id"


class ProjectError(RuntimeError):
    """Base exception for project operations."""


class ProjectDirectoryError(ProjectError):
    """Raised when a project directory is missing or invalid."""


class ProjectAlreadyExistsError(ProjectError):
    """Raised when creating a project would overwrite an existing path."""


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    root_path: Path
    created_at: datetime
    updated_at: datetime
    last_opened_at: datetime


@dataclass(frozen=True)
class ProjectRemovalResult:
    project: Project
    cleanup_warnings: tuple[str, ...] = ()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _from_text(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def canonical_root(path: str | Path, *, strict: bool = True) -> Path:
    return Path(path).expanduser().resolve(strict=strict)


def root_key(path: str | Path) -> str:
    return os.path.normcase(str(canonical_root(path)))


class ProjectRepository:
    def __init__(self, database: ProjectDatabase):
        self.database = database

    @staticmethod
    def _project_from_row(row) -> Project:
        return Project(
            id=row["id"],
            name=row["name"],
            root_path=Path(row["root_path"]),
            created_at=_from_text(row["created_at"]),
            updated_at=_from_text(row["updated_at"]),
            last_opened_at=_from_text(row["last_opened_at"]),
        )

    def create(self, name: str, root_path: str | Path) -> Project:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("Project name cannot be empty")

        canonical_path = canonical_root(root_path)
        now = _utc_now()
        project = Project(
            id=str(uuid4()),
            name=cleaned_name,
            root_path=canonical_path,
            created_at=now,
            updated_at=now,
            last_opened_at=now,
        )
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO projects(
                    id, name, root_path, root_key,
                    created_at, updated_at, last_opened_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project.id,
                    project.name,
                    str(project.root_path),
                    root_key(project.root_path),
                    _to_text(project.created_at),
                    _to_text(project.updated_at),
                    _to_text(project.last_opened_at),
                ),
            )
        return project

    def get(self, project_id: str) -> Project | None:
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return self._project_from_row(row) if row is not None else None

    def get_by_root(self, path: str | Path) -> Project | None:
        key = root_key(path)
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE root_key = ?",
                (key,),
            ).fetchone()
        return self._project_from_row(row) if row is not None else None

    def list_recent(self, limit: int = 10) -> list[Project]:
        with self.database.read() as connection:
            rows = connection.execute(
                """
                SELECT * FROM projects
                ORDER BY last_opened_at DESC, name COLLATE NOCASE
                LIMIT ?
                """,
                (max(0, limit),),
            ).fetchall()
        return [self._project_from_row(row) for row in rows]

    def touch_opened(self, project_id: str) -> Project | None:
        now = _utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE projects
                SET last_opened_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (_to_text(now), _to_text(now), project_id),
            )
        return self.get(project_id)

    def update_root(self, project_id: str, root_path: str | Path) -> Project | None:
        canonical_path = canonical_root(root_path)
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE projects
                SET root_path = ?, root_key = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    str(canonical_path),
                    root_key(canonical_path),
                    _to_text(_utc_now()),
                    project_id,
                ),
            )
        return self.get(project_id)

    def delete(self, project_id: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "DELETE FROM projects WHERE id = ?",
                (project_id,),
            )

    def set_setting(self, project_id: str, key: str, value: Any) -> None:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO project_settings(project_id, key, value_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id, key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (project_id, key, serialized, _to_text(_utc_now())),
            )

    def get_setting(
        self,
        project_id: str,
        key: str,
        default: Any = None,
    ) -> Any:
        with self.database.read() as connection:
            row = connection.execute(
                """
                SELECT value_json FROM project_settings
                WHERE project_id = ? AND key = ?
                """,
                (project_id, key),
            ).fetchone()
        return default if row is None else json.loads(row["value_json"])

    def set_application_state(self, key: str, value: str | None) -> None:
        with self.database.transaction() as connection:
            if value is None:
                connection.execute(
                    "DELETE FROM application_state WHERE key = ?",
                    (key,),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO application_state(key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (key, value, _to_text(_utc_now())),
                )

    def get_application_state(self, key: str) -> str | None:
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT value FROM application_state WHERE key = ?",
                (key,),
            ).fetchone()
        return None if row is None else str(row["value"])


class ProjectService:
    """Coordinates filesystem validation, persistence, and active project state."""

    def __init__(self, repository: ProjectRepository, paths: AppPaths):
        self.repository = repository
        self.paths = paths
        self.active_project: Project | None = None

    def create_project(self, path: str | Path, name: str | None = None) -> Project:
        requested_path = Path(path).expanduser()
        project_name = (name or requested_path.name).strip()
        if not project_name:
            raise ProjectDirectoryError("Project name cannot be empty")
        if requested_path.exists():
            raise ProjectAlreadyExistsError(
                f"A file or directory already exists at {requested_path}"
            )
        try:
            requested_path.mkdir(parents=True, exist_ok=False)
        except OSError as error:
            raise ProjectDirectoryError(
                f"Unable to create project directory: {error}"
            ) from error

        try:
            return self._register_and_activate(
                requested_path,
                project_name,
            )
        except Exception:
            try:
                requested_path.rmdir()
            except OSError:
                pass
            raise

    def open_project(self, path: str | Path) -> Project:
        try:
            project_root = canonical_root(path)
        except OSError as error:
            raise ProjectDirectoryError(f"Project directory does not exist: {path}") from error
        if not project_root.is_dir():
            raise ProjectDirectoryError(f"Project path is not a directory: {project_root}")

        existing = self.repository.get_by_root(project_root)
        if existing is not None:
            return self._activate(existing)
        project_name = project_root.name or project_root.anchor
        return self._register_and_activate(project_root, project_name)

    def open_registered_project(self, project_id: str) -> Project:
        project = self.repository.get(project_id)
        if project is None:
            raise ProjectDirectoryError(f"Unknown project: {project_id}")
        if not project.root_path.is_dir():
            raise ProjectDirectoryError(
                f"Project directory no longer exists: {project.root_path}"
            )
        return self._activate(project)

    def restore_active_project(self) -> Project | None:
        project_id = self.repository.get_application_state(ACTIVE_PROJECT_KEY)
        if not project_id:
            return None
        try:
            return self.open_registered_project(project_id)
        except ProjectDirectoryError:
            self.repository.set_application_state(ACTIVE_PROJECT_KEY, None)
            return None

    def close_project(self) -> None:
        self.repository.set_application_state(ACTIVE_PROJECT_KEY, None)
        self.active_project = None

    def recent_projects(self, limit: int = 10) -> list[Project]:
        return self.repository.list_recent(limit)

    def get_project(self, project_id: str) -> Project | None:
        return self.repository.get(project_id)

    def set_project_setting(self, project_id: str, key: str, value: Any) -> None:
        self.repository.set_setting(project_id, key, value)

    def get_project_setting(
        self,
        project_id: str,
        key: str,
        default: Any = None,
    ) -> Any:
        return self.repository.get_setting(project_id, key, default)

    def relocate_project(
        self,
        project_id: str,
        root_path: str | Path,
    ) -> Project:
        project = self.repository.get(project_id)
        if project is None:
            raise ProjectDirectoryError(f"Unknown project: {project_id}")
        try:
            new_root = canonical_root(root_path)
        except OSError as error:
            raise ProjectDirectoryError(
                f"Project directory does not exist: {root_path}"
            ) from error
        if not new_root.is_dir():
            raise ProjectDirectoryError(
                f"Project path is not a directory: {new_root}"
            )
        registered = self.repository.get_by_root(new_root)
        if registered is not None and registered.id != project_id:
            raise ProjectAlreadyExistsError(
                f"That folder is already registered as '{registered.name}'"
            )
        relocated = self.repository.update_root(project_id, new_root)
        if relocated is None:
            raise ProjectDirectoryError(f"Unknown project: {project_id}")
        return self._activate(relocated)

    def remove_project(self, project_id: str) -> ProjectRemovalResult:
        """Forget a project and remove only SammyAI-owned project state."""
        project = self.repository.get(project_id)
        if project is None:
            raise ProjectDirectoryError(f"Unknown project: {project_id}")

        if self.repository.get_application_state(ACTIVE_PROJECT_KEY) == project_id:
            self.repository.set_application_state(ACTIVE_PROJECT_KEY, None)
        if self.active_project is not None and self.active_project.id == project_id:
            self.active_project = None
        self.repository.delete(project_id)

        warnings: list[str] = []
        managed_directories = (
            self.paths.project_data_dir(project_id),
            self.paths.project_cache_dir(project_id),
        )
        for directory in managed_directories:
            try:
                self._remove_managed_project_directory(directory)
            except OSError as error:
                warnings.append(f"Unable to remove {directory}: {error}")
        return ProjectRemovalResult(project, tuple(warnings))

    def _remove_managed_project_directory(self, directory: Path) -> None:
        allowed_roots = (
            self.paths.projects_data_dir.resolve(),
            self.paths.projects_cache_dir.resolve(),
        )
        target = directory.resolve(strict=False)
        if target in allowed_roots or not any(
            target.parent == root for root in allowed_roots
        ):
            raise OSError(f"Refusing to remove unsafe managed path: {target}")
        if target.exists():
            shutil.rmtree(target)

    def _register_and_activate(self, root: Path, name: str) -> Project:
        project = self.repository.create(name, root)
        try:
            return self._activate(project)
        except Exception:
            if self.repository.get_application_state(ACTIVE_PROJECT_KEY) == project.id:
                self.repository.set_application_state(ACTIVE_PROJECT_KEY, None)
            self.repository.delete(project.id)
            raise

    def _activate(self, project: Project) -> Project:
        refreshed = self.repository.touch_opened(project.id) or project
        self.paths.project_data_dir(refreshed.id).mkdir(parents=True, exist_ok=True)
        self.paths.project_cache_dir(refreshed.id).mkdir(parents=True, exist_ok=True)
        self.repository.set_application_state(ACTIVE_PROJECT_KEY, refreshed.id)
        self.active_project = refreshed
        return refreshed
