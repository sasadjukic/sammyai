import json

import pytest

from sammyai_core.agent_workflows import (
    AGENT_DEFINITIONS,
    AgentType,
    AgentWorkflowService,
)
from sammyai_core.database import ProjectDatabase
from sammyai_core.file_tools import SafeFileTools
from sammyai_core.paths import AppPaths
from sammyai_core.projects import ProjectRepository, ProjectService


@pytest.fixture
def workflow_service(tmp_path):
    paths = AppPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        log_dir=tmp_path / "logs",
    ).ensure_created()
    database = ProjectDatabase(paths.project_database_path)
    database.migrate()
    project_service = ProjectService(ProjectRepository(database), paths)
    root = tmp_path / "novel"
    root.mkdir()
    project_service.open_project(root)
    service = AgentWorkflowService(SafeFileTools(project_service))
    try:
        yield root, service
    finally:
        database.close()


def test_all_public_agent_types_have_definitions():
    assert set(AGENT_DEFINITIONS) == set(AgentType)
    assert [agent.display_name for agent in AgentType] == [
        "Assistant",
        "Brainstormer",
        "Writer",
        "Editor",
        "Critic",
    ]


def test_general_agent_uses_one_layered_prompt(workflow_service):
    _root, service = workflow_service
    calls = []

    def complete(messages, system_prompt):
        calls.append((messages, system_prompt))
        return "Three possible openings."

    result = service.run(
        AgentType.GENERAL,
        user_request="Suggest an opening.",
        messages=[{"role": "user", "content": "Suggest an opening."}],
        complete=complete,
    )

    assert result.response == "Three possible openings."
    assert result.model_calls == 1
    assert result.change_set is None
    assert "## Core Policy" in calls[0][1]
    assert "## Assistant Role" in calls[0][1]
    assert "## Output Contract" in calls[0][1]


def test_writer_runs_draft_evaluation_and_revision(workflow_service):
    _root, service = workflow_service
    responses = iter(
        (
            "First draft",
            "The ending lacks a decisive image.",
            "Revised final draft",
        )
    )
    calls = []
    progress = []

    def complete(messages, system_prompt):
        calls.append((messages, system_prompt))
        return next(responses)

    result = service.run(
        AgentType.WRITER,
        user_request="Write the final paragraph.",
        messages=[
            {"role": "system", "content": "Project context"},
            {"role": "user", "content": "Write the final paragraph."},
        ],
        complete=complete,
        on_event=lambda event: progress.append(event.stage),
    )

    assert result.response == "Revised final draft"
    assert result.model_calls == 3
    assert [event.stage for event in result.events] == [
        "started",
        "context",
        "draft",
        "evaluation",
        "revision",
        "completed",
    ]
    assert progress == [
        "started",
        "context",
        "draft",
        "evaluation",
        "revision",
        "completed",
    ]
    assert "DRAFT TO EVALUATE:\nFirst draft" in calls[1][0][-1]["content"]
    assert "strict evaluator" in calls[1][1]
    assert "EVALUATOR BRIEF" in calls[2][0][-1]["content"]
    assert "Current Run Instruction" in calls[2][1]


def test_writer_returns_first_draft_when_revision_is_empty(workflow_service):
    _root, service = workflow_service
    responses = iter(
        (
            "First draft with the teaser scenes.",
            "The draft satisfies the request.",
            "   ",
        )
    )

    def complete(_messages, _system_prompt):
        return next(responses)

    result = service.run(
        AgentType.WRITER,
        user_request="Write a teaser opening.",
        messages=[{"role": "user", "content": "Write a teaser opening."}],
        complete=complete,
    )

    assert result.response == "First draft with the teaser scenes."
    assert result.model_calls == 3
    assert result.events[-2].message == (
        "Writer revision returned no text; showing the first draft"
    )


def test_brainstormer_prepares_but_does_not_apply_file_change(
    workflow_service,
):
    root, service = workflow_service
    directive = {
        "summary": "Create a character arc",
        "files": [
            {
                "path": "characters/mara.md",
                "operation": "write",
                "content": "# Mara\n\nShe learns to trust the crew.\n",
            }
        ],
    }

    result = service.run(
        AgentType.BRAINSTORMER,
        user_request="Create Mara's arc in characters/mara.md",
        messages=[{"role": "user", "content": "Create the file."}],
        complete=lambda _messages, _prompt: (
            "I prepared Mara's arc.\n"
            f"<sammyai_changes>{json.dumps(directive)}</sammyai_changes>"
        ),
    )

    assert result.response == "I prepared Mara's arc."
    assert result.change_set is not None
    assert result.change_preview.files[0].relative_path == "characters/mara.md"
    assert not (root / "characters" / "mara.md").exists()


def test_critic_is_read_only_even_if_model_emits_directive(workflow_service):
    _root, service = workflow_service
    directive = {
        "summary": "Forbidden edit",
        "files": [
            {
                "path": "chapter.md",
                "operation": "write",
                "content": "Rewritten",
            }
        ],
    }

    result = service.run(
        AgentType.CRITIC,
        user_request="Critique this.",
        messages=[{"role": "user", "content": "Critique this."}],
        complete=lambda _messages, _prompt: (
            "The motivation is unclear."
            f"<sammyai_changes>{json.dumps(directive)}</sammyai_changes>"
        ),
    )

    assert result.response == "The motivation is unclear."
    assert result.change_set is None
    assert "read-only" in result.notices[0]


def test_unsafe_agent_file_directive_becomes_a_notice(workflow_service):
    _root, service = workflow_service
    directive = {
        "summary": "Escape project",
        "files": [
            {
                "path": "../outside.md",
                "operation": "write",
                "content": "Blocked",
            }
        ],
    }

    result = service.run(
        AgentType.EDITOR,
        user_request="Edit a file.",
        messages=[{"role": "user", "content": "Edit a file."}],
        complete=lambda _messages, _prompt: (
            f"<sammyai_changes>{json.dumps(directive)}</sammyai_changes>"
        ),
    )

    assert result.change_set is None
    assert "Unsafe project-relative path" in result.notices[0]


def test_existing_file_change_requires_exact_file_authorization(
    workflow_service,
):
    root, service = workflow_service
    (root / "chapter.md").write_bytes(b"Original\n")
    directive = {
        "summary": "Revise chapter",
        "files": [
            {
                "path": "chapter.md",
                "operation": "write",
                "content": "Revised\n",
            }
        ],
    }
    response = (
        "Revision prepared."
        f"<sammyai_changes>{json.dumps(directive)}</sammyai_changes>"
    )

    blocked = service.run(
        AgentType.EDITOR,
        user_request="Revise the chapter.",
        messages=[{"role": "user", "content": "Revise the chapter."}],
        complete=lambda _messages, _prompt: response,
    )
    allowed = service.run(
        AgentType.EDITOR,
        user_request="Revise @chapter.md.",
        messages=[{"role": "user", "content": "Revise @chapter.md."}],
        complete=lambda _messages, _prompt: response,
        authorized_files=("chapter.md",),
    )

    assert blocked.change_set is None
    assert "exact @file context" in blocked.notices[0]
    assert allowed.change_set is not None


def test_malformed_agent_directive_does_not_crash_run(workflow_service):
    _root, service = workflow_service

    result = service.run(
        AgentType.EDITOR,
        user_request="Edit a file.",
        messages=[{"role": "user", "content": "Edit a file."}],
        complete=lambda _messages, _prompt: (
            "I attempted a file proposal."
            "<sammyai_changes>{not-json}</sammyai_changes>"
        ),
    )

    assert result.change_set is None
    assert "File proposal rejected" in result.notices[0]
