"""UI-independent state for one open editor document."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from uuid import uuid4


def normalize_document_path(path: str | Path) -> str:
    """Return a stable comparison key without requiring the path to exist."""
    resolved = Path(path).expanduser().resolve(strict=False)
    return os.path.normcase(os.path.normpath(str(resolved)))


def document_format_id(path: str | Path | None) -> str:
    """Return the small format identifier supported by the current editor."""
    if path is None:
        return "plain_text"
    return "markdown" if Path(path).suffix.casefold() == ".md" else "plain_text"


@dataclass
class DocumentSession:
    """Persistent-in-memory state for a document shown in the workspace."""

    display_name: str
    content: str = ""
    path: Path | None = None
    clean_snapshot: str = ""
    session_id: str = field(default_factory=lambda: str(uuid4()))
    cursor_position: int = 0
    vertical_scroll: int = 0
    horizontal_scroll: int = 0
    format_id: str = "plain_text"
    external_change_state: str = "unchanged"

    def __post_init__(self) -> None:
        if self.path is not None:
            self.path = Path(self.path).expanduser().resolve(strict=False)
            self.display_name = self.path.name
            self.format_id = document_format_id(self.path)

    @classmethod
    def untitled(cls, number: int) -> "DocumentSession":
        return cls(display_name=f"Untitled {number}")

    @classmethod
    def from_path(cls, path: str | Path, content: str) -> "DocumentSession":
        resolved = Path(path).expanduser().resolve(strict=False)
        return cls(
            path=resolved,
            display_name=resolved.name,
            content=content,
            clean_snapshot=content,
            format_id=document_format_id(resolved),
        )

    @property
    def normalized_path(self) -> str | None:
        return normalize_document_path(self.path) if self.path is not None else None

    @property
    def is_modified(self) -> bool:
        return self.content != self.clean_snapshot

    def update_content(self, content: str) -> None:
        self.content = content

    def mark_clean(self, content: str | None = None) -> None:
        if content is not None:
            self.content = content
        self.clean_snapshot = self.content
        self.external_change_state = "unchanged"

    def assign_path(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve(strict=False)
        self.display_name = self.path.name
        self.format_id = document_format_id(self.path)

