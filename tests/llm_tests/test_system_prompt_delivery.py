"""Characterization tests for provider-specific system-prompt delivery."""

from unittest.mock import MagicMock, patch
import pytest

from llm.client import LLMClient, SYSTEM_PROMPT


@pytest.mark.parametrize("provider", ["openai", "anthropic", "google", "ollama_cloud", "local"])
def test_writer_style_reaches_every_provider_exactly_once(provider):
    from llm.style_prompt import style_layer
    from sammyai_core.style_profiles import StyleProfileSnapshot
    style = StyleProfileSnapshot("profile", None, "Style", 1, "DISTINCTIVE_STYLE_RULE")
    prompt = "Base rules\n" + style_layer(style).content
    mapping = {"Test": {"name": "test-model", "provider": provider, "type": "local" if provider == "local" else "cloud"}}
    with (patch("llm.client.get_model_mapping", return_value=mapping),
          patch("llm.client.openai.OpenAI") as openai_factory,
          patch("llm.client.anthropic.Anthropic") as anthropic_factory,
          patch("llm.client.genai.Client") as google_factory,
          patch("llm.client.ollama.Client") as ollama_factory):
        openai_factory.return_value.chat.completions.create.return_value = MagicMock(choices=[MagicMock(message=MagicMock(content="Result"))])
        anthropic_factory.return_value.messages.create.return_value = MagicMock(content=[MagicMock(text="Result")])
        google_factory.return_value.chats.create.return_value.send_message.return_value = MagicMock(text="Result")
        ollama_factory.return_value.chat.return_value = {"message": {"content": "Result"}}
        client = LLMClient(model_key="Test", api_key="fake-key", system_prompt=prompt)
        assert client.chat([{"role": "user", "content": "Write a paragraph."}]) == "Result"
        if provider == "openai":
            payload = openai_factory.return_value.chat.completions.create.call_args.kwargs["messages"]
        elif provider == "anthropic":
            payload = anthropic_factory.return_value.messages.create.call_args.kwargs["system"]
        elif provider == "google":
            payload = google_factory.return_value.chats.create.call_args.kwargs["config"]["system_instruction"]
        else:
            payload = ollama_factory.return_value.chat.call_args.kwargs["messages"]
        assert str(payload).count("DISTINCTIVE_STYLE_RULE") == 1


def test_gemini_system_prompt():
    mapping = {
        "Gemini Test": {
            "name": "gemini-test",
            "type": "cloud",
            "provider": "google",
        }
    }
    with (
        patch("llm.client.get_model_mapping", return_value=mapping),
        patch("llm.client.genai.Client") as client_factory,
    ):
        provider = client_factory.return_value
        chat = MagicMock()
        provider.chats.create.return_value = chat
        chat.send_message.return_value = MagicMock(text="test response")

        client = LLMClient(model_key="Gemini Test", api_key="test-key")
        assert client.chat([{"role": "user", "content": "hello"}]) == "test response"

        client_factory.assert_called_once_with(api_key="test-key")
        config = provider.chats.create.call_args.kwargs["config"]
        assert config["system_instruction"] == SYSTEM_PROMPT


def test_ollama_cloud_system_prompt():
    mapping = {
        "Ollama Cloud Test": {
            "name": "writer-test",
            "type": "cloud",
            "provider": "ollama_cloud",
            "host": "https://ollama.example",
        }
    }
    with (
        patch("llm.client.get_model_mapping", return_value=mapping),
        patch("llm.client.ollama.Client") as client_factory,
    ):
        provider = client_factory.return_value
        provider.chat.return_value = {"message": {"content": "test response"}}

        client = LLMClient(model_key="Ollama Cloud Test", api_key="test-key")
        assert client.chat([{"role": "user", "content": "hello"}]) == "test response"

        messages = provider.chat.call_args.kwargs["messages"]
        assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
