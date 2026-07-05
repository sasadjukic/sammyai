"""Project-confined file tools with atomic change-set apply and undo."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import tempfile
from typing import Iterable

from editing.change_sets import (
    ChangeSet,
    ChangeSetPreview,
    FileChange,
    FileChangeKind,
    FileChangePreview,
    FileChangeRequest,
    FileRequestKind,
    apply_text_edits,
    content_hash,
)
from editing.diff_manager import DiffFormat, DiffManager

from .projects import Project, ProjectService


ALLOWED_TEXT_EXTENSIONS = frozenset({".md", ".txt"})
BLOCKED_PATH_PARTS = frozenset({".git", ".hg", ".svn", ".sammyai"})


class FileToolError(RuntimeError):
    """Base exception for safe project file operations."""


class UnsafePathError(FileToolError):
    """Raised when a requested path escapes or aliases the project root."""


class ChangeConflictError(FileToolError):
    """Raised when files changed after a change set was prepared."""


class ChangeApplyError(FileToolError):
    """Raised when a staged change set cannot be committed safely."""


@dataclass(frozen=True)
class AppliedChangeSet:
    change_set: ChangeSet
    changed_paths: tuple[str, ...]


@dataclass
class _StagedFile:
    change: FileChange
    target: Path
    staged_path: Path | None = None
    backup_path: Path | None = None
    applied: bool = False


class SafeFileTools:
    """Prepare, preview, atomically apply, and undo project file changes."""

    def __init__(
        self,
        project_service: ProjectService,
        *,
        max_file_bytes: int = 10 * 1024 * 1024,
    ):
        self.project_service = project_service
        self.max_file_bytes = max_file_bytes
        self.diff_manager = DiffManager()
        self._undo_stack: list[AppliedChangeSet] = []
        self._redo_stack: list[AppliedChangeSet] = []

    def read_text(self, relative_path: str) -> str:
        project = self._require_project()
        target = self._resolve_path(project, relative_path, must_exist=True)
        return self._read_text(target)

    def prepare_change_set(
        self,
        requests: Iterable[FileChangeRequest],
        *,
        description: str,
    ) -> ChangeSet:
        project = self._require_project()
        prepared: list[FileChange] = []
        seen: set[str] = set()

        for request in requests:
            target = self._resolve_path(
                project,
                request.relative_path,
                must_exist=request.kind != FileRequestKind.WRITE,
            )
            relative_path = target.relative_to(project.root_path).as_posix()
            key = os.path.normcase(relative_path)
            if key in seen:
                raise FileToolError(
                    f"A change set cannot modify {relative_path} more than once"
                )
            seen.add(key)

            exists = target.exists()
            before = self._read_text(target) if exists else None

            if request.kind == FileRequestKind.WRITE:
                after = request.content
                kind = FileChangeKind.UPDATE if exists else FileChangeKind.CREATE
            elif request.kind == FileRequestKind.EDIT:
                if before is None:
                    raise FileToolError(f"Cannot edit missing file: {relative_path}")
                after = apply_text_edits(before, request.edits)
                kind = FileChangeKind.UPDATE
            else:
                if before is None:
                    raise FileToolError(f"Cannot delete missing file: {relative_path}")
                after = None
                kind = FileChangeKind.DELETE

            if before == after:
                continue
            prepared.append(
                FileChange(
                    relative_path=relative_path,
                    kind=kind,
                    before_content=before,
                    after_content=after,
                    before_hash=content_hash(before) if before is not None else None,
                    after_hash=content_hash(after) if after is not None else None,
                )
            )

        if not prepared:
            raise FileToolError("The requested change set contains no changes")
        return ChangeSet(
            project_id=project.id,
            description=description.strip() or "Project file changes",
            changes=tuple(prepared),
        )

    def preview(self, change_set: ChangeSet) -> ChangeSetPreview:
        files: list[FileChangePreview] = []
        for change in change_set.changes:
            before = change.before_content or ""
            after = change.after_content or ""
            diff = self.diff_manager.generate_diff(
                before,
                after,
                original_name=f"a/{change.relative_path}",
                modified_name=f"b/{change.relative_path}",
                format=DiffFormat.UNIFIED,
            )
            stats = self.diff_manager.get_diff_stats(diff)
            files.append(
                FileChangePreview(
                    relative_path=change.relative_path,
                    kind=change.kind,
                    unified_diff=str(diff),
                    additions=stats["additions"],
                    deletions=stats["deletions"],
                )
            )
        return ChangeSetPreview(
            change_set_id=change_set.id,
            description=change_set.description,
            files=tuple(files),
        )

    def apply(self, change_set: ChangeSet) -> AppliedChangeSet:
        result = self._apply(change_set)
        self._undo_stack.append(result)
        self._redo_stack.clear()
        return result

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def undo_last(self) -> AppliedChangeSet:
        if not self._undo_stack:
            raise FileToolError("There is no applied change set to undo")
        applied = self._undo_stack[-1]
        inverse = self._inverse(applied.change_set, prefix="Undo")
        self._apply(inverse)
        self._undo_stack.pop()
        self._redo_stack.append(applied)
        return applied

    def redo_last(self) -> AppliedChangeSet:
        if not self._redo_stack:
            raise FileToolError("There is no change set to redo")
        applied = self._redo_stack[-1]
        result = self._apply(applied.change_set)
        self._redo_stack.pop()
        self._undo_stack.append(applied)
        return result

    def _apply(self, change_set: ChangeSet) -> AppliedChangeSet:
        project = self._require_project()
        if change_set.project_id != project.id:
            raise ChangeConflictError(
                "The change set belongs to a different project"
            )

        staged: list[_StagedFile] = []
        created_directories: list[Path] = []
        try:
            resolved: list[tuple[FileChange, Path]] = []
            for change in change_set.changes:
                target = self._resolve_path(
                    project,
                    change.relative_path,
                    must_exist=change.before_content is not None,
                )
                self._validate_precondition(target, change)
                resolved.append((change, target))

            for change, target in resolved:
                staged_file = _StagedFile(change=change, target=target)
                staged.append(staged_file)
                if change.after_content is not None:
                    created_directories.extend(
                        self._create_parent_directories(
                            project.root_path,
                            target.parent,
                        )
                    )
                    staged_file.staged_path = self._stage_content(
                        target,
                        change.after_content,
                    )
                if change.before_content is not None:
                    staged_file.backup_path = self._backup_file(target)

            for item in staged:
                self._validate_precondition(item.target, item.change)
                if item.change.after_content is None:
                    item.target.unlink()
                else:
                    self._replace(item.staged_path, item.target)
                    item.staged_path = None
                item.applied = True
        except Exception as error:
            rollback_error = self._rollback(staged)
            self._cleanup(staged, preserve_backups=bool(rollback_error))
            self._cleanup_directories(created_directories)
            if isinstance(error, FileToolError) and not rollback_error:
                raise
            detail = f"; rollback failed: {rollback_error}" if rollback_error else ""
            raise ChangeApplyError(f"Unable to apply change set: {error}{detail}") from error

        self._cleanup(staged)
        return AppliedChangeSet(
            change_set=change_set,
            changed_paths=tuple(change.relative_path for change in change_set.changes),
        )

    def _validate_precondition(self, target: Path, change: FileChange) -> None:
        if change.before_content is None:
            if target.exists():
                raise ChangeConflictError(
                    f"Cannot create {change.relative_path}: file now exists"
                )
            return
        if not target.is_file():
            raise ChangeConflictError(
                f"Cannot change {change.relative_path}: file is missing"
            )
        current = self._read_text(target)
        if content_hash(current) != change.before_hash:
            raise ChangeConflictError(
                f"Cannot change {change.relative_path}: content changed "
                "after the change set was prepared"
            )

    def _inverse(self, change_set: ChangeSet, *, prefix: str) -> ChangeSet:
        changes: list[FileChange] = []
        for change in change_set.changes:
            if change.kind == FileChangeKind.CREATE:
                kind = FileChangeKind.DELETE
            elif change.kind == FileChangeKind.DELETE:
                kind = FileChangeKind.CREATE
            else:
                kind = FileChangeKind.UPDATE
            changes.append(
                FileChange(
                    relative_path=change.relative_path,
                    kind=kind,
                    before_content=change.after_content,
                    after_content=change.before_content,
                    before_hash=change.after_hash,
                    after_hash=change.before_hash,
                )
            )
        return ChangeSet(
            project_id=change_set.project_id,
            description=f"{prefix}: {change_set.description}",
            changes=tuple(changes),
        )

    def _require_project(self) -> Project:
        project = self.project_service.active_project
        if project is None:
            raise FileToolError("A project must be open to use file tools")
        return project

    def _resolve_path(
        self,
        project: Project,
        relative_path: str,
        *,
        must_exist: bool,
    ) -> Path:
        normalized = relative_path.replace("\\", "/")
        pure_path = PurePosixPath(normalized)
        windows_path = PureWindowsPath(normalized)
        if (
            pure_path.is_absolute()
            or windows_path.is_absolute()
            or bool(windows_path.drive)
            or not pure_path.parts
            or any(part in {"", ".", ".."} for part in pure_path.parts)
            or any(part.casefold() in BLOCKED_PATH_PARTS for part in pure_path.parts)
        ):
            raise UnsafePathError(f"Unsafe project-relative path: {relative_path}")
        if Path(pure_path.name).suffix.lower() not in ALLOWED_TEXT_EXTENSIONS:
            raise UnsafePathError(
                f"Unsupported editable file type: {pure_path.suffix or '(none)'}"
            )

        root = project.root_path.resolve()
        target = root.joinpath(*pure_path.parts)
        cursor = root
        for part in pure_path.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise UnsafePathError(
                    f"Symbolic links are not allowed in change paths: {relative_path}"
                )
        try:
            target.resolve(strict=False).relative_to(root)
        except ValueError as error:
            raise UnsafePathError(
                f"Path escapes the active project: {relative_path}"
            ) from error
        if must_exist and not target.is_file():
            raise FileToolError(f"Project file does not exist: {relative_path}")
        if target.exists() and not target.is_file():
            raise UnsafePathError(f"Path is not a regular file: {relative_path}")
        return target

    def _read_text(self, path: Path) -> str:
        size = path.stat().st_size
        if size > self.max_file_bytes:
            raise FileToolError(
                f"File exceeds the {self.max_file_bytes}-byte safety limit: {path}"
            )
        try:
            return path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as error:
            raise FileToolError(f"File is not valid UTF-8 text: {path}") from error

    def _stage_content(self, target: Path, content: str) -> Path:
        encoded = content.encode("utf-8")
        if len(encoded) > self.max_file_bytes:
            raise FileToolError(
                f"Result exceeds the {self.max_file_bytes}-byte safety limit: {target}"
            )
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".sammyai-tmp",
            dir=target.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as temporary:
                temporary.write(encoded)
                temporary.flush()
                os.fsync(temporary.fileno())
            if target.exists():
                shutil.copymode(target, temporary_path)
            return temporary_path
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _create_parent_directories(root: Path, parent: Path) -> list[Path]:
        missing: list[Path] = []
        cursor = parent
        while cursor != root and not cursor.exists():
            missing.append(cursor)
            cursor = cursor.parent
        created: list[Path] = []
        try:
            for directory in reversed(missing):
                directory.mkdir()
                created.append(directory)
        except Exception:
            SafeFileTools._cleanup_directories(created)
            raise
        return created

    @staticmethod
    def _cleanup_directories(directories: list[Path]) -> None:
        for directory in reversed(directories):
            try:
                directory.rmdir()
            except OSError:
                pass

    @staticmethod
    def _backup_file(target: Path) -> Path:
        descriptor, backup_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".sammyai-bak",
            dir=target.parent,
        )
        os.close(descriptor)
        backup_path = Path(backup_name)
        try:
            shutil.copy2(target, backup_path)
            return backup_path
        except Exception:
            backup_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _replace(source: Path | None, target: Path) -> None:
        if source is None:
            raise ChangeApplyError(f"No staged content exists for {target}")
        os.replace(source, target)

    def _rollback(self, staged: list[_StagedFile]) -> str | None:
        errors: list[str] = []
        for item in reversed(staged):
            if not item.applied:
                continue
            try:
                if item.backup_path is not None and item.backup_path.exists():
                    os.replace(item.backup_path, item.target)
                    item.backup_path = None
                else:
                    item.target.unlink(missing_ok=True)
            except Exception as error:
                errors.append(f"{item.change.relative_path}: {error}")
        return "; ".join(errors) or None

    @staticmethod
    def _cleanup(
        staged: list[_StagedFile],
        *,
        preserve_backups: bool = False,
    ) -> None:
        for item in staged:
            if item.staged_path is not None:
                item.staged_path.unlink(missing_ok=True)
            if item.backup_path is not None and not preserve_backups:
                item.backup_path.unlink(missing_ok=True)
