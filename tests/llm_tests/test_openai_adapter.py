"""Exercise real OpenAI SDK serialization with an offline HTTP transport."""

import json
from unittest.mock import MagicMock

import httpx
import openai
import pytest

from llm.client import LLMClient
from sammyai_core.agent_workflows import AgentType, AgentWorkflowService
from sammyai_core.database import ProjectDatabase
from sammyai_core.diagnostics import RequestTraceService
from sammyai_core.selection_actions import (
    SelectionAction, SelectionActionRequest, SelectionSnapshot, parse_result,
)
from sammyai_core.style_profiles import StyleProfileSnapshot


@pytest.fixture
def make_client(monkeypatch):
    sdk_class = openai.OpenAI
    clients = []

    def make(model="gpt-6-luna", *, text="Revised prose.", error=None, finish_reason="stop"):
        requests = []

        def respond(request):
            assert request.method == "POST"
            assert request.url.path == "/v1/chat/completions"
            payload = json.loads(request.content)
            requests.append(payload)
            if error:
                return httpx.Response(400, json={"error": {
                    "message": error, "type": "invalid_request_error",
                    "param": "model", "code": "unsupported_value",
                }})
            return httpx.Response(200, headers={"x-request-id": "req-offline"}, json={
                "id": "completion-offline", "object": "chat.completion", "created": 0,
                "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                             "finish_reason": finish_reason}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            })

        sdk = sdk_class(api_key="offline-test-key", max_retries=0,
                        http_client=httpx.Client(transport=httpx.MockTransport(respond)))
        clients.append(sdk)
        monkeypatch.setattr("llm.client.openai.OpenAI", lambda **kwargs: sdk)
        monkeypatch.setattr("llm.client.get_model_mapping", lambda: {
            "Test": {"name": model, "type": "cloud", "provider": "openai"},
        })
        return LLMClient("Test", api_key="offline-test-key", system_prompt="Base rules."), requests

    yield make
    for client in clients:
        client.close()


@pytest.mark.parametrize("model", [
    "gpt-6-luna", "gpt-6-luna-2026-08-20", "gpt-6-astra", "gpt-6.1-sol",
    "gpt-6.1-terra", "gpt-5", "gpt-5-mini", "gpt-5.1", "gpt-5.2",
    "gpt-5.6-luna", "o1", "o1-mini", "o3", "o3-mini-2025-01-31", "o4-mini",
    "ft:o4-mini-2025-04-16:example:writer:123",
])
def test_reasoning_request_omits_unset_limit_and_sampling_controls(make_client, model):
    client, requests = make_client(model)
    assert client.chat([{"role": "user", "content": "Write a paragraph."}]) == "Revised prose."
    assert requests == [{"model": model, "messages": [
        {"role": "system", "content": "Base rules."},
        {"role": "user", "content": "Write a paragraph."},
    ]}]
    metadata = client.last_response_metadata
    assert metadata["effective_settings"] == {}
    assert metadata["provider_request_id"] == "req-offline"
    assert metadata["usage"]["total_tokens"] == 15


@pytest.mark.parametrize("model", ["gpt-6-luna", "gpt-5-mini", "o3-mini"])
def test_reasoning_limit_uses_completion_tokens_and_ignores_sampling_overrides(make_client, model):
    client, requests = make_client(model)
    client.chat([{"role": "user", "content": "Write."}], max_tokens=2048,
                temperature=0.4, top_p=0.8, seed=42, include_system=False)
    assert requests == [{"model": model, "messages": [{"role": "user", "content": "Write."}],
                         "max_completion_tokens": 2048}]
    assert client.last_response_metadata["effective_settings"] == {"max_completion_tokens": 2048}


@pytest.mark.parametrize("model", [
    "gpt-4o", "gpt-4.1-mini", "gpt-3.5-turbo", "ft:gpt-4o-2024-08-06:example:writer:123",
    "custom-chat-model", "o10-custom", "gpt-60-custom",
])
def test_legacy_and_unknown_models_keep_sampling_and_explicit_limit(make_client, model):
    client, requests = make_client(model)
    client.chat([{"role": "user", "content": "Write."}], max_tokens=128,
                temperature=0, top_p=0.75, seed=0)
    assert requests[0]["model"] == model
    assert {k: v for k, v in requests[0].items() if k not in {"model", "messages"}} == {
        "max_tokens": 128, "temperature": 0, "top_p": 0.75, "seed": 0,
    }


def test_legacy_defaults_and_unset_values_are_serialized_without_nulls(make_client):
    client, requests = make_client("gpt-4o")
    client.temperature, client.top_p, client.seed = 0.65, 0.85, None
    client.chat([{"role": "user", "content": "Write."}])
    assert requests[0]["temperature"] == 0.65
    assert requests[0]["top_p"] == 0.85
    assert "seed" not in requests[0] and "max_tokens" not in requests[0]
    assert client.last_response_metadata["effective_settings"] == {"temperature": 0.65, "top_p": 0.85}
    client.temperature = client.top_p = None
    client.chat([{"role": "user", "content": "Write again."}])
    assert set(requests[1]) == {"model", "messages"}
    assert client.last_response_metadata["effective_settings"] == {}


def test_provider_error_is_preserved_without_retry_or_model_fallback(make_client):
    client, requests = make_client(error="This model is unavailable.")
    with pytest.raises(RuntimeError, match="This model is unavailable") as caught:
        client.chat([{"role": "user", "content": "Write."}])
    assert isinstance(caught.value.__cause__, openai.BadRequestError)
    assert caught.value.__cause__.status_code == 400
    assert len(requests) == 1
    assert requests[0]["model"] == "gpt-6-luna"
    assert client.last_response_metadata["effective_settings"] == {}


@pytest.fixture
def style():
    return StyleProfileSnapshot("style", None, "Direct prose", 2,
                                "DISTINCTIVE_STYLE: avoid decorative contrasts.",
                                "DISTINCTIVE_EXAMPLE: Rain tapped the lid.")


@pytest.mark.parametrize("agent,call_count", [(AgentType.WRITER, 3), (AgentType.EDITOR, 1)])
def test_writing_stages_send_style_with_valid_luna_parameters(make_client, style, agent, call_count, tmp_path):
    client, requests = make_client()
    db = ProjectDatabase(tmp_path / "diagnostics.sqlite3")
    db.migrate()
    try:
        trace = RequestTraceService(db)
        identity = trace.begin("chat", None, agent=agent.value)

        def complete(messages, prompt):
            client.system_prompt = prompt
            return client.chat(messages)

        result = AgentWorkflowService(None).run(
            agent, user_request="Write a paragraph.",
            messages=[{"role": "user", "content": "Write a paragraph."}],
            style_snapshot=style, complete=complete, trace=trace, identity=identity,
            response_metadata=lambda: client.last_response_metadata,
        )
        assert result.response == "Revised prose."
        assert result.model_calls == len(requests) == call_count
        for payload in requests:
            assert set(payload) == {"model", "messages"}
            assert json.dumps(payload["messages"]).count("DISTINCTIVE_STYLE") == 1
            assert json.dumps(payload["messages"]).count("DISTINCTIVE_EXAMPLE") == 1
        detail = trace.detail(identity.request_id, include_content=True)
        responded = [event for event in detail["events"] if event["code"] == "model.responded"]
        assert len(responded) == call_count
        assert all(event["details"]["effective_settings"] == {} for event in responded)
        assert "DISTINCTIVE_STYLE" not in json.dumps(detail)
    finally:
        db.close()


@pytest.mark.parametrize("action,kind", [
    (SelectionAction.REWRITE, "replacement"), (SelectionAction.TIGHTEN, "replacement"),
    (SelectionAction.EXPAND, "replacement"), (SelectionAction.DIALOGUE, "replacement"),
    (SelectionAction.TONE, "replacement"), (SelectionAction.CONTINUE, "insertion"),
    (SelectionAction.CRITIQUE, "critique"), (SelectionAction.CUSTOM, "replacement"),
    (SelectionAction.CUSTOM, "critique"),
])
def test_every_selection_action_sends_style_and_preserves_result_contract(make_client, style, action, kind):
    reply = json.dumps({"kind": kind, "text": "Revised passage."})
    client, requests = make_client(text=reply)
    original = "Before.\nOld passage.\nAfter."
    selection = SelectionSnapshot("doc", None, "Draft", "hash", original, 1, None,
                                  20 if action == SelectionAction.CONTINUE else 8, 20, "text")
    request = SelectionActionRequest(selection, action, "chat", None, "playful", style_snapshot=style)
    client.system_prompt = request.system_prompt()
    response = client.chat(request.messages())
    result = parse_result(response, request, client.last_response_metadata)
    assert result.kind == kind
    assert set(requests[0]) == {"model", "messages"}
    messages = requests[0]["messages"]
    assert messages[0]["content"].count(style.instructions) == 1
    assert messages[0]["content"].count(style.examples) == 1
    assert "## Output Contract" in messages[0]["content"]
    assert json.loads(messages[1]["content"])["passage"] == selection.prompt_context()
    if kind == "critique":
        with pytest.raises(ValueError, match="Critiques cannot"):
            result.proposed_text(request)
    else:
        assert result.proposed_text(request) == original[:selection.start] + result.text + original[selection.end:]


def test_luna_truncation_metadata_still_blocks_selection_edits(make_client, style):
    client, _ = make_client(text='{"kind":"replacement","text":"Incomplete"}', finish_reason="length")
    selection = SelectionSnapshot("doc", None, "Draft", "hash", "Passage.", 1, None, 0, 8, "text")
    request = SelectionActionRequest(selection, SelectionAction.REWRITE, "chat", None, style_snapshot=style)
    client.system_prompt = request.system_prompt()
    response = client.chat(request.messages())
    with pytest.raises(ValueError, match="truncated"):
        parse_result(response, request, client.last_response_metadata)


@pytest.mark.parametrize("provider", ["local", "ollama_cloud"])
def test_ollama_keeps_sampling_controls_and_native_token_limit(monkeypatch, provider):
    monkeypatch.setattr("llm.client.get_model_mapping", lambda: {
        "Test": {"name": "gemma4:31b", "type": "local" if provider == "local" else "cloud",
                 "provider": provider},
    })
    sdk = MagicMock()
    sdk.chat.return_value = {"message": {"content": "Prose."}}
    monkeypatch.setattr("llm.client.ollama.Client", lambda **kwargs: sdk)
    client = LLMClient("Test", api_key="offline-test-key")
    assert client.chat([{"role": "user", "content": "Write."}], max_tokens=128,
                       temperature=0.6, top_p=0.8, seed=0) == "Prose."
    assert sdk.chat.call_args.kwargs["options"] == {
        "temperature": 0.6, "top_p": 0.8, "seed": 0, "num_predict": 128,
    }
