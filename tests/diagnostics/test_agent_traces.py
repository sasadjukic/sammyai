from dataclasses import replace
import json

import pytest

from test_trace_service import trace
from sammyai_core.agent_workflows import AgentWorkflowService


def run(trace, responses, *, agent="general", metadata=None):
    identity = trace.begin("chat", "project", agent=agent)
    replies = iter(responses)
    result = AgentWorkflowService(None).run(agent, user_request="Help", messages=[{"role": "user", "content": "Help"}],
        complete=lambda *_: next(replies), trace=trace, identity=identity, response_metadata=lambda: metadata or {})
    return result, trace.detail(identity.request_id, include_content=True)


def test_writer_stages_and_configurable_evidence_survive_reload(trace):
    trace.save_settings(replace(trace.settings, drafts=True, responses=True, prompts=True))
    result, data = run(trace, ["Draft", "Evaluation", "Revision"], agent="writer")
    assert result.response == "Revision"
    assert [s["name"] for s in data["steps"]] == ["model.draft", "model.evaluation", "model.revision", "proposal.validation"]
    assert all(s["duration_ms"] >= 0 for s in data["steps"])
    assert [c["text"] for c in data["content"] if c["kind"] == "drafts"] == ["Draft", "Evaluation"]
    assert data["request"]["run_id"] == result.run_id
    for event in data["events"]:
        if event["code"] == "model.responded":
            assert event["details"]["provider_request_id"] is None
            assert event["details"]["finish_reason"] is None


def test_normal_prose_is_not_labeled_as_a_json_proposal(trace):
    _, data = run(trace, ["Some writing advice."])
    validation = next(e for e in data["events"] if e["code"] == "proposal.validation")["details"]
    assert validation["proposal_format"] is None and validation["operations"] == []


@pytest.mark.parametrize("operation", ["PRIVATE STORY", {"text": "PRIVATE STORY"}])
def test_invalid_operations_do_not_bypass_capture_settings_in_metadata(trace, operation):
    raw = '<sammyai_changes>' + json.dumps({"files": [{"path": "chapter.md", "operation": operation}]}) + '</sammyai_changes>'
    _, data = run(trace, [raw], agent="editor")
    assert "PRIVATE STORY" not in json.dumps(data)
    validation = next(e for e in data["events"] if e["code"] == "proposal.validation")["details"]
    assert validation["operations"] == ["unsupported"]


@pytest.mark.parametrize("source", [
    '<sammyai_changes>{"files": broken}</sammyai_changes>',
    '<sammyai_changes>{"files":[]}',
])
def test_failed_proposals_have_captured_original_and_truthful_outcome(trace, source):
    trace.save_settings(replace(trace.settings, failed_proposals=True))
    result, data = run(trace, [source], agent="editor")
    assert result.outcome == "proposal_rejected"
    assert result.change_set is None
    assert data["request"]["outcome"] == "proposal_rejected"
    assert any(e["code"] == "error.proposal_parse" and e["details"]["traceback"] for e in data["events"])
    assert next(c for c in data["content"] if c["kind"] == "failed_proposals")["text"] == source


def test_malformed_json_ending_retains_location_without_capturing_content(trace):
    body = '{"files":[\n  {"path":"chapter.md","content":"PRIVATE STORY"' + r'\n]}"\n'
    with pytest.raises(json.JSONDecodeError) as expected:
        json.loads(body)
    result, data = run(trace, ['<sammyai_changes>' + body + '</sammyai_changes>'], agent="editor")
    assert result.outcome == "proposal_rejected"
    assert result.change_set is None and result.change_preview is None
    assert result.model_calls == 1
    assert "Invalid JSON in change directive" in result.notices[0]
    assert f"line {expected.value.lineno}, column {expected.value.colno}" in result.notices[0]
    assert "PRIVATE STORY" not in result.response
    assert "PRIVATE STORY" not in json.dumps(data)
    error = next(e for e in data["events"] if e["code"] == "error.proposal_parse")
    assert error["details"]["exception_type"] == "JSONDecodeError"
    assert error["details"]["json_error"] == {
        "message": expected.value.msg, "line": expected.value.lineno,
        "column": expected.value.colno, "position": expected.value.pos,
    }


@pytest.mark.parametrize("text,metadata,event", [
    ("", {}, "model.empty"),
    ("partial text", {"finish_reason": "length", "provider_request_id": "provider-id", "usage": {"total_tokens": 55}}, "model.truncated"),
])
def test_empty_and_truncated_responses_are_distinct(trace, text, metadata, event):
    result, data = run(trace, [text], metadata=metadata)
    assert result.outcome == "incomplete_response"
    assert any(e["code"] == event for e in data["events"])
    assert result.change_set is None


def test_provider_exception_has_step_traceback_and_durable_failure(trace):
    identity = trace.begin("chat", None, agent="general")
    def fail(*_):
        raise TimeoutError("provider timeout")
    with pytest.raises(TimeoutError):
        AgentWorkflowService(None).run("general", user_request="test", messages=[], complete=fail, trace=trace, identity=identity)
    data = trace.detail(identity.request_id)
    assert data["request"]["outcome"] == "provider_failed"
    assert data["steps"][0]["outcome"] == "provider_failed"
    error = next(e for e in data["events"] if e["code"] == "error.provider")
    assert error["details"]["exception_type"] == "TimeoutError"
    assert error["details"]["traceback"]


@pytest.mark.parametrize("source", [
    '<SAMMYAI_CHANGES>{"private": "SECRET STORY"}',
    '</sammyai_changes>SECRET STORY',
    '< sammyai_changes>SECRET STORY',
])
def test_malformed_envelopes_do_not_leak_uncaptured_proposal_into_chat(trace, source):
    result, data = run(trace, [source], agent="editor")
    assert result.outcome == "proposal_rejected"
    assert "SECRET STORY" not in result.response
    assert "SECRET STORY" not in json.dumps(data)
