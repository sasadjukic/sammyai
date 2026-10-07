from types import SimpleNamespace as Obj

import pytest

from llm.client import LLMClient


@pytest.mark.parametrize("provider,response,reason,usage", [
    ("openai", Obj(id="completion", _request_id="request", choices=[Obj(finish_reason="length")], usage=Obj(prompt_tokens=5, completion_tokens=9)), "length", "prompt_tokens"),
    ("anthropic", Obj(id="message", _request_id="request", stop_reason="end_turn", usage=Obj(input_tokens=5, output_tokens=9)), "end_turn", "input_tokens"),
    ("google", Obj(response_id="response", candidates=[Obj(finish_reason="MAX_TOKENS")], usage_metadata=Obj(prompt_token_count=5, candidates_token_count=9)), "MAX_TOKENS", "prompt_token_count"),
    ("ollama", {"done_reason": "stop", "prompt_eval_count": 5, "eval_count": 9}, "stop", "input_tokens"),
])
def test_metadata_allowlist_retains_available_values(provider, response, reason, usage):
    client = object.__new__(LLMClient)
    client.last_response_metadata = {"effective_settings": {"temperature": 0.7}}
    client._record_response_metadata(response, provider)
    assert client.last_response_metadata["finish_reason"] == reason
    assert client.last_response_metadata["usage"][usage] == 5
    assert client.last_response_metadata["effective_settings"] == {"temperature": 0.7}


def test_absent_provider_metadata_remains_unknown():
    client = object.__new__(LLMClient)
    client._record_response_metadata({}, "openai")
    assert client.last_response_metadata["usage"] is None
    assert client.last_response_metadata["finish_reason"] is None
    assert client.last_response_metadata["provider_request_id"] is None
