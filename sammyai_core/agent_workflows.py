"""Agent definitions and orchestrated creative-writing workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import logging
import os
from pathlib import PurePosixPath
import re
from typing import Callable, Iterable
from uuid import uuid4

from editing.change_sets import (
    ChangeSet,
    ChangeSetPreview,
    FileChangeKind,
    FileChangeRequest,
)
from llm.prompt_layers import (
    PromptComposer,
    PromptLayer,
    PromptLayerOrder,
)
from llm.system_prompt import SYSTEM_PROMPT

from .file_tools import FileToolError, SafeFileTools
from .file_edit_context import AdditionPolicy, FileEditSnapshot, estimate_tokens


logger = logging.getLogger(__name__)

CHANGE_DIRECTIVE_PATTERN = re.compile(
    r"<sammyai_changes>\s*(\{.*?\})\s*</sammyai_changes>",
    re.DOTALL,
)


def _file_key(path: str) -> str:
    return os.path.normcase(PurePosixPath(path.replace("\\", "/")).as_posix())


class AgentType(str, Enum):
    GENERAL = "general"
    BRAINSTORMER = "brainstormer"
    WRITER = "writer"
    EDITOR = "editor"
    CRITIC = "critic"

    @property
    def display_name(self) -> str:
        return {
            AgentType.GENERAL: "Assistant",
            AgentType.BRAINSTORMER: "Brainstormer",
            AgentType.WRITER: "Writer",
            AgentType.EDITOR: "Editor",
            AgentType.CRITIC: "Critic",
        }[self]


@dataclass(frozen=True)
class AgentDefinition:
    type: AgentType
    role_prompt: str
    workflow_prompt: str
    can_propose_file_changes: bool


@dataclass(frozen=True)
class AgentRunEvent:
    stage: str
    message: str


@dataclass(frozen=True)
class AgentRunResult:
    run_id: str
    agent_type: AgentType
    response: str
    events: tuple[AgentRunEvent, ...]
    model_calls: int
    change_set: ChangeSet | None = None
    change_preview: ChangeSetPreview | None = None
    notices: tuple[str, ...] = ()
    originating_session_id: str | None = None


LLMCompletion = Callable[[list[dict[str, str]], str], str]
AgentEventCallback = Callable[[AgentRunEvent], None]


AGENT_DEFINITIONS = {
    AgentType.GENERAL: AgentDefinition(
        type=AgentType.GENERAL,
        role_prompt=(
            "Act as SammyAI's general creative-writing collaborator. Adapt to "
            "the user's request while preserving their authorship and intent."
        ),
        workflow_prompt=(
            "Respond directly. Use project context when relevant. Do not propose "
            "file writes; the specialized agents handle file-changing workflows."
        ),
        can_propose_file_changes=False,
    ),
    AgentType.BRAINSTORMER: AgentDefinition(
        type=AgentType.BRAINSTORMER,
        role_prompt=(
            "You are the Brainstormer. Generate distinct, usable possibilities "
            "for plots, characters, arcs, settings, themes, and scene problems. "
            "Treat the user's creative decisions as constraints."
        ),
        workflow_prompt=(
            "Identify the creative target, then offer meaningfully different "
            "options with tradeoffs. Recommend a direction only when useful. "
            "Do not silently write project files. If the user explicitly asks "
            "you to create or update a .md or .txt file, propose that change "
            "through the structured change directive."
        ),
        can_propose_file_changes=True,
    ),
    AgentType.WRITER: AgentDefinition(
        type=AgentType.WRITER,
        role_prompt=(
            "You are the Writer. Produce polished prose, screenplay, teleplay, "
            "essay, or narrative material in the project's established form, "
            "voice, tense, point of view, and continuity."
        ),
        workflow_prompt=(
            "Draft the requested material, evaluate it against the user's brief "
            "and project context, then revise weaknesses before returning the "
            "final version. File writes must be proposed as structured changes "
            "and never described as already applied."
        ),
        can_propose_file_changes=True,
    ),
    AgentType.EDITOR: AgentDefinition(
        type=AgentType.EDITOR,
        role_prompt=(
            "You are the Editor. Improve clarity, grammar, continuity, rhythm, "
            "pacing, and consistency while preserving the author's meaning and "
            "voice. Do not rewrite merely to impose personal style."
        ),
        workflow_prompt=(
            "Diagnose the text before editing. Make the smallest changes that "
            "solve the requested problem. Explain material editorial decisions. "
            "When asked to change a project file, propose the smallest supported "
            "operation through a structured change directive for diff review. "
            "For additions, return only the new material."
        ),
        can_propose_file_changes=True,
    ),
    AgentType.CRITIC: AgentDefinition(
        type=AgentType.CRITIC,
        role_prompt=(
            "You are the Critic. Independently assess narrative effectiveness "
            "from a demanding reader's perspective. Be specific, candid, and "
            "constructive rather than agreeable."
        ),
        workflow_prompt=(
            "Evaluate strengths, weaknesses, reader impact, plausibility, "
            "continuity, pacing, character motivation, and thematic coherence. "
            "Prioritize findings by impact and cite the supplied text. You are "
            "read-only and must never propose or apply file changes."
        ),
        can_propose_file_changes=False,
    ),
}

CHANGE_OUTPUT_PROMPT = r"""
Normal prose belongs outside the directive.

Only when the user explicitly requests a project file creation, update, or
deletion, append exactly one directive in this form:

<sammyai_changes>
{"summary":"Short description","files":[
  {"path":"project-relative.md","operation":"write","content":"complete UTF-8 file content"}
]}
</sammyai_changes>

Use only explicitly requested project-relative .md or .txt paths.
Allowed operations:
- "write": complete resulting file content. Create a file, or replace an
  existing file ONLY when its COMPLETE contents were supplied as explicit @file
  context. Never use write to add a small section to a partially supplied file.
- "delete": remove a file ONLY with complete explicit @file context.
- "append": content contains ONLY the new material to add at the file ending.
  Requires explicit @file context including the ending, not the entire file.
- "insert_before" / "insert_after": content contains ONLY new material;
  "anchor" is an exact, unique, complete source line shown in the supplied file
  context. Insertion is immediately before/after that LINE. To add a scene after
  another scene's body, insert_before the NEXT scene heading, or append at EOF.
  Do not invent line numbers, anchors, or omitted source text. If the location is
  unclear, ask the user to name or quote a unique target line.

Example addition:
<sammyai_changes>
{"summary":"Add Scene 20","files":[
  {"path":"scene_breakdown.md","operation":"append","content":"\n\n## Scene 20\nNew breakdown.\n"}
]}
</sammyai_changes>

Keep existing material out of addition content. Include intentional spacing.
Check supplied headings for duplicate scenes/sections. Headings and excerpts
may omit relevant story context: ask for more context when continuity requires
it. Reading a file is not permission to change unrelated parts of it.
Never claim the change has been applied; SammyAI will show a diff for approval.
"""

READ_ONLY_OUTPUT_PROMPT = """
Return only the user-facing response. Do not emit tool calls, XML directives,
JSON control data, or claims that project files were changed.
"""

EVALUATOR_PROMPT = """
Act as a strict evaluator for a creative-writing draft. Compare the draft with
the original request and supplied project context. Identify concrete failures
in instruction-following, continuity, voice, structure, pacing, and prose.
Return a concise revision brief. Do not rewrite the draft and do not emit file
change directives.
"""

REVISION_PROMPT = """
Revise the draft using the evaluator's brief. Preserve strong material, correct
the identified problems, and satisfy the original request. Return the final
user-facing response. If the original request explicitly asked for a file
change, keep its operation and target scope in the structured change directive.
Append/insert directives contain ONLY the final new material, never a complete
replacement file. The same supplied file context applies to every stage.
"""


class AgentWorkflowService:
    """Execute selected agents and convert file proposals into change sets."""

    def __init__(self, file_tools: SafeFileTools | None, *, addition_policy: AdditionPolicy | None = None):
        self.file_tools = file_tools
        self.addition_policy = addition_policy or AdditionPolicy()
        self.prompt_composer = PromptComposer()

    @staticmethod
    def available_agents() -> tuple[AgentType, ...]:
        return tuple(AgentType)

    def run(
        self,
        agent_type: AgentType | str,
        *,
        user_request: str,
        messages: list[dict[str, str]],
        complete: LLMCompletion,
        authorized_files: Iterable[str] = (),
        file_snapshots: Iterable[FileEditSnapshot] = (),
        addition_policy: AdditionPolicy | None = None,
        on_event: AgentEventCallback | None = None,
    ) -> AgentRunResult:
        selected = AgentType(agent_type)
        definition = AGENT_DEFINITIONS[selected]
        # Immutable request evidence survives arbitrary draft/review stages.
        # Legacy trusted callers may still authorize complete files by name;
        # capture their sources BEFORE invoking the model, never afterward.
        snapshots = tuple(file_snapshots)
        if not snapshots and self.file_tools is not None:
            project = self.file_tools.project_service.active_project
            if project is not None:
                snapshots = tuple(
                    FileEditSnapshot(project.id, path, self.file_tools.read_text(path), (), True)
                    for path in authorized_files
                )
        policy = addition_policy or self.addition_policy
        messages = [dict(message) for message in messages]
        if definition.can_propose_file_changes:
            messages.insert(0, {"role": "system", "content": (
                f"Addition budget for this request: at most {policy.max_added_tokens} estimated tokens "
                "of new append/insert text across all files (approximately four characters per token). "
                "Unchanged destination text does not count. Use a smaller addition or ask to split a larger request."
            )})
        run_id = str(uuid4())
        events: list[AgentRunEvent] = []

        def record(stage: str, message: str) -> None:
            event = AgentRunEvent(stage, message)
            events.append(event)
            if on_event is not None:
                on_event(event)

        record("started", f"{selected.display_name} started")
        record("context", "Project and conversation context prepared")

        if selected == AgentType.WRITER:
            raw_response, calls = self._run_writer(
                definition,
                user_request,
                messages,
                complete,
                record,
            )
        else:
            prompt = self._compose_prompt(definition)
            raw_response = complete(messages, prompt)
            calls = 1
            record("completed", f"{selected.display_name} responded")

        notices: list[str] = []
        try:
            response, directive = self._extract_change_directive(raw_response)
        except (ValueError, json.JSONDecodeError) as error:
            logger.warning("Invalid agent change directive: %s", error)
            response = CHANGE_DIRECTIVE_PATTERN.sub("", raw_response).strip()
            directive = None
            notices.append(f"File proposal rejected: {error}")
        change_set = None
        preview = None

        if directive is not None:
            if not definition.can_propose_file_changes:
                notices.append(
                    f"{selected.display_name} is read-only; its file directive "
                    "was ignored."
                )
            elif self.file_tools is None:
                notices.append(
                    "File changes require an open, initialized project."
                )
            else:
                try:
                    change_set = self._prepare_change_set(
                        directive,
                        file_snapshots=snapshots,
                        policy=policy,
                    )
                    preview = self.file_tools.preview(change_set)
                    record(
                        "review",
                        f"Prepared {len(change_set.changes)} file change(s)",
                    )
                except (ValueError, FileToolError, json.JSONDecodeError) as error:
                    logger.warning("Agent file directive rejected: %s", error)
                    notices.append(f"File proposal rejected: {error}")

        visible_response = response.strip()
        if not visible_response and change_set is not None:
            visible_response = "I prepared the requested file changes for review."
        elif not visible_response:
            visible_response = (
                "SammyAI completed the workflow, but the model did not return "
                "displayable text. Please try again or switch models."
            )

        return AgentRunResult(
            run_id=run_id,
            agent_type=selected,
            response=visible_response,
            events=tuple(events),
            model_calls=calls,
            change_set=change_set,
            change_preview=preview,
            notices=tuple(notices),
        )

    def _run_writer(
        self,
        definition: AgentDefinition,
        user_request: str,
        messages: list[dict[str, str]],
        complete: LLMCompletion,
        record: Callable[[str, str], None],
    ) -> tuple[str, int]:
        writer_prompt = self._compose_prompt(definition)
        draft = complete(messages, writer_prompt)
        record("draft", "Writer produced a first draft")

        evaluation_messages = self._replace_last_user_message(
            messages,
            "ORIGINAL REQUEST:\n"
            f"{user_request}\n\nDRAFT TO EVALUATE:\n{draft}",
        )
        evaluator_definition = AgentDefinition(
            type=AgentType.WRITER,
            role_prompt=EVALUATOR_PROMPT,
            workflow_prompt=(
                "Return only an actionable revision brief for the Writer."
            ),
            can_propose_file_changes=False,
        )
        evaluation = complete(
            evaluation_messages,
            self._compose_prompt(evaluator_definition, read_only=True),
        )
        record("evaluation", "Evaluator reviewed the draft")

        revision_messages = self._replace_last_user_message(
            messages,
            "ORIGINAL REQUEST:\n"
            f"{user_request}\n\nFIRST DRAFT:\n{draft}\n\n"
            f"EVALUATOR BRIEF:\n{evaluation}",
        )
        final_response = complete(
            revision_messages,
            self._compose_prompt(
                definition,
                run_instruction=REVISION_PROMPT,
            ),
        )
        if not final_response.strip() and draft.strip():
            record(
                "revision",
                "Writer revision returned no text; showing the first draft",
            )
            record("completed", "Writer workflow completed")
            return draft, 3

        record("revision", "Writer revised the draft")
        record("completed", "Writer workflow completed")
        return final_response, 3

    @staticmethod
    def _replace_last_user_message(
        messages: list[dict[str, str]],
        content: str,
    ) -> list[dict[str, str]]:
        revised = [dict(message) for message in messages]
        for index in range(len(revised) - 1, -1, -1):
            if revised[index].get("role") == "user":
                revised[index] = {"role": "user", "content": content}
                return revised
        revised.append({"role": "user", "content": content})
        return revised

    def _compose_prompt(
        self,
        definition: AgentDefinition,
        *,
        read_only: bool | None = None,
        run_instruction: str | None = None,
    ) -> str:
        allow_changes = (
            definition.can_propose_file_changes
            if read_only is None
            else not read_only
        )
        layers = [
            PromptLayer("Core Policy", SYSTEM_PROMPT, PromptLayerOrder.CORE),
            PromptLayer(
                f"{definition.type.display_name} Role",
                definition.role_prompt,
                PromptLayerOrder.AGENT,
            ),
            PromptLayer(
                "Workflow",
                definition.workflow_prompt,
                PromptLayerOrder.WORKFLOW,
            ),
            PromptLayer(
                "Output Contract",
                CHANGE_OUTPUT_PROMPT if allow_changes else READ_ONLY_OUTPUT_PROMPT,
                PromptLayerOrder.OUTPUT,
            ),
        ]
        if run_instruction:
            layers.append(
                PromptLayer(
                    "Current Run Instruction",
                    run_instruction,
                    PromptLayerOrder.RUN,
                )
            )
        return self.prompt_composer.compose(layers)

    def _prepare_change_set(
        self,
        directive: dict,
        *,
        file_snapshots: tuple[FileEditSnapshot, ...],
        policy: AdditionPolicy,
    ) -> ChangeSet:
        if not isinstance(directive, dict):
            raise ValueError("Change directive must be a JSON object")
        summary = directive.get("summary")
        files = directive.get("files")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("Change directive requires a summary")
        if not isinstance(files, list) or not files:
            raise ValueError("Change directive requires at least one file")
        if len(files) > policy.max_files:
            raise ValueError(
                f"Change directive exceeds the {policy.max_files}-file limit"
            )

        if self.file_tools is None:
            raise FileToolError("Project file tools are unavailable")
        project = self.file_tools.project_service.active_project
        if project is None:
            raise FileToolError("File changes require an open project")
        snapshots = {_file_key(snapshot.relative_path): snapshot for snapshot in file_snapshots}
        requests: list[FileChangeRequest] = []
        added_tokens = 0
        for item in files:
            if not isinstance(item, dict):
                raise ValueError("Each file change must be an object")
            path = item.get("path")
            operation = item.get("operation")
            if not isinstance(path, str):
                raise ValueError("Each file change requires a path")
            if not isinstance(operation, str):
                raise ValueError(f"File operation for {path} must be a string")
            snapshot = snapshots.get(_file_key(path))
            if snapshot is not None and snapshot.project_id != project.id:
                raise FileToolError("The project changed since file context was captured. Request a new proposal.")
            expected_hash = snapshot.source_hash if snapshot else None
            if snapshot is not None and not snapshot.complete and operation in {"write", "delete"}:
                raise FileToolError(
                    f"@{path} was referenced but only partial context fit. Whole-file replacement/deletion is blocked; "
                    "use append or insertion for new material, or provide complete context for a rewrite."
                )
            if operation == "write":
                content = item.get("content")
                if not isinstance(content, str):
                    raise ValueError(f"Write for {path} requires string content")
                requests.append(FileChangeRequest.write(path, content, expected_hash=expected_hash))
            elif operation == "delete":
                requests.append(FileChangeRequest.delete(path, expected_hash=expected_hash))
            elif operation in {"append", "insert_before", "insert_after"}:
                allowed_fields = {"path", "operation", "content"}
                if operation != "append":
                    allowed_fields.add("anchor")
                if set(item) - allowed_fields:
                    raise ValueError(f"Unsupported addition fields for {path}: {', '.join(sorted(set(item) - allowed_fields))}")
                if snapshot is None:
                    raise FileToolError(f"Additions require current explicit @file context: {path}")
                content = item.get("content")
                edit = snapshot.addition(operation, content, item.get("anchor"))
                added_tokens += estimate_tokens(edit.replacement)
                if added_tokens > policy.max_added_tokens:
                    raise FileToolError(
                        f"New material exceeds the {policy.max_added_tokens}-token addition budget; "
                        "request a smaller addition. The destination file size is not the cause."
                    )
                requests.append(FileChangeRequest.edit(path, (edit,), expected_hash=expected_hash))
            else:
                raise ValueError(f"Unsupported operation for {path}: {operation}")

        change_set = self.file_tools.prepare_change_set(
            requests,
            description=summary,
        )
        if change_set.project_id != project.id:
            raise FileToolError("The project changed while preparing the proposal. Request a new proposal.")
        authorized = set(snapshots)
        unauthorized = [
            change.relative_path
            for change in change_set.changes
            if change.kind != FileChangeKind.CREATE
            and _file_key(change.relative_path) not in authorized
        ]
        if unauthorized:
            paths = ", ".join(unauthorized)
            raise FileToolError(
                "Existing files must be supplied as exact @file context before "
                f"an agent can change them: {paths}"
            )
        return change_set

    @staticmethod
    def _extract_change_directive(
        response: str,
    ) -> tuple[str, dict | None]:
        matches = list(CHANGE_DIRECTIVE_PATTERN.finditer(response))
        if not matches:
            return response, None
        if len(matches) > 1:
            raise ValueError("Agent returned multiple change directives")
        match = matches[0]
        directive = json.loads(match.group(1))
        visible_response = (
            response[:match.start()] + response[match.end():]
        ).strip()
        return visible_response, directive
