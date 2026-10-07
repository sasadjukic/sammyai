"""Plain-text edit transport. File prose never needs JSON or XML escaping.

Control lines are reserved; incomplete or ambiguous framing is rejected. The
parser constructs ordinary Python data for the existing validation/review path.
It has no model, filesystem, or file-application capabilities.
"""
from __future__ import annotations

import re


PROMPT_VERSION = "agent-prompts-v2-text-edits"
OPEN = "<sammyai_edits>"
CLOSE = "</sammyai_edits>"
SEARCH = "<<<SAMMYAI_SEARCH>>>"
REPLACEMENT = "<<<SAMMYAI_REPLACEMENT>>>"
CONTENT = "<<<SAMMYAI_CONTENT>>>"
ANCHOR = "<<<SAMMYAI_ANCHOR>>>"
END = "<<<SAMMYAI_END>>>"
CONTROL_LINES = {OPEN, CLOSE, SEARCH, REPLACEMENT, CONTENT, ANCHOR, END}
OPERATIONS = frozenset({"replace", "write", "append", "insert_before", "insert_after", "delete"})
TEXT_OPEN_PATTERN = re.compile(r"^[ \t]*<sammyai_edits>[ \t]*\r?$", re.MULTILINE)
TEXT_MARKER_PATTERN = re.compile(r"<\s*/?\s*sammyai_edits\b", re.IGNORECASE)
PROPOSAL_MARKER_PATTERN = re.compile(r"<\s*/?\s*sammyai_(?:changes|edits)\b", re.IGNORECASE)


class ProposalFormatError(ValueError):
    """Structural errors never include the potentially private offending text."""


def _remove_line_ending(text: str) -> str:
    if text.endswith("\r\n"):
        return text[:-2]
    if text.endswith("\n"):
        return text[:-1]
    return text


class _Reader:
    def __init__(self, text: str):
        # Only LF/CRLF frame control lines. Unicode paragraph separators remain
        # literal content, rather than silently creating new control lines.
        self.lines = re.findall(r"[^\n]*\n|[^\n]+$", text)
        self.index = 0

    def fail(self, message: str):
        raise ProposalFormatError(f"Invalid text edit directive at line {self.index + 1}: {message}")

    def peek(self) -> str | None:
        while self.index < len(self.lines):
            value = _remove_line_ending(self.lines[self.index]).strip()
            if value:
                return value
            self.index += 1
        return None

    def field(self, name: str) -> str:
        line = self.peek()
        prefix = name + ":"
        if line is None or not line.startswith(prefix) or not line[len(prefix):].strip():
            self.fail(f"expected a nonempty {name}: line")
        self.index += 1
        return line[len(prefix):].strip()

    def block(self, opening: str, closing: str) -> str:
        if self.peek() != opening:
            self.fail(f"expected {opening}")
        self.index += 1
        start = self.index
        while self.index < len(self.lines):
            control = _remove_line_ending(self.lines[self.index]).strip()
            if control == closing:
                text = "".join(self.lines[start:self.index])
                self.index += 1
                # Exactly one newline separates literal text from the closing
                # marker. Extra blank lines, spaces and all escapes stay intact.
                return _remove_line_ending(text)
            if control in CONTROL_LINES or control.startswith("<<<SAMMYAI_"):
                self.fail(f"expected {closing}; found an incomplete or conflicting block")
            self.index += 1
        self.fail(f"missing {closing}")


def extract_text_proposal(response: str) -> tuple[str, dict]:
    opening = TEXT_OPEN_PATTERN.search(response)
    if opening is None:
        raise ProposalFormatError("Incomplete or malformed text edit directive envelope")
    prefix = response[:opening.start()]
    if PROPOSAL_MARKER_PATTERN.search(prefix):
        raise ProposalFormatError("Agent returned multiple or mixed change directives")
    # Include the newline after the opening tag as harmless framing whitespace.
    reader = _Reader(response[opening.end():])
    summary = reader.field("summary")
    files = []
    while reader.peek() != CLOSE:
        path = reader.field("file")
        operation = reader.field("operation")
        item = {"path": path, "operation": operation}
        if operation == "replace":
            replacements = []
            while reader.peek() == SEARCH:
                old_text = reader.block(SEARCH, REPLACEMENT)
                # The replacement marker closes SEARCH and opens the new text.
                reader.index -= 1
                new_text = reader.block(REPLACEMENT, END)
                replacements.append({"old_text": old_text, "new_text": new_text})
            if not replacements:
                reader.fail("replace requires at least one search/replacement pair")
            item["replacements"] = replacements
        elif operation in {"write", "append", "insert_before", "insert_after"}:
            if operation.startswith("insert_"):
                anchor = reader.block(ANCHOR, CONTENT)
                reader.index -= 1
                item["anchor"] = anchor
            item["content"] = reader.block(CONTENT, END)
        elif operation != "delete":
            reader.fail("unsupported file operation")
        files.append(item)
    if not files:
        reader.fail("at least one file operation is required")
    reader.index += 1
    suffix = "".join(reader.lines[reader.index:])
    if PROPOSAL_MARKER_PATTERN.search(suffix) or any(
        _remove_line_ending(line).strip() in CONTROL_LINES for line in reader.lines[reader.index:]
    ):
        raise ProposalFormatError("Agent returned multiple or mixed change directives")
    return (prefix + suffix).strip(), {"summary": summary, "files": files}


TEXT_OUTPUT_PROMPT = """
Normal user-facing prose belongs outside the directive. Only when the user
explicitly requests file changes, append one <sammyai_edits> directive.
Use the plain-text format below, even if earlier conversation used JSON.
SammyAI constructs the structured data. Do not JSON-escape writing, quotes or
backslashes, encode newlines as literal \\n, or wrap the directive in code fences.

Prefer targeted replacements for revisions to existing passages. Include the
exact old passage and its replacement, copying enough context for a unique match.
For several changes to one file, repeat SEARCH/REPLACEMENT/END blocks under ONE
file/operation pair. All searches refer to the original supplied file, not the
result of another replacement. Do not use guessed offsets or line numbers.

<sammyai_edits>
summary: Revise two passages
file: chapter.md
operation: replace
<<<SAMMYAI_SEARCH>>>
Exact existing first passage.
<<<SAMMYAI_REPLACEMENT>>>
Revised first passage with "ordinary quotes".
<<<SAMMYAI_END>>>
<<<SAMMYAI_SEARCH>>>
Exact existing second passage.
<<<SAMMYAI_REPLACEMENT>>>
Revised second passage.
<<<SAMMYAI_END>>>
</sammyai_edits>

For a new file or an explicitly requested whole-file rewrite:
<sammyai_edits>
summary: Create the requested outline
file: outline.md
operation: write
<<<SAMMYAI_CONTENT>>>
# Outline
Write the complete file here using ordinary text and real newlines.

<<<SAMMYAI_END>>>
</sammyai_edits>

Allowed operations and source requirements:
- replace: exact, unique, non-overlapping old passages, each fully visible in
  current explicit @file context. Return only those passages and their replacements.
  An empty replacement removes the matched passage. Never search for empty text.
- write: complete resulting file. Existing files require COMPLETE explicit @file
  context. Use this for full rewrites, not small changes to partly supplied files.
- append: same CONTENT block as write, containing ONLY new ending material.
  Requires explicit @file context that includes the file ending.
- insert_before / insert_after: an ANCHOR block followed by a CONTENT block:
  <<<SAMMYAI_ANCHOR>>>
  Exact unique complete source line
  <<<SAMMYAI_CONTENT>>>
  Only the new material
  <<<SAMMYAI_END>>>
  Requires that anchor in current explicit @file context. Insertion is before or
  after that LINE. To add after a scene body, insert_before the next scene heading.
- delete: only file: and operation: delete, no text blocks. Requires COMPLETE
  explicit @file context and an explicit user deletion request.

Repeat file:/operation: for different files inside the single envelope. List
each file once; combine revisions to that file as replacement pairs. Use only
explicitly requested project-relative .md or .txt paths. Each summary:, file:
and operation: value occupies one line. Keep marker lines exactly as shown.
Inside blocks, whitespace is literal. One newline before the next marker is
framing; to include a final newline in content, leave an extra blank line before
that marker. Keep intended paragraph spacing. Reserved marker lines cannot occur
as literal content; explain the conflict instead of emitting ambiguous blocks.

Never invent omitted source text. Ask for more context if a target is missing
or ambiguous. Check headings for duplicate additions. Reading a file is not
permission to change unrelated parts. Never claim edits are applied: SammyAI
will validate them and show a diff for the user's approval.
"""
