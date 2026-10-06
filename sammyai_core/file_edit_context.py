"""Request-local file evidence, independently configurable from model workflows.

Full source snapshots stay local. Models receive only the rendered context and
return additions; the application resolves their insertion points in that snapshot.
"""

from dataclasses import dataclass
import re

from editing.change_sets import TextEdit, content_hash


def estimate_tokens(text: str) -> int:
    """Provider-neutral estimate shared by context and addition budgets."""
    return (len(text) + 3) // 4


@dataclass(frozen=True)
class AdditionPolicy:
    """Limit newly generated additions, never the unchanged destination text."""

    max_added_tokens: int = 4_000
    max_files: int = 20

    def __post_init__(self):
        if self.max_added_tokens <= 0 or self.max_files <= 0:
            raise ValueError("Addition policy limits must be positive")


@dataclass(frozen=True)
class FileContextPolicy:
    """Bounded selection defaults; callers can tune them for future models."""

    excerpt_chars: int = 2_400
    max_outline_entries: int = 80
    max_query_windows: int = 3
    max_snapshot_bytes: int = 10 * 1024 * 1024

    def __post_init__(self):
        if min(self.excerpt_chars, self.max_outline_entries, self.max_query_windows, self.max_snapshot_bytes) <= 0:
            raise ValueError("File context policy limits must be positive")


@dataclass(frozen=True)
class FileEditSnapshot:
    project_id: str
    relative_path: str
    content: str
    visible_ranges: tuple[tuple[int, int], ...]
    complete: bool = False

    @property
    def source_hash(self) -> str:
        return content_hash(self.content)

    def addition(self, operation: str, content: str, anchor: str | None = None) -> TextEdit:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("An addition requires nonempty new text")
        if operation == "append":
            if anchor is not None:
                raise ValueError("Append does not accept an anchor")
            if not self.complete and not any(end == len(self.content) for _, end in self.visible_ranges):
                raise ValueError("The file ending was not supplied; reference the file again before appending")
            offset = len(self.content)
        elif operation in {"insert_before", "insert_after"}:
            if not isinstance(anchor, str) or not anchor.strip() or "\n" in anchor or "\r" in anchor:
                raise ValueError("Insertion requires an exact, nonempty source line as its anchor")
            matches = [(start, end) for start, end, line in source_lines(self.content) if line == anchor]
            if len(matches) != 1:
                raise ValueError("Insertion anchor is missing or ambiguous; choose a unique complete line")
            start, end = matches[0]
            if not self.complete and not any(left <= start and start + len(anchor) <= right for left, right in self.visible_ranges):
                raise ValueError("Insertion anchor was not supplied in file context; name or quote the target in your request")
            offset = start if operation == "insert_before" else end
        else:
            raise ValueError(f"Unsupported addition operation: {operation}")

        self._check_duplicate_sections(content, offset)
        # Normalize only NEW text. Every byte of the existing UTF-8 source remains
        # in its original position on either side of the insertion.
        newline = "\r\n" if "\r\n" in self.content else "\r" if "\r" in self.content and "\n" not in self.content else "\n"
        addition = content.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)
        if offset and self.content[offset - 1] not in "\r\n" and not addition.startswith(("\r", "\n")):
            addition = newline + addition
        if offset < len(self.content) and not addition.endswith(("\r", "\n")):
            addition += newline
        return TextEdit(offset, offset, addition, expected_text="")

    def _check_duplicate_sections(self, addition: str, offset: int) -> None:
        headings = [(heading_level(line), line) for _, _, line in source_lines(addition) if heading_level(line) is not None]
        if not headings:
            return
        top = min(level for level, _ in headings)
        existing_headings = [(start, heading_level(line), line) for start, _, line in source_lines(self.content) if heading_level(line) is not None]
        # A numbered scene may legitimately recur under a different act/chapter.
        # Identify parents by their source positions, not potentially repeated titles.
        parents = []
        for start, level, _line in existing_headings:
            if start >= offset:
                break
            while parents and parents[-1][0] >= level:
                parents.pop()
            parents.append((level, start))
        destination_parent = tuple(start for level, start in parents if level < top)
        parents = []
        existing = set()
        for start, level, line in existing_headings:
            while parents and parents[-1][0] >= level:
                parents.pop()
            if level == top and tuple(position for parent_level, position in parents if parent_level < top) == destination_parent:
                existing.add(section_key(line))
            parents.append((level, start))
        seen = set()
        for level, line in headings:
            if level != top:
                continue
            key = section_key(line)
            if key in existing or key in seen:
                raise ValueError(f"Section already exists or is repeated: {line}. Request an edit instead of adding a duplicate.")
            seen.add(key)


def source_lines(text: str):
    offset = 0
    for line in text.splitlines(keepends=True):
        yield offset, offset + len(line), line.rstrip("\r\n")
        offset += len(line)


def heading_level(line: str) -> int | None:
    markdown = re.match(r"^ {0,3}(#{1,6})\s+\S", line)
    if markdown:
        return len(markdown[1])
    if re.match(r"^(?:scene|chapter|act)\s+(?:\d+|[IVXLCDM]+)\b", line, re.IGNORECASE):
        return 0
    return None


def section_key(line: str) -> str:
    title = line.strip().strip("# ").casefold()
    numbered = re.match(r"^(scene|chapter|act)\s+(\d+|[ivxlcdm]+)\b", title)
    return " ".join(numbered.groups()) if numbered else title


def select_file_context(project_id: str, path: str, content: str, query: str, max_tokens: int,
                        policy: FileContextPolicy) -> tuple[str, FileEditSnapshot | None, bool]:
    """Return budgeted context and exactly the source ranges it exposes.

    Headings form an outline, query matches expose insertion anchors, and the
    tail supports append. No truncated metadata or unseen ranges grant edits.
    """
    header = f"Explicit project file requested by the user: {path}\n\n"
    full = header + content
    if estimate_tokens(full) <= max_tokens:
        return full, FileEditSnapshot(project_id, path, content, ((0, len(content)),), True), False
    partial_header = header + (
        "[Partial file context: append or insert at a supplied unique line only. "
        "Whole-file replacement/deletion is not authorized. Excerpts may omit story context.]\n"
    )
    # Tiny budgets cannot carry a useful operation contract: retain read-only
    # truncated context rather than granting an operation from incomplete metadata.
    suffix = "\n\n[Context truncated to fit the configured budget; no file edits authorized.]"
    if max_tokens * 4 < len(partial_header) + 160:
        available = max_tokens * 4 - len(suffix)
        return (full[:available] + suffix if available > 0 else ""), None, True

    rendered = partial_header
    ranges: list[tuple[int, int]] = []
    remaining_chars = max_tokens * 4 - len(rendered)
    excerpt_size = min(policy.excerpt_chars, max(80, remaining_chars // 4))
    tail_start = max(0, len(content) - excerpt_size)
    # Start at a complete line when possible; long individual lines remain
    # contextual excerpts and cannot masquerade as complete insertion anchors.
    next_line = content.find("\n", tail_start)
    if tail_start and next_line != -1 and next_line + 1 <= len(content) - excerpt_size // 2:
        tail_start = next_line + 1

    def add(label: str, start: int, end: int) -> bool:
        nonlocal rendered
        if start == end or any(left <= start and end <= right for left, right in ranges):
            return False
        section = f"\n--- {label} ---\n{content[start:end]}\n"
        if estimate_tokens(rendered + section) > max_tokens:
            return False
        rendered += section
        ranges.append((start, end))
        return True

    add("File ending (append follows this text)", tail_start, len(content))
    lines = list(source_lines(content))
    # Exclude @paths from search terms. Match numbered scenes as whole phrases,
    # so Scene 2 does not select Scene 20 merely because it is a prefix.
    search = re.sub(r"@(?:\"[^\"]+\"|'[^']+'|\S+)", "", query).casefold()
    phrases = re.findall(r"(?:scene|chapter|act)\s+(?:\d+|[ivxlcdm]+)\b", search)
    words = {word for word in re.findall(r"\w{4,}", search) if word not in {
        "append", "insert", "before", "after", "breakdown", "please", "file", "scene", "chapter", "write", "could", "would", "this", "that",
    }}
    def score(line: str) -> int:
        folded = line.casefold()
        return sum(20 for phrase in phrases if re.search(r"\b" + re.escape(phrase) + r"\b", folded)) + len(words.intersection(re.findall(r"\w+", folded)))

    ranked = sorted(lines, key=lambda item: (-score(item[2]), item[0]))
    for start, end, line in [item for item in ranked if score(item[2]) > 0][:policy.max_query_windows]:
        add("Relevant excerpt (incomplete section)", start, min(len(content), max(end, start + excerpt_size)))

    outline = [item for item in lines if heading_level(item[2]) is not None]
    # Rank requested headings first, then present remaining outline entries in
    # source order. Only entries that actually fit become visible anchor evidence.
    outline.sort(key=lambda item: (-score(item[2]), item[0]))
    for start, end, _line in outline[:policy.max_outline_entries]:
        add("Heading (body may be omitted)", start, end)
    add("File beginning", 0, min(len(content), excerpt_size))
    return rendered, FileEditSnapshot(project_id, path, content, tuple(ranges)), True
