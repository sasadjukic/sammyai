"""Agent definitions and orchestrated creative-writing workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import logging
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


logger = logging.getLogger(__name__)

CHANGE_DIRECTIVE_PATTERN = re.compile(
    r"<sammyai_changes>\s*(\{.*?\})\s*</sammyai_changes>",
    re.DOTALL,
)
MAX_CHANGE_FILES = 20


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
            "When asked to edit a project file, return the complete resulting "
            "file through a structured change directive for diff review."
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

CHANGE_OUTPUT_PROMPT = """
Normal prose belongs outside the directive.

Only when the user explicitly requests a project file creation, update, or
deletion, append exactly one directive in this form:

<sammyai_changes>
{"summary":"Short description","files":[
  {"path":"project-relative.md","operation":"write","content":"complete UTF-8 file content"}
]}
</sammyai_changes>

Allowed operations are "write" and "delete". Use only project-relative .md or
.txt paths. "write" must contain the complete resulting file, not a patch.
Existing files may be changed only when their complete contents were supplied
through explicit @file context; otherwise ask the user to reference the file.
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
change, include the structured change directive using the complete revised
file content.
"""


class AgentWorkflowService:
    """Execute selected agents and convert file proposals into change sets."""

    def __init__(self, file_tools: SafeFileTools | None):
        self.file_tools = file_tools
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
        on_event: AgentEventCallback | None = None,
    ) -> AgentRunResult:
        selected = AgentType(agent_type)
        definition = AGENT_DEFINITIONS[selected]
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
                        authorized_files=authorized_files,
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
        authorized_files: Iterable[str],
    ) -> ChangeSet:
        if not isinstance(directive, dict):
            raise ValueError("Change directive must be a JSON object")
        summary = directive.get("summary")
        files = directive.get("files")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("Change directive requires a summary")
        if not isinstance(files, list) or not files:
            raise ValueError("Change directive requires at least one file")
        if len(files) > MAX_CHANGE_FILES:
            raise ValueError(
                f"Change directive exceeds the {MAX_CHANGE_FILES}-file limit"
            )

        requests: list[FileChangeRequest] = []
        for item in files:
            if not isinstance(item, dict):
                raise ValueError("Each file change must be an object")
            path = item.get("path")
            operation = item.get("operation")
            if not isinstance(path, str):
                raise ValueError("Each file change requires a path")
            if operation == "write":
                content = item.get("content")
                if not isinstance(content, str):
                    raise ValueError(f"Write for {path} requires string content")
                requests.append(FileChangeRequest.write(path, content))
            elif operation == "delete":
                requests.append(FileChangeRequest.delete(path))
            else:
                raise ValueError(f"Unsupported operation for {path}: {operation}")

        if self.file_tools is None:
            raise FileToolError("Project file tools are unavailable")
        change_set = self.file_tools.prepare_change_set(
            requests,
            description=summary,
        )
        authorized = {
            path.replace("\\", "/").casefold()
            for path in authorized_files
        }
        unauthorized = [
            change.relative_path
            for change in change_set.changes
            if change.kind != FileChangeKind.CREATE
            and change.relative_path.casefold() not in authorized
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
