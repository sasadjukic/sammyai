"""Chat continues through selected agents and explicit review after DBE retirement."""

from types import SimpleNamespace

import pytest

from test_inline_review import review_window
from editing.change_sets import FileChangeRequest
from editing.review_session import HunkState
from llm.chat_manager import MessageRole
from sammyai_core.agent_workflows import AgentRunResult, AgentType


@pytest.mark.parametrize("operation,anchor", [("append", None), ("insert_before", "## Scene 10")])
def test_large_file_addition_from_chat_to_inline_review(review_window, monkeypatch, operation, anchor):
    import json
    from sammyai_core.context_engine import ProjectContextEngine, ProjectFileRepository
    window, root = review_window
    source = "".join(f"## Scene {i}\r\n" + "Existing material. " * 100 + "\r\n\r\n" for i in range(1, 20))
    path = root / "scene_breakdown.md"
    path.write_bytes(source.encode("utf-8"))
    window._open_file_path(path)
    window._create_chat_panel()
    window.chat_panel.agent_combo.setCurrentIndex(window.chat_panel.agent_combo.findData("editor"))
    engine = ProjectContextEngine(window.project_service, ProjectFileRepository(window.project_service.repository.database), None)
    window.chat_manager.context_engine = engine
    proposal = {"path": path.name, "operation": operation, "content": "## New scene\nA turning point.\n\n"}
    if anchor:
        proposal["anchor"] = anchor
    model_messages = []
    def complete(messages):
        model_messages.extend(messages)
        return "Ready to review.\n<sammyai_changes>" + json.dumps({"summary": "Add a scene", "files": [proposal]}) + "</sammyai_changes>"
    window.llm_client = SimpleNamespace(system_prompt="base", chat=complete)
    monkeypatch.setattr(window.task_runner, "submit", lambda fn, **kwargs: fn())
    window._on_chat_message_sent("Add a new scene before Scene 10 in @scene_breakdown.md" if anchor else "Add a new scene to @scene_breakdown.md")

    assert any("Partial file context" in message["content"] for message in model_messages)
    batch = next(iter(window.review_controller.batches.values()))
    view = window.editor_workspace.review_for_session(batch.reviews[0].target_document_id)
    assert path.read_bytes() == source.encode("utf-8")
    assert not view.apply_button.isEnabled()
    view.accept_all_button.click()
    view.apply_button.click()
    addition = "## New scene\r\nA turning point.\r\n\r\n"
    expected = source.replace(anchor, addition + anchor) if anchor else source + addition
    assert path.read_bytes() == expected.encode("utf-8")
    window._undo_last_change_set()
    assert path.read_bytes() == source.encode("utf-8")
    window._redo_last_change_set()
    assert path.read_bytes() == expected.encode("utf-8")


@pytest.mark.parametrize("agent", list(AgentType))
def test_send_uses_selected_agent_without_implicit_editor_selection(review_window, monkeypatch, agent):
    window, _root = review_window
    window._create_chat_panel()
    window.chat_panel.agent_combo.setCurrentIndex(window.chat_panel.agent_combo.findData(agent.value))
    window.editor.insertPlainText("Private unsaved selection")
    window.editor.selectAll()
    calls, completions = [], []
    window.llm_client = SimpleNamespace(system_prompt="base", chat=lambda messages: completions.extend(messages) or "Agent reply")

    def run(selected_agent, **kwargs):
        calls.append((selected_agent, kwargs))
        reply = kwargs["complete"](kwargs["messages"], "Selected agent prompt")
        return AgentRunResult("run", selected_agent, reply, (), 1)

    window.agent_workflows = SimpleNamespace(run=run)
    monkeypatch.setattr(window.task_runner, "submit", lambda fn, **kwargs: fn())
    window._on_chat_message_sent("Help with my scene")

    assert calls[0][0] == agent
    assert calls[0][1]["user_request"] == "Help with my scene"
    assert completions and all("Private unsaved selection" not in message["content"] for message in completions)
    assert window.llm_client.system_prompt == "base"
    messages = window.chat_manager.get_active_session().messages
    assert [message.role for message in messages[-2:]] == [MessageRole.USER, MessageRole.ASSISTANT]
    assert messages[-1].content == "Agent reply"
    assert messages[-1].metadata["agent_type"] == agent.value
    assert window.editor.toPlainText() == "Private unsaved selection"
    assert not window.review_controller.batches


def test_editor_chat_proposal_requires_review_and_keeps_file_history(review_window, monkeypatch):
    window, root = review_window
    path = root / "chapter.md"
    path.write_bytes(b"Original\r\n")
    window._open_file_path(path)
    window._create_chat_panel()
    window.chat_panel.agent_combo.setCurrentIndex(window.chat_panel.agent_combo.findData("editor"))
    source = window.file_tools.prepare_change_set([FileChangeRequest.write("chapter.md", "Revised\r\n")], description="Revise")
    window.llm_client = SimpleNamespace(system_prompt="base")
    window.agent_workflows = SimpleNamespace(run=lambda *a, **k: AgentRunResult(
        "editor-run", AgentType.EDITOR, "Review this proposal", (), 1,
        source, window.file_tools.preview(source),
    ))
    monkeypatch.setattr(window.task_runner, "submit", lambda fn, **kwargs: fn())
    window._on_chat_message_sent("Revise @chapter.md")

    batch = next(iter(window.review_controller.batches.values()))
    assert path.read_bytes() == b"Original\r\n"
    assert batch.reviews[0].originating_session_id == window.chat_manager.active_session_id
    view = window.editor_workspace.review_for_session(batch.reviews[0].target_document_id)
    assert not view.apply_button.isEnabled()
    batch.reviews[0].decide_all(HunkState.ACCEPTED)
    assert window.review_controller.apply(batch.id)
    assert path.read_bytes() == b"Revised\r\n"
    window._undo_last_change_set()
    assert path.read_bytes() == b"Original\r\n"
    window._redo_last_change_set()
    assert path.read_bytes() == b"Revised\r\n"
