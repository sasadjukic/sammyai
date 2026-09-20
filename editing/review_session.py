"""Deterministic review decisions against immutable file snapshots (no Qt)."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from enum import Enum
from types import MappingProxyType
from uuid import uuid4

from editing.change_sets import FileChange, FileChangeKind, content_hash


class HunkState(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ReviewHunk:
    id: str
    start: int
    end: int
    original_start_line: int
    proposed_start_line: int
    removed: str
    inserted: str


def structured_hunks(change: FileChange) -> tuple[ReviewHunk, ...]:
    """Keep line endings, EOF and character offsets independent of display text."""
    before, after = change.before_content or "", change.after_content or ""
    old_lines, new_lines = before.splitlines(keepends=True), after.splitlines(keepends=True)
    offsets = [0]
    for line in old_lines:
        offsets.append(offsets[-1] + len(line))
    if change.kind != FileChangeKind.UPDATE:
        # Creating/deleting a file is indivisible, including an empty file.
        opcodes = [(change.kind.value, 0, len(old_lines), 0, len(new_lines))]
    else:
        # Trim shared ends before matching. Enable difflib's repetitive-line
        # heuristic for large inputs to avoid quadratic UI stalls. Grouping may
        # be coarser in a long repeated passage; snapshot synthesis stays exact.
        prefix = 0
        limit = min(len(old_lines), len(new_lines))
        while prefix < limit and old_lines[prefix] == new_lines[prefix]:
            prefix += 1
        suffix = 0
        while suffix < limit - prefix and old_lines[-suffix - 1] == new_lines[-suffix - 1]:
            suffix += 1
        old_end, new_end = len(old_lines) - suffix, len(new_lines) - suffix
        matcher = SequenceMatcher(
            None, old_lines[prefix:old_end], new_lines[prefix:new_end],
            autojunk=max(len(old_lines), len(new_lines)) > 4000,
        )
        opcodes = [(tag, i + prefix, j + prefix, k + prefix, l + prefix)
                   for tag, i, j, k, l in matcher.get_opcodes()]
    hunks = []
    for tag, i, j, k, l in opcodes:
        if tag == "equal":
            continue
        identity = f"{change.relative_path}\0{change.before_hash}\0{change.after_hash}\0{tag}:{i}:{j}:{k}:{l}"
        hunks.append(ReviewHunk(
            content_hash(identity), offsets[i], offsets[j], i + 1, k + 1,
            "".join(old_lines[i:j]), "".join(new_lines[k:l]),
        ))
    return tuple(hunks)


@dataclass(frozen=True)
class ReviewSession:
    source_change_set_id: str
    target_document_id: str
    normalized_path: str | None
    change: FileChange
    originating_agent_id: str | None = None
    originating_session_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    hunks: tuple[ReviewHunk, ...] = field(init=False)
    _states: dict[str, HunkState] = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        hunks = structured_hunks(self.change)
        object.__setattr__(self, "hunks", hunks)
        object.__setattr__(self, "_states", {h.id: HunkState.PENDING for h in hunks})

    @property
    def states(self):
        return MappingProxyType(self._states)

    @property
    def pending_count(self) -> int:
        return sum(state == HunkState.PENDING for state in self._states.values())

    def decide(self, hunk_id: str, state: HunkState) -> None:
        if hunk_id not in self._states:
            raise KeyError(hunk_id)
        self._states[hunk_id] = HunkState(state)

    def decide_all(self, state: HunkState) -> None:
        for hunk in self.hunks:
            self.decide(hunk.id, state)

    def final_content(self) -> str | None:
        if self.pending_count:
            raise ValueError("Review still has pending hunks")
        if self.change.kind != FileChangeKind.UPDATE:
            return (self.change.after_content if self._states[self.hunks[0].id] == HunkState.ACCEPTED
                    else self.change.before_content)
        original = self.change.before_content
        parts, position = [], 0
        for hunk in self.hunks:
            parts.append(original[position:hunk.start])
            parts.append(hunk.inserted if self._states[hunk.id] == HunkState.ACCEPTED else hunk.removed)
            position = hunk.end
        parts.append(original[position:])
        return "".join(parts)

    def final_change(self) -> FileChange | None:
        content = self.final_content()
        if content == self.change.before_content:
            return None
        return FileChange(
            self.change.relative_path, self.change.kind,
            self.change.before_content, content, self.change.before_hash,
            content_hash(content) if content is not None else None,
        )
