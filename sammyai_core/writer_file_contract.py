"""Request-local Writer destinations; never grants permission to edit a file.

Recognize explicit file commands in the current request, not in conversation or
retrieved prose. Less specific wording can be refined by a validated draft
proposal. Normal source, project, path and review checks remain authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import PurePosixPath
import re

from .file_edit_context import FileEditSnapshot


PATH = re.compile(r'@?(?:"[^"\n]+\.(?:md|txt)"|`[^`\n]+\.(?:md|txt)`|[\w./\\-]+\.(?:md|txt))', re.I)
ACTION = re.compile(r'\b(append|add|insert|write|rewrite|create|save|store|stored|saved|put|replace|revise|edit|update|delete)\b', re.I)
NEGATION = re.compile(r"\b(?:do not|don't|never|without|cannot|can't)\b", re.I)
REFERENCE = re.compile(r'\b(?:using|from|about|inspired by|based on|outlined in|described in|specified in|according to)\s*$', re.I)


def path_key(path: str) -> str:
    return os.path.normcase(PurePosixPath(path.replace("\\", "/")).as_posix())


def _operations(text: str) -> tuple[str, ...]:
    actions = list(ACTION.finditer(text))
    if not actions or NEGATION.search(text) or REFERENCE.search(text):
        return ()
    action = actions[-1].group().lower()
    tail = text[actions[-1].end():]
    if action in {"append", "add", "insert"}:
        if re.search(r'\bbefore\b', tail, re.I):
            return ("insert_before",)
        if re.search(r'\bafter\b', tail, re.I):
            return ("insert_after",)
        return ("append",) if action != "insert" else ("append", "insert_before", "insert_after")
    if action in {"write", "rewrite", "create"}:
        return ("write",)
    if action in {"delete", "replace"}:
        return (action,)
    if action in {"revise", "edit", "update"}:
        return ("replace", "write")
    return ("append", "write", "replace", "insert_before", "insert_after")


@dataclass(frozen=True)
class WriterFileTarget:
    path: str
    operations: tuple[str, ...]


@dataclass(frozen=True)
class WriterFileContract:
    targets: tuple[WriterFileTarget, ...] = ()

    @classmethod
    def from_request(cls, request: str, snapshots: tuple[FileEditSnapshot, ...]) -> WriterFileContract:
        targets = {}
        # A basename may resolve to a project-relative path only when the
        # request's captured evidence has one unambiguous match.
        def resolve(path: str) -> str:
            path = path.lstrip("@").strip('"`')
            exact = [s.relative_path for s in snapshots if path_key(s.relative_path) == path_key(path)]
            matches = exact or [s.relative_path for s in snapshots if path_key(PurePosixPath(s.relative_path).name) == path_key(path)]
            return matches[0] if len(matches) == 1 else path

        # Ignore fenced examples; this intentionally is not a general natural
        # language authorization parser. Unrecognized requests keep the original
        # prompt and can acquire a contract from a valid draft proposal.
        request = re.sub(r'```.*?```', '', request, flags=re.S)
        last_target = None
        for clause in re.split(r'[.!?;]\s+|\n', request):
            if re.match(r'\s*(?:explain|describe|discuss|how|why|what)\b', clause, re.I):
                continue
            previous_end = 0
            clause_operations = ()
            for match in PATH.finditer(clause):
                prefix = clause[previous_end:match.start()]
                operations = _operations(prefix)
                if not operations and re.fullmatch(r'\s*(?:(?:in|to)\s+)?', prefix, re.I):
                    following = clause[match.end():]
                    if re.match(r'\s*[:,]\s*(?:please\s+)?' + ACTION.pattern, following, re.I):
                        operations = _operations(following)
                if not operations and re.fullmatch(r'\s*(?:and|,|&)\s*(?:(?:to|in)\s*)?', prefix, re.I):
                    operations = clause_operations
                if operations:
                    path = resolve(match.group())
                    last_target = path_key(path)
                    targets[last_target] = WriterFileTarget(path, operations)
                else:
                    last_target = None
                clause_operations = operations
                previous_end = match.end()
            # "Store drafts in @draft.md ... append them to that document."
            tail = clause[previous_end:]
            if last_target and re.search(r'\b(?:(?:that|this|the same) (?:file|document)|(?:to|into|in) it)\b', tail, re.I):
                operations = _operations(tail)
                if operations:
                    old = targets[last_target]
                    targets[last_target] = WriterFileTarget(old.path, operations)
        return cls(tuple(targets.values()))

    def validate(self, directive: dict | None) -> None:
        if not self.targets:
            return
        if directive is None:
            raise ValueError("Writer did not return a file-change proposal for the requested destination. Regenerate the request.")
        files = directive.get("files")
        if not isinstance(files, list) or any(not isinstance(item, dict) or not isinstance(item.get("path"), str) for item in files):
            raise ValueError("Writer returned an invalid file-change proposal. Regenerate the request.")
        expected = {path_key(t.path): t for t in self.targets}
        actual = {path_key(item["path"]) for item in files}
        if actual != set(expected):
            raise ValueError("Writer changed or omitted a requested file target. Regenerate the request with the original destinations.")
        for item in files:
            target = expected[path_key(item["path"])]
            if item.get("operation") not in target.operations:
                raise ValueError(f"Writer must preserve the requested operation for {target.path}: {' or '.join(target.operations)}. Regenerate the proposal.")

    def preserve_draft(self, directive: dict) -> WriterFileContract:
        """Call only after normal source/policy validation of the draft succeeds."""
        self.validate(directive)
        return WriterFileContract(tuple(
            WriterFileTarget(item["path"], (item["operation"],)) for item in directive["files"]
        ))

    def prompt(self) -> str:
        destinations = "\n".join(f"- {t.path}: {' or '.join(t.operations)}" for t in self.targets)
        return (
            "Writer file request (unchanged for this run):\n"
            + (destinations or "Follow the original request; reading a reference is not a request to change it.")
            + "\nDrafts and proposals have not been saved. The supplied file snapshots remain the only existing file content. "
            "An empty file is a valid append destination: append the complete new material at position zero. "
            "Keep the requested destinations and operations through drafting, evaluation and revision. "
            "The evaluator checks these requirements but must not emit file directives. "
            "During revision, revise the unsaved draft in memory, then return a complete final proposal against the ORIGINAL file. "
            "For append/insert, return ALL revised new material, even if the evaluator asks for only a small correction. "
            "Never search the destination for text that exists only in an unsaved draft. "
            "Do not substitute an acknowledgement or revision commentary for the requested deliverable. "
            "If a valid file proposal cannot be produced, explain the failure; never claim the file was changed."
        )
