"""Project-scoped persistent memory, provenance, and conversation summaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
import sqlite3
from typing import Any, Callable, Iterable
from uuid import uuid4

from llm.prompt_layers import PromptComposer, PromptLayer, PromptLayerOrder

from .database import ProjectDatabase
from .projects import Project, ProjectService


class MemoryError(RuntimeError):
    """Base exception for persistent-memory operations."""


class MemoryDuplicateError(MemoryError):
    """Raised when identical structured memory already exists."""


class MemoryKind(str, Enum):
    CHARACTER = "character"
    PLOT = "plot"
    WORLD = "world"
    STYLE = "style"
    DECISION = "decision"
    PREFERENCE = "preference"
    OTHER = "other"

    @property
    def display_name(self) -> str:
        return self.value.replace("_", " ").title()


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ProvenanceType(str, Enum):
    USER = "user"
    FILE = "file"
    CHAT = "chat"
    AGENT = "agent"
    SUMMARY = "summary"


@dataclass(frozen=True)
class MemoryProvenance:
    id: str
    memory_id: str
    source_type: ProvenanceType
    source_ref: str | None
    source_label: str
    excerpt: str | None
    created_at: datetime


@dataclass(frozen=True)
class Memory:
    id: str
    project_id: str
    kind: MemoryKind
    title: str
    content: str
    status: MemoryStatus
    confidence: float
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None
    provenance: tuple[MemoryProvenance, ...] = ()


@dataclass(frozen=True)
class ConversationSummary:
    id: str
    project_id: str
    session_id: str
    title: str
    content: str
    message_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SuggestedMemory:
    kind: MemoryKind
    title: str
    content: str
    confidence: float = 0.8


@dataclass(frozen=True)
class ConversationSummaryDraft:
    project_id: str
    session_id: str
    title: str
    content: str
    message_count: int
    suggested_memories: tuple[SuggestedMemory, ...] = ()


@dataclass(frozen=True)
class MemoryContext:
    text: str
    total_tokens: int
    memory_ids: tuple[str, ...]
    summary_ids: tuple[str, ...]
    truncated: bool = False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _from_text(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _hash_content(content: str) -> str:
    normalized = " ".join(content.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4) if text else 0


class MemoryRepository:
    def __init__(self, database: ProjectDatabase):
        self.database = database

    def create_memory(
        self,
        project_id: str,
        kind: MemoryKind,
        title: str,
        content: str,
        *,
        confidence: float = 1.0,
        provenance: Iterable[
            tuple[ProvenanceType, str | None, str, str | None]
        ] = (),
    ) -> Memory:
        cleaned_title = title.strip()
        cleaned_content = content.strip()
        if not cleaned_title or not cleaned_content:
            raise MemoryError("Memory title and content are required")
        if not 0.0 <= confidence <= 1.0:
            raise MemoryError("Memory confidence must be between 0 and 1")

        memory_id = str(uuid4())
        now = _utc_now()
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO memories(
                        id, project_id, kind, title, content, content_hash,
                        status, confidence, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        memory_id,
                        project_id,
                        kind.value,
                        cleaned_title,
                        cleaned_content,
                        _hash_content(cleaned_content),
                        MemoryStatus.ACTIVE.value,
                        confidence,
                        _to_text(now),
                        _to_text(now),
                    ),
                )
                for source_type, source_ref, source_label, excerpt in provenance:
                    self._insert_provenance(
                        connection,
                        memory_id,
                        source_type,
                        source_ref,
                        source_label,
                        excerpt,
                        now,
                    )
        except sqlite3.IntegrityError as error:
            if "UNIQUE constraint failed" in str(error):
                raise MemoryDuplicateError(
                    "An identical memory already exists in this project"
                ) from error
            raise
        memory = self.get_memory(memory_id)
        if memory is None:
            raise MemoryError("Memory was not persisted")
        return memory

    def update_memory(
        self,
        memory_id: str,
        *,
        kind: MemoryKind,
        title: str,
        content: str,
        confidence: float,
        status: MemoryStatus,
    ) -> Memory:
        cleaned_title = title.strip()
        cleaned_content = content.strip()
        if not cleaned_title or not cleaned_content:
            raise MemoryError("Memory title and content are required")
        if not 0.0 <= confidence <= 1.0:
            raise MemoryError("Memory confidence must be between 0 and 1")
        try:
            with self.database.transaction() as connection:
                cursor = connection.execute(
                    """
                    UPDATE memories
                    SET kind = ?, title = ?, content = ?, content_hash = ?,
                        confidence = ?, status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        kind.value,
                        cleaned_title,
                        cleaned_content,
                        _hash_content(cleaned_content),
                        confidence,
                        status.value,
                        _to_text(_utc_now()),
                        memory_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise MemoryError(f"Unknown memory: {memory_id}")
        except sqlite3.IntegrityError as error:
            if "UNIQUE constraint failed" in str(error):
                raise MemoryDuplicateError(
                    "An identical memory already exists in this project"
                ) from error
            raise
        memory = self.get_memory(memory_id)
        if memory is None:
            raise MemoryError(f"Unknown memory: {memory_id}")
        return memory

    def add_provenance(
        self,
        memory_id: str,
        source_type: ProvenanceType,
        source_ref: str | None,
        source_label: str,
        excerpt: str | None = None,
    ) -> MemoryProvenance:
        provenance_id = str(uuid4())
        now = _utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO memory_provenance(
                    id, memory_id, source_type, source_ref,
                    source_label, excerpt, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    provenance_id,
                    memory_id,
                    source_type.value,
                    source_ref,
                    source_label.strip(),
                    excerpt.strip() if excerpt else None,
                    _to_text(now),
                ),
            )
        return MemoryProvenance(
            id=provenance_id,
            memory_id=memory_id,
            source_type=source_type,
            source_ref=source_ref,
            source_label=source_label.strip(),
            excerpt=excerpt.strip() if excerpt else None,
            created_at=now,
        )

    def get_memory(self, memory_id: str) -> Memory | None:
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT * FROM memories WHERE id = ?",
                (memory_id,),
            ).fetchone()
            if row is None:
                return None
            provenance_rows = connection.execute(
                """
                SELECT * FROM memory_provenance
                WHERE memory_id = ?
                ORDER BY created_at, id
                """,
                (memory_id,),
            ).fetchall()
        return self._memory_from_row(row, provenance_rows)

    def list_memories(
        self,
        project_id: str,
        *,
        status: MemoryStatus | None = None,
        kind: MemoryKind | None = None,
        search: str = "",
        limit: int = 500,
    ) -> list[Memory]:
        clauses = ["project_id = ?"]
        parameters: list[Any] = [project_id]
        if status is not None:
            clauses.append("status = ?")
            parameters.append(status.value)
        if kind is not None:
            clauses.append("kind = ?")
            parameters.append(kind.value)
        if search.strip():
            clauses.append("(title LIKE ? OR content LIKE ?)")
            pattern = f"%{search.strip()}%"
            parameters.extend((pattern, pattern))
        parameters.append(max(0, limit))

        with self.database.read() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM memories
                WHERE {' AND '.join(clauses)}
                ORDER BY updated_at DESC, title COLLATE NOCASE
                LIMIT ?
                """,
                parameters,
            ).fetchall()
            memory_ids = [row["id"] for row in rows]
            provenance_by_memory: dict[str, list[Any]] = {
                memory_id: [] for memory_id in memory_ids
            }
            if memory_ids:
                placeholders = ",".join("?" for _ in memory_ids)
                provenance_rows = connection.execute(
                    f"""
                    SELECT * FROM memory_provenance
                    WHERE memory_id IN ({placeholders})
                    ORDER BY created_at, id
                    """,
                    memory_ids,
                ).fetchall()
                for provenance_row in provenance_rows:
                    provenance_by_memory[provenance_row["memory_id"]].append(
                        provenance_row
                    )
        return [
            self._memory_from_row(row, provenance_by_memory[row["id"]])
            for row in rows
        ]

    def delete_memory(self, memory_id: str) -> None:
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM memories WHERE id = ?", (memory_id,))

    def touch_memories(self, memory_ids: Iterable[str]) -> None:
        ids = tuple(dict.fromkeys(memory_ids))
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        with self.database.transaction() as connection:
            connection.execute(
                f"""
                UPDATE memories SET last_used_at = ?
                WHERE id IN ({placeholders})
                """,
                (_to_text(_utc_now()), *ids),
            )

    def save_summary(
        self,
        project_id: str,
        session_id: str,
        title: str,
        content: str,
        message_count: int,
    ) -> ConversationSummary:
        cleaned_title = title.strip()
        cleaned_content = content.strip()
        if not cleaned_title or not cleaned_content:
            raise MemoryError("Summary title and content are required")
        if message_count < 0:
            raise MemoryError("Summary message count cannot be negative")
        summary_id = str(uuid4())
        now = _utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO conversation_summaries(
                    id, project_id, session_id, title, content, content_hash,
                    message_count, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, session_id, message_count) DO UPDATE SET
                    title = excluded.title,
                    content = excluded.content,
                    content_hash = excluded.content_hash,
                    updated_at = excluded.updated_at
                """,
                (
                    summary_id,
                    project_id,
                    session_id,
                    cleaned_title,
                    cleaned_content,
                    _hash_content(cleaned_content),
                    message_count,
                    _to_text(now),
                    _to_text(now),
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM conversation_summaries
                WHERE project_id = ? AND session_id = ? AND message_count = ?
                """,
                (project_id, session_id, message_count),
            ).fetchone()
        return self._summary_from_row(row)

    def save_summary_bundle(
        self,
        project_id: str,
        session_id: str,
        title: str,
        content: str,
        message_count: int,
        suggestions: Iterable[SuggestedMemory],
    ) -> tuple[ConversationSummary, tuple[Memory, ...]]:
        """Atomically save a summary and its selected structured memories."""
        cleaned_title = title.strip()
        cleaned_content = content.strip()
        selected = tuple(suggestions)
        if not cleaned_title or not cleaned_content:
            raise MemoryError("Summary title and content are required")
        if message_count < 0:
            raise MemoryError("Summary message count cannot be negative")
        for suggestion in selected:
            if not suggestion.title.strip() or not suggestion.content.strip():
                raise MemoryError(
                    "Selected memory suggestions require a title and content"
                )
            if not 0.0 <= suggestion.confidence <= 1.0:
                raise MemoryError(
                    "Suggested memory confidence must be between 0 and 1"
                )

        now = _utc_now()
        summary_id = str(uuid4())
        memory_ids: list[str] = []
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO conversation_summaries(
                    id, project_id, session_id, title, content, content_hash,
                    message_count, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, session_id, message_count) DO UPDATE SET
                    title = excluded.title,
                    content = excluded.content,
                    content_hash = excluded.content_hash,
                    updated_at = excluded.updated_at
                """,
                (
                    summary_id,
                    project_id,
                    session_id,
                    cleaned_title,
                    cleaned_content,
                    _hash_content(cleaned_content),
                    message_count,
                    _to_text(now),
                    _to_text(now),
                ),
            )
            summary_row = connection.execute(
                """
                SELECT * FROM conversation_summaries
                WHERE project_id = ? AND session_id = ? AND message_count = ?
                """,
                (project_id, session_id, message_count),
            ).fetchone()
            persisted_summary_id = summary_row["id"]

            for suggestion in selected:
                memory_id = str(uuid4())
                try:
                    connection.execute(
                        """
                        INSERT INTO memories(
                            id, project_id, kind, title, content, content_hash,
                            status, confidence, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            memory_id,
                            project_id,
                            suggestion.kind.value,
                            suggestion.title.strip(),
                            suggestion.content.strip(),
                            _hash_content(suggestion.content.strip()),
                            MemoryStatus.ACTIVE.value,
                            suggestion.confidence,
                            _to_text(now),
                            _to_text(now),
                        ),
                    )
                except sqlite3.IntegrityError as error:
                    if "UNIQUE constraint failed" in str(error):
                        continue
                    raise
                self._insert_provenance(
                    connection,
                    memory_id,
                    ProvenanceType.SUMMARY,
                    persisted_summary_id,
                    f"Summary: {cleaned_title}",
                    suggestion.content,
                    now,
                )
                self._insert_provenance(
                    connection,
                    memory_id,
                    ProvenanceType.CHAT,
                    session_id,
                    f"Chat session {session_id}",
                    None,
                    now,
                )
                memory_ids.append(memory_id)

        summary = self._summary_from_row(summary_row)
        memories = tuple(
            memory
            for memory_id in memory_ids
            if (memory := self.get_memory(memory_id)) is not None
        )
        return summary, memories

    def list_summaries(
        self,
        project_id: str,
        *,
        limit: int = 100,
    ) -> list[ConversationSummary]:
        with self.database.read() as connection:
            rows = connection.execute(
                """
                SELECT * FROM conversation_summaries
                WHERE project_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (project_id, max(0, limit)),
            ).fetchall()
        return [self._summary_from_row(row) for row in rows]

    def delete_summary(self, summary_id: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "DELETE FROM conversation_summaries WHERE id = ?",
                (summary_id,),
            )

    @staticmethod
    def _insert_provenance(
        connection,
        memory_id: str,
        source_type: ProvenanceType,
        source_ref: str | None,
        source_label: str,
        excerpt: str | None,
        created_at: datetime,
    ) -> None:
        connection.execute(
            """
            INSERT INTO memory_provenance(
                id, memory_id, source_type, source_ref,
                source_label, excerpt, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                memory_id,
                source_type.value,
                source_ref,
                source_label.strip(),
                excerpt.strip() if excerpt else None,
                _to_text(created_at),
            ),
        )

    @staticmethod
    def _memory_from_row(row, provenance_rows) -> Memory:
        return Memory(
            id=row["id"],
            project_id=row["project_id"],
            kind=MemoryKind(row["kind"]),
            title=row["title"],
            content=row["content"],
            status=MemoryStatus(row["status"]),
            confidence=float(row["confidence"]),
            created_at=_from_text(row["created_at"]),
            updated_at=_from_text(row["updated_at"]),
            last_used_at=_from_text(row["last_used_at"]),
            provenance=tuple(
                MemoryProvenance(
                    id=provenance_row["id"],
                    memory_id=provenance_row["memory_id"],
                    source_type=ProvenanceType(provenance_row["source_type"]),
                    source_ref=provenance_row["source_ref"],
                    source_label=provenance_row["source_label"],
                    excerpt=provenance_row["excerpt"],
                    created_at=_from_text(provenance_row["created_at"]),
                )
                for provenance_row in provenance_rows
            ),
        )

    @staticmethod
    def _summary_from_row(row) -> ConversationSummary:
        return ConversationSummary(
            id=row["id"],
            project_id=row["project_id"],
            session_id=row["session_id"],
            title=row["title"],
            content=row["content"],
            message_count=int(row["message_count"]),
            created_at=_from_text(row["created_at"]),
            updated_at=_from_text(row["updated_at"]),
        )


class ProjectMemoryService:
    """Project-aware memory CRUD and bounded retrieval."""

    def __init__(
        self,
        repository: MemoryRepository,
        project_service: ProjectService,
    ):
        self.repository = repository
        self.project_service = project_service

    @property
    def active_project(self) -> Project | None:
        return self.project_service.active_project

    def create_memory(
        self,
        kind: MemoryKind,
        title: str,
        content: str,
        *,
        confidence: float = 1.0,
        source_type: ProvenanceType = ProvenanceType.USER,
        source_ref: str | None = None,
        source_label: str = "Manual entry",
        excerpt: str | None = None,
    ) -> Memory:
        project = self._require_project()
        return self.repository.create_memory(
            project.id,
            kind,
            title,
            content,
            confidence=confidence,
            provenance=(
                (source_type, source_ref, source_label, excerpt),
            ),
        )

    def update_memory(
        self,
        memory_id: str,
        *,
        kind: MemoryKind,
        title: str,
        content: str,
        confidence: float,
        status: MemoryStatus,
    ) -> Memory:
        original = self._require_owned_memory(memory_id)
        updated = self.repository.update_memory(
            memory_id,
            kind=kind,
            title=title,
            content=content,
            confidence=confidence,
            status=status,
        )
        if (
            original.kind != updated.kind
            or original.title != updated.title
            or original.content != updated.content
            or original.confidence != updated.confidence
        ):
            self.repository.add_provenance(
                memory_id,
                ProvenanceType.USER,
                None,
                "Manual edit",
                updated.content,
            )
            updated = self.repository.get_memory(memory_id) or updated
        return updated

    def list_memories(
        self,
        *,
        status: MemoryStatus | None = None,
        kind: MemoryKind | None = None,
        search: str = "",
    ) -> list[Memory]:
        project = self._require_project()
        return self.repository.list_memories(
            project.id,
            status=status,
            kind=kind,
            search=search,
        )

    def delete_memory(self, memory_id: str) -> None:
        self._require_owned_memory(memory_id)
        self.repository.delete_memory(memory_id)

    def list_summaries(self) -> list[ConversationSummary]:
        project = self._require_project()
        return self.repository.list_summaries(project.id)

    def delete_summary(self, summary_id: str) -> None:
        project = self._require_project()
        summaries = self.repository.list_summaries(project.id, limit=1_000)
        if not any(summary.id == summary_id for summary in summaries):
            raise MemoryError(f"Unknown project summary: {summary_id}")
        self.repository.delete_summary(summary_id)

    def save_summary_draft(
        self,
        draft: ConversationSummaryDraft,
        selected_memory_indices: Iterable[int],
    ) -> tuple[ConversationSummary, tuple[Memory, ...]]:
        project = self._require_project()
        if draft.project_id != project.id:
            raise MemoryError("Summary draft belongs to a different project")
        selected_suggestions: list[SuggestedMemory] = []
        for index in dict.fromkeys(selected_memory_indices):
            if index < 0 or index >= len(draft.suggested_memories):
                raise MemoryError(f"Invalid suggested-memory index: {index}")
            selected_suggestions.append(draft.suggested_memories[index])
        return self.repository.save_summary_bundle(
            project.id,
            draft.session_id,
            draft.title,
            draft.content,
            draft.message_count,
            selected_suggestions,
        )

    def build_context(
        self,
        query: str,
        *,
        max_tokens: int = 800,
        limit: int = 12,
    ) -> MemoryContext:
        project = self.active_project
        if project is None or max_tokens <= 0:
            return MemoryContext("", 0, (), ())
        memories = self.repository.list_memories(
            project.id,
            status=MemoryStatus.ACTIVE,
            limit=500,
        )
        query_terms = {
            term.casefold()
            for term in re.findall(r"[\w'-]{3,}", query)
        }

        def score(memory: Memory) -> tuple[float, datetime]:
            title_terms = set(re.findall(r"[\w'-]{3,}", memory.title.casefold()))
            content_terms = set(
                re.findall(r"[\w'-]{3,}", memory.content.casefold())
            )
            overlap = len(query_terms & content_terms)
            title_overlap = len(query_terms & title_terms)
            relevance = (
                overlap
                + title_overlap * 2
                + memory.confidence
                + (0.25 if memory.last_used_at else 0.0)
            )
            return relevance, memory.updated_at

        ranked = sorted(memories, key=score, reverse=True)
        if query_terms:
            relevant = [memory for memory in ranked if score(memory)[0] > 1.0]
            ranked = relevant or ranked
        ranked = ranked[: max(0, limit)]

        summaries = self.repository.list_summaries(project.id, limit=1)
        sections: list[str] = []
        used_memories: list[str] = []
        used_summaries: list[str] = []
        used_tokens = 0
        truncated = False

        if summaries:
            summary = summaries[0]
            section = (
                f"Recent approved conversation summary — {summary.title}:\n"
                f"{summary.content}"
            )
            tokens = _estimate_tokens(section)
            if tokens <= max_tokens:
                sections.append(section)
                used_summaries.append(summary.id)
                used_tokens += tokens
            else:
                truncated = True

        for memory in ranked:
            provenance = (
                memory.provenance[0].source_label
                if memory.provenance
                else "Unknown source"
            )
            section = (
                f"[{memory.kind.display_name}] {memory.title}: "
                f"{memory.content}\nSource: {provenance}"
            )
            tokens = _estimate_tokens(section)
            if used_tokens + tokens > max_tokens:
                truncated = True
                continue
            sections.append(section)
            used_memories.append(memory.id)
            used_tokens += tokens

        self.repository.touch_memories(used_memories)
        text = "\n\n".join(sections)
        return MemoryContext(
            text=text,
            total_tokens=used_tokens,
            memory_ids=tuple(used_memories),
            summary_ids=tuple(used_summaries),
            truncated=truncated,
        )

    def _require_project(self) -> Project:
        project = self.active_project
        if project is None:
            raise MemoryError("Open a project to use persistent memory")
        return project

    def _require_owned_memory(self, memory_id: str) -> Memory:
        project = self._require_project()
        memory = self.repository.get_memory(memory_id)
        if memory is None or memory.project_id != project.id:
            raise MemoryError(f"Unknown project memory: {memory_id}")
        return memory


SUMMARY_SYSTEM_PROMPT = """
You create durable, factual memory for a creative-writing project.
Summarize only information supported by the supplied conversation. Separate
confirmed creative decisions from tentative ideas. Do not invent details.

Return strict JSON with this schema:
{
  "title": "short summary title",
  "summary": "concise session summary",
  "memories": [
    {
      "kind": "character|plot|world|style|decision|preference|other",
      "title": "short label",
      "content": "one durable fact or decision",
      "confidence": 0.8
    }
  ]
}

Include at most 12 suggested memories. Do not use Markdown fences.
"""


class ConversationSummarizer:
    """Generate an editable summary draft without persisting it."""

    MAX_INPUT_CHARACTERS = 60_000

    def __init__(self):
        self.prompt_composer = PromptComposer()

    def generate(
        self,
        *,
        project_id: str,
        session_id: str,
        messages: Iterable[dict[str, str]],
        complete: Callable[[list[dict[str, str]], str], str],
    ) -> ConversationSummaryDraft:
        conversation = [
            message
            for message in messages
            if message.get("role") in {"user", "assistant"}
            and str(message.get("content", "")).strip()
        ]
        if not conversation:
            raise MemoryError("The current chat has no messages to summarize")
        bounded_reversed: list[dict[str, str]] = []
        used_characters = 0
        for message in reversed(conversation[-80:]):
            content = str(message.get("content", ""))
            remaining = self.MAX_INPUT_CHARACTERS - used_characters
            if remaining <= 0:
                break
            if len(content) > remaining:
                marker = "[Earlier content truncated]\n"
                tail_length = max(0, remaining - len(marker))
                content = marker[:remaining] + (
                    content[-tail_length:] if tail_length else ""
                )
            bounded_reversed.append(
                {"role": message["role"], "content": content}
            )
            used_characters += len(content)
        bounded = list(reversed(bounded_reversed))
        prompt = self.prompt_composer.compose(
            (
                PromptLayer(
                    "Conversation Memory",
                    SUMMARY_SYSTEM_PROMPT,
                    PromptLayerOrder.CORE,
                ),
            )
        )
        response = complete(bounded, prompt)
        payload = self._parse_payload(response)
        suggestions: list[SuggestedMemory] = []
        raw_memories = payload.get("memories", [])
        if not isinstance(raw_memories, list):
            raise MemoryError("Summary memories must be a list")
        for raw_memory in raw_memories[:12]:
            if not isinstance(raw_memory, dict):
                continue
            try:
                kind = MemoryKind(str(raw_memory.get("kind", "other")))
            except ValueError:
                kind = MemoryKind.OTHER
            title = str(raw_memory.get("title", "")).strip()
            content = str(raw_memory.get("content", "")).strip()
            if not title or not content:
                continue
            try:
                confidence = float(raw_memory.get("confidence", 0.8))
            except (TypeError, ValueError):
                confidence = 0.8
            suggestions.append(
                SuggestedMemory(
                    kind=kind,
                    title=title,
                    content=content,
                    confidence=max(0.0, min(1.0, confidence)),
                )
            )

        title = str(payload.get("title", "")).strip()
        summary = str(payload.get("summary", "")).strip()
        if not title or not summary:
            raise MemoryError("The model returned an incomplete summary")
        return ConversationSummaryDraft(
            project_id=project_id,
            session_id=session_id,
            title=title,
            content=summary,
            message_count=len(conversation),
            suggested_memories=tuple(suggestions),
        )

    @staticmethod
    def _parse_payload(response: str) -> dict:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as error:
            raise MemoryError(f"Unable to parse conversation summary: {error}") from error
        if not isinstance(payload, dict):
            raise MemoryError("Conversation summary must be a JSON object")
        return payload
