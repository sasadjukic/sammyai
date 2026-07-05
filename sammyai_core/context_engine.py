"""Project-scoped file synchronization and prompt-context assembly."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import logging
import os
from pathlib import Path
import re
from threading import RLock
from typing import Any

from .database import ProjectDatabase
from .documents import DocumentService
from .projects import Project, ProjectService


logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = frozenset({".md", ".txt", ".pdf"})
IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".sammyai",
        ".venv",
        "__pycache__",
        "node_modules",
        "venv",
    }
)
FILE_REFERENCE_PATTERN = re.compile(
    r"(?<![\w@])@(?:\"([^\"]+)\"|'([^']+)'|([^\s,;]+))"
)


def estimate_tokens(text: str) -> int:
    """Return a deterministic, provider-neutral token estimate."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _relative_key(relative_path: str) -> str:
    return os.path.normcase(relative_path.replace("\\", "/"))


def _content_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class ProjectFileRecord:
    project_id: str
    relative_path: str
    content_hash: str
    size_bytes: int
    modified_ns: int
    indexed_at: str | None
    sync_status: str
    last_error: str | None = None


@dataclass(frozen=True)
class SyncReport:
    project_id: str | None
    added: int = 0
    updated: int = 0
    removed: int = 0
    unchanged: int = 0
    failed: int = 0

    @property
    def changed(self) -> int:
        return self.added + self.updated + self.removed


@dataclass(frozen=True)
class FileReference:
    reference: str
    path: Path | None
    relative_path: str | None
    error: str | None = None


@dataclass(frozen=True)
class ContextResult:
    system_messages: tuple[str, ...]
    total_tokens: int
    max_tokens: int
    truncated: bool
    notices: tuple[str, ...]
    sync_report: SyncReport
    referenced_files: tuple[str, ...]


class ProjectFileRepository:
    """Persists the last successfully synchronized state of project files."""

    def __init__(self, database: ProjectDatabase):
        self.database = database

    @staticmethod
    def _from_row(row) -> ProjectFileRecord:
        return ProjectFileRecord(
            project_id=row["project_id"],
            relative_path=row["relative_path"],
            content_hash=row["content_hash"],
            size_bytes=int(row["size_bytes"]),
            modified_ns=int(row["modified_ns"]),
            indexed_at=row["indexed_at"],
            sync_status=row["sync_status"],
            last_error=row["last_error"],
        )

    def list_for_project(self, project_id: str) -> list[ProjectFileRecord]:
        with self.database.read() as connection:
            rows = connection.execute(
                """
                SELECT * FROM project_files
                WHERE project_id = ?
                ORDER BY relative_path COLLATE NOCASE
                """,
                (project_id,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def upsert(self, record: ProjectFileRecord) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO project_files(
                    project_id, relative_path, relative_key, content_hash,
                    size_bytes, modified_ns, indexed_at, sync_status, last_error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, relative_path) DO UPDATE SET
                    relative_key = excluded.relative_key,
                    content_hash = excluded.content_hash,
                    size_bytes = excluded.size_bytes,
                    modified_ns = excluded.modified_ns,
                    indexed_at = excluded.indexed_at,
                    sync_status = excluded.sync_status,
                    last_error = excluded.last_error
                """,
                (
                    record.project_id,
                    record.relative_path,
                    _relative_key(record.relative_path),
                    record.content_hash,
                    record.size_bytes,
                    record.modified_ns,
                    record.indexed_at,
                    record.sync_status,
                    record.last_error,
                ),
            )

    def delete(self, project_id: str, relative_path: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                DELETE FROM project_files
                WHERE project_id = ? AND relative_path = ?
                """,
                (project_id, relative_path),
            )

    def mark_all_pending(self) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE project_files
                SET sync_status = 'pending', last_error = NULL
                """
            )


class _ContextBudget:
    def __init__(self, max_tokens: int):
        if max_tokens <= 0:
            raise ValueError("Context budget must be greater than zero")
        self.max_tokens = max_tokens
        self.used_tokens = 0
        self.truncated = False

    def add(self, text: str) -> str | None:
        remaining = self.max_tokens - self.used_tokens
        if remaining <= 0:
            self.truncated = True
            return None

        tokens = estimate_tokens(text)
        if tokens <= remaining:
            self.used_tokens += tokens
            return text

        suffix = "\n\n[Context truncated to fit the configured budget.]"
        character_limit = remaining * 4
        if character_limit <= len(suffix):
            self.truncated = True
            return None

        fitted = text[: character_limit - len(suffix)].rstrip() + suffix
        self.used_tokens += estimate_tokens(fitted)
        self.truncated = True
        return fitted


class ProjectContextEngine:
    """Keeps project RAG state current and builds bounded LLM context."""

    def __init__(
        self,
        project_service: ProjectService | None,
        file_repository: ProjectFileRepository,
        rag_system: Any | None,
        *,
        document_service: DocumentService | None = None,
        max_context_tokens: int = 4_000,
    ):
        self.project_service = project_service
        self.file_repository = file_repository
        self.rag_system = rag_system
        self.document_service = document_service or DocumentService()
        self.max_context_tokens = max_context_tokens
        self._sync_lock = RLock()

    @property
    def active_project(self) -> Project | None:
        if self.project_service is None:
            return None
        return self.project_service.active_project

    def sync_active_project(self) -> SyncReport:
        project = self.active_project
        if project is None:
            return SyncReport(project_id=None)
        return self.sync_project(project)

    def sync_project(
        self,
        project: Project,
        *,
        force_reindex: bool = False,
    ) -> SyncReport:
        """Hash files and incrementally reconcile the project RAG namespace."""
        if self.rag_system is None:
            return SyncReport(project_id=project.id)

        with self._sync_lock:
            previous = {
                record.relative_path: record
                for record in self.file_repository.list_for_project(project.id)
            }
            current, scan_failures = self._scan_project(project)
            added = updated = removed = unchanged = failed = 0
            failed += len(scan_failures)
            for relative_path in scan_failures:
                previous.pop(relative_path, None)

            for relative_path, (path, stat) in current.items():
                old = previous.pop(relative_path, None)
                if (
                    not force_reindex
                    and old is not None
                    and old.sync_status == "indexed"
                    and old.size_bytes == stat.st_size
                    and old.modified_ns == stat.st_mtime_ns
                ):
                    unchanged += 1
                    continue

                try:
                    digest = _content_hash(path)
                except OSError:
                    failed += 1
                    logger.exception("Unable to hash project file %s", path)
                    continue

                needs_index = (
                    force_reindex
                    or old is None
                    or old.content_hash != digest
                    or old.sync_status != "indexed"
                )
                if not needs_index:
                    if (
                        old.size_bytes != stat.st_size
                        or old.modified_ns != stat.st_mtime_ns
                    ):
                        self.file_repository.upsert(
                            ProjectFileRecord(
                                project_id=old.project_id,
                                relative_path=old.relative_path,
                                content_hash=old.content_hash,
                                size_bytes=stat.st_size,
                                modified_ns=stat.st_mtime_ns,
                                indexed_at=old.indexed_at,
                                sync_status=old.sync_status,
                                last_error=old.last_error,
                            )
                        )
                    unchanged += 1
                    continue

                try:
                    success = self.rag_system.index_file(
                        str(path),
                        force_reindex=True,
                        project_id=project.id,
                        relative_path=relative_path,
                        content_hash=digest,
                    )
                    if not success:
                        raise RuntimeError("RAG indexing returned no indexed chunks")
                except Exception as error:
                    failed += 1
                    logger.exception("Unable to synchronize project file %s", path)
                    self.file_repository.upsert(
                        ProjectFileRecord(
                            project_id=project.id,
                            relative_path=relative_path,
                            content_hash=digest,
                            size_bytes=stat.st_size,
                            modified_ns=stat.st_mtime_ns,
                            indexed_at=None,
                            sync_status="error",
                            last_error=str(error),
                        )
                    )
                    continue

                self.file_repository.upsert(
                    ProjectFileRecord(
                        project_id=project.id,
                        relative_path=relative_path,
                        content_hash=digest,
                        size_bytes=stat.st_size,
                        modified_ns=stat.st_mtime_ns,
                        indexed_at=_utc_now_text(),
                        sync_status="indexed",
                    )
                )
                if old is None:
                    added += 1
                else:
                    updated += 1

            for relative_path in previous:
                absolute_path = project.root_path / Path(relative_path)
                try:
                    self.rag_system.remove_file(str(absolute_path))
                except Exception:
                    failed += 1
                    logger.exception(
                        "Unable to remove stale project context for %s",
                        absolute_path,
                    )
                    continue
                self.file_repository.delete(project.id, relative_path)
                removed += 1

            return SyncReport(
                project_id=project.id,
                added=added,
                updated=updated,
                removed=removed,
                unchanged=unchanged,
                failed=failed,
            )

    def invalidate_index_state(self) -> None:
        """Mark manifests stale after the underlying vector index is reset."""
        self.file_repository.mark_all_pending()

    def resolve_file_references(
        self,
        query: str,
        project: Project | None = None,
    ) -> list[FileReference]:
        references = self._extract_reference_names(query)
        if not references:
            return []

        selected_project = project or self.active_project
        if selected_project is None:
            return [
                FileReference(
                    reference=reference,
                    path=None,
                    relative_path=None,
                    error=f"@{reference} requires an open project",
                )
                for reference in references
            ]

        candidates = self._candidate_paths(selected_project)
        by_relative = {
            _relative_key(relative): (relative, path)
            for relative, path in candidates
        }
        by_name: dict[str, list[tuple[str, Path]]] = {}
        for relative, path in candidates:
            by_name.setdefault(path.name.casefold(), []).append((relative, path))

        resolved: list[FileReference] = []
        for reference in references:
            normalized = reference.replace("\\", "/").strip("/")
            if (
                not normalized
                or Path(normalized).is_absolute()
                or ".." in Path(normalized).parts
            ):
                resolved.append(
                    FileReference(
                        reference=reference,
                        path=None,
                        relative_path=None,
                        error=f"@{reference} is not a safe project-relative path",
                    )
                )
                continue

            exact = by_relative.get(_relative_key(normalized))
            if exact is not None:
                relative, path = exact
                resolved.append(FileReference(reference, path, relative))
                continue

            matches = by_name.get(Path(normalized).name.casefold(), [])
            if len(matches) == 1:
                relative, path = matches[0]
                resolved.append(FileReference(reference, path, relative))
            elif len(matches) > 1:
                options = ", ".join(relative for relative, _path in matches[:5])
                resolved.append(
                    FileReference(
                        reference=reference,
                        path=None,
                        relative_path=None,
                        error=f"@{reference} is ambiguous; use one of: {options}",
                    )
                )
            else:
                resolved.append(
                    FileReference(
                        reference=reference,
                        path=None,
                        relative_path=None,
                        error=f"@{reference} was not found in the active project",
                    )
                )
        return resolved

    def build_context(
        self,
        query: str,
        *,
        cin_context: str | None = None,
        top_k: int = 3,
    ) -> ContextResult:
        """Build explicit-file, injected, and RAG context within one budget."""
        project = self.active_project
        sync_report = self.sync_active_project()
        references = self.resolve_file_references(query, project)
        notices = tuple(reference.error for reference in references if reference.error)
        budget = _ContextBudget(self.max_context_tokens)
        messages: list[str] = []
        referenced_files: list[str] = []

        for reference in references:
            if reference.path is None or reference.relative_path is None:
                continue
            try:
                content = self.document_service.extract_context_text(reference.path)
            except Exception as error:
                notices += (
                    f"Unable to read @{reference.reference}: {error}",
                )
                continue
            section = (
                f"Explicit project file requested by the user: "
                f"{reference.relative_path}\n\n{content}"
            )
            fitted = budget.add(section)
            if fitted is not None:
                messages.append(fitted)
                referenced_files.append(reference.relative_path)

        if notices:
            fitted = budget.add("Context notices:\n- " + "\n- ".join(notices))
            if fitted is not None:
                messages.append(fitted)

        if cin_context:
            fitted = budget.add(
                "User-injected file context:\n\n"
                f"{cin_context}\n\nUse this context when it is relevant."
            )
            if fitted is not None:
                messages.append(fitted)

        if self.rag_system is not None and query:
            try:
                kwargs: dict[str, Any] = {
                    "top_k": top_k,
                    "boost_active_files": True,
                }
                if project is not None:
                    kwargs["project_id"] = project.id
                context = self.rag_system.get_context(query, **kwargs)
                if context and context.chunks:
                    fitted = budget.add(
                        "Relevant context retrieved from project files:\n\n"
                        f"{context.format_for_llm()}"
                    )
                    if fitted is not None:
                        messages.append(fitted)
            except Exception:
                logger.exception("Project RAG context retrieval failed")

        return ContextResult(
            system_messages=tuple(messages),
            total_tokens=budget.used_tokens,
            max_tokens=budget.max_tokens,
            truncated=budget.truncated,
            notices=notices,
            sync_report=sync_report,
            referenced_files=tuple(referenced_files),
        )

    def _scan_project(
        self,
        project: Project,
    ) -> tuple[
        dict[str, tuple[Path, os.stat_result]],
        set[str],
    ]:
        files: dict[str, tuple[Path, os.stat_result]] = {}
        failures: set[str] = set()
        for relative_path, path in self._candidate_paths(project):
            try:
                stat = path.stat()
                files[relative_path] = (path, stat)
            except OSError:
                logger.exception("Unable to inspect project file %s", path)
                failures.add(relative_path)
        return files, failures

    @staticmethod
    def _candidate_paths(project: Project) -> list[tuple[str, Path]]:
        root = project.root_path.resolve()
        candidates: list[tuple[str, Path]] = []
        for current_root, directory_names, file_names in os.walk(root):
            directory_names[:] = sorted(
                name
                for name in directory_names
                if name not in IGNORED_DIRECTORIES and not name.startswith(".")
            )
            current = Path(current_root)
            for file_name in sorted(file_names):
                path = current / file_name
                if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                try:
                    resolved = path.resolve()
                    relative = resolved.relative_to(root).as_posix()
                except (OSError, ValueError):
                    logger.warning("Skipping project file outside root: %s", path)
                    continue
                candidates.append((relative, resolved))
        return candidates

    @staticmethod
    def _extract_reference_names(query: str) -> list[str]:
        references: list[str] = []
        seen: set[str] = set()
        for match in FILE_REFERENCE_PATTERN.finditer(query):
            raw = next(group for group in match.groups() if group is not None)
            reference = raw.rstrip(".,!?:)]}")
            key = reference.casefold()
            if reference and key not in seen:
                references.append(reference)
                seen.add(key)
        return references
