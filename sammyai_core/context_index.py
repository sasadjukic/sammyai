"""Read-only context index inventory shared by storage and UI."""

from dataclasses import dataclass


@dataclass(frozen=True)
class IndexedFileSummary:
    file_path: str
    project_id: str | None
    chunk_count: int
