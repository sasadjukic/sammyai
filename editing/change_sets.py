"""Structured, reviewable descriptions of proposed project file changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Iterable
from uuid import uuid4


class ChangeSetError(RuntimeError):
    """Base exception for invalid or conflicting structured changes."""


class EditConflict(ChangeSetError):
    """Raised when a structured edit does not match its expected source."""


class FileChangeKind(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class FileRequestKind(str, Enum):
    WRITE = "write"
    EDIT = "edit"
    DELETE = "delete"


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TextEdit:
    """Replace one zero-based character range in a UTF-8 text file."""

    start: int
    end: int
    replacement: str
    expected_text: str | None = None

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError("Text edit range is invalid")


def apply_text_edits(original: str, edits: Iterable[TextEdit]) -> str:
    """Apply non-overlapping edits against one immutable source snapshot."""
    ordered = sorted(tuple(edits), key=lambda edit: (edit.start, edit.end))
    previous_end = 0
    for edit in ordered:
        if edit.end > len(original):
            raise EditConflict(
                f"Edit range {edit.start}:{edit.end} exceeds file length "
                f"{len(original)}"
            )
        if edit.start < previous_end:
            raise EditConflict("Structured edits overlap")
        if (
            edit.expected_text is not None
            and original[edit.start:edit.end] != edit.expected_text
        ):
            raise EditConflict(
                f"Edit range {edit.start}:{edit.end} no longer matches "
                "the expected text"
            )
        previous_end = edit.end

    result = original
    for edit in reversed(ordered):
        result = result[:edit.start] + edit.replacement + result[edit.end:]
    return result


@dataclass(frozen=True)
class FileChangeRequest:
    relative_path: str
    kind: FileRequestKind
    content: str | None = None
    edits: tuple[TextEdit, ...] = ()

    @classmethod
    def write(cls, relative_path: str, content: str) -> "FileChangeRequest":
        return cls(relative_path, FileRequestKind.WRITE, content=content)

    @classmethod
    def edit(
        cls,
        relative_path: str,
        edits: Iterable[TextEdit],
    ) -> "FileChangeRequest":
        return cls(relative_path, FileRequestKind.EDIT, edits=tuple(edits))

    @classmethod
    def delete(cls, relative_path: str) -> "FileChangeRequest":
        return cls(relative_path, FileRequestKind.DELETE)

    def __post_init__(self) -> None:
        if not self.relative_path.strip():
            raise ValueError("File change path cannot be empty")
        if self.kind == FileRequestKind.WRITE and self.content is None:
            raise ValueError("Write requests require content")
        if self.kind == FileRequestKind.WRITE and self.edits:
            raise ValueError("Write requests cannot contain text edits")
        if self.kind == FileRequestKind.EDIT and not self.edits:
            raise ValueError("Edit requests require at least one text edit")
        if self.kind == FileRequestKind.EDIT and self.content is not None:
            raise ValueError("Edit requests cannot contain full-file content")
        if self.kind == FileRequestKind.DELETE and (
            self.content is not None or self.edits
        ):
            raise ValueError("Delete requests cannot contain content or edits")


@dataclass(frozen=True)
class FileChange:
    relative_path: str
    kind: FileChangeKind
    before_content: str | None
    after_content: str | None
    before_hash: str | None
    after_hash: str | None

    def __post_init__(self) -> None:
        if not self.relative_path.strip():
            raise ValueError("File change path cannot be empty")
        if self.kind == FileChangeKind.CREATE and self.before_content is not None:
            raise ValueError("Create changes cannot have previous content")
        if self.kind == FileChangeKind.CREATE and self.after_content is None:
            raise ValueError("Create changes require resulting content")
        if self.kind == FileChangeKind.DELETE and self.after_content is not None:
            raise ValueError("Delete changes cannot have resulting content")
        if self.kind == FileChangeKind.DELETE and self.before_content is None:
            raise ValueError("Delete changes require previous content")
        if self.kind == FileChangeKind.UPDATE and (
            self.before_content is None or self.after_content is None
        ):
            raise ValueError("Update changes require previous and resulting content")
        if self.before_content is not None:
            if self.before_hash != content_hash(self.before_content):
                raise ValueError("Previous content hash is inconsistent")
        elif self.before_hash is not None:
            raise ValueError("Previous hash requires previous content")
        if self.after_content is not None:
            if self.after_hash != content_hash(self.after_content):
                raise ValueError("Resulting content hash is inconsistent")
        elif self.after_hash is not None:
            raise ValueError("Resulting hash requires resulting content")


@dataclass(frozen=True)
class ChangeSet:
    project_id: str
    description: str
    changes: tuple[FileChange, ...]
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        if not self.changes:
            raise ValueError("A change set must contain at least one file change")
        paths = [change.relative_path.casefold() for change in self.changes]
        if len(paths) != len(set(paths)):
            raise ValueError("A change set cannot modify the same path twice")


@dataclass(frozen=True)
class FileChangePreview:
    relative_path: str
    kind: FileChangeKind
    unified_diff: str
    additions: int
    deletions: int


@dataclass(frozen=True)
class ChangeSetPreview:
    change_set_id: str
    description: str
    files: tuple[FileChangePreview, ...]

    @property
    def additions(self) -> int:
        return sum(file.additions for file in self.files)

    @property
    def deletions(self) -> int:
        return sum(file.deletions for file in self.files)
