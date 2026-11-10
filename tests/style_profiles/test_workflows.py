from dataclasses import replace
import json

import pytest

from llm.style_prompt import style_layer, style_metadata
from sammyai_core.agent_workflows import AgentType, AgentWorkflowService
from sammyai_core.database import ProjectDatabase
from sammyai_core.diagnostics import RequestTraceService
from sammyai_core.selection_actions import SelectionAction, SelectionActionRequest, SelectionSnapshot, parse_result
from sammyai_core.style_profiles import StyleProfileSnapshot


@pytest.fixture
def snapshot():
    return StyleProfileSnapshot("style", None, "My voice", 3, "UNIQUE_PRIVATE_RULE: use concrete detail.", "UNIQUE_PRIVATE_EXAMPLE: Rain ticked on the lid.")


@pytest.mark.parametrize("agent", list(AgentType))
def test_agents_receive_profile_once_in_correct_mode(snapshot, agent):
    prompts = []
    result = AgentWorkflowService(None).run(agent, user_request="Write a paragraph.",
        messages=[{"role": "user", "content": "Write a paragraph."}], style_snapshot=snapshot,
        complete=lambda messages, prompt: prompts.append(prompt) or "Prose.")
    uses_style = agent in {AgentType.WRITER, AgentType.EDITOR, AgentType.CRITIC}
    for index, prompt in enumerate(prompts):
        assert prompt.count("UNIQUE_PRIVATE_RULE") == int(uses_style)
        assert prompt.count("UNIQUE_PRIVATE_EXAMPLE") == int(uses_style)
        if uses_style:
            assert prompt.index("## Writer Style") < prompt.index("## Workflow") < prompt.index("## Output Contract")
            assert "current explicit request overrides" in prompt
            assert ("Evaluate adherence to this style" in prompt) == (agent == AgentType.CRITIC or index == 1)
    assert result.style_used["state"] == ("selected" if uses_style else "not_applicable")


@pytest.mark.parametrize("action", list(SelectionAction))
def test_selection_uses_shared_layer_preserves_exact_context_and_contract(snapshot, action):
    selection = SelectionSnapshot("doc", None, "Draft", "hash", "Before.\nPassage.\nAfter.", 1, None, 8, 16, "text")
    request = SelectionActionRequest(selection, action, "chat", None, "joyful", style_snapshot=snapshot)
    prompt = request.system_prompt()
    assert prompt.count(snapshot.canonical_content) == 1
    assert request.style_profile_id == snapshot.id
    assert style_layer(snapshot, request.style_used["mode"]).content in prompt
    assert prompt.index("## Writer Style") < prompt.index("## Output Contract")
    assert "requested tone change" in prompt and "tighten when asked to tighten" in prompt
    message = json.loads(request.messages()[0]["content"])
    assert message["passage"] == selection.prompt_context()
    if action == SelectionAction.TONE:
        assert "joyful" in message["instruction"]
    if action == SelectionAction.CRITIQUE:
        with pytest.raises(ValueError):
            parse_result('{"kind":"replacement","text":"changed"}', request)
    if action == SelectionAction.CUSTOM:
        assert request.style_used["mode"] == "conditional"
        for kind in ("critique", "replacement"):
            assert parse_result(json.dumps({"kind": kind, "text": "result"}), request).kind == kind


@pytest.mark.parametrize("capture", [False, True])
def test_stage_metadata_survives_restart_and_respects_content_capture(snapshot, tmp_path, capture):
    db = ProjectDatabase(tmp_path / "traces.sqlite3")
    db.migrate()
    trace = RequestTraceService(db)
    trace.save_settings(replace(trace.settings, prompts=capture))
    identity = trace.begin("chat", None, agent="writer")
    AgentWorkflowService(None).run("writer", user_request="Write a paragraph.", messages=[{"role": "user", "content": "Write a paragraph."}],
        complete=lambda *_: "Prose.", style_snapshot=snapshot, trace=trace, identity=identity)
    db.close()
    reopened = ProjectDatabase(tmp_path / "traces.sqlite3")
    try:
        detail = RequestTraceService(reopened).detail(identity.request_id, include_content=True)
        events = [e for e in detail["events"] if e["code"] == "style.used"]
        assert len(events) == 3
        assert [e["details"]["mode"] for e in events] == ["apply", "evaluate", "apply"]
        assert {e["details"]["content_hash"] for e in events} == {snapshot.content_hash}
        assert "UNIQUE_PRIVATE_RULE" not in json.dumps(events)
        assert ("UNIQUE_PRIVATE_EXAMPLE" in json.dumps(detail)) == capture
    finally:
        reopened.close()


def test_content_hash_shared_but_evaluation_wrapper_differs(snapshot):
    writing, evaluating = style_metadata(snapshot), style_metadata(snapshot, "evaluate")
    assert writing["content_hash"] == evaluating["content_hash"]
    assert writing["layer_hash"] != evaluating["layer_hash"]
    assert writing["estimated_tokens"] > 0
    assert snapshot.instructions not in json.dumps(writing)
