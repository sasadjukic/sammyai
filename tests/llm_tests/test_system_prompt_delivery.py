"""Characterization tests for provider-specific system-prompt delivery."""

from unittest.mock import MagicMock, patch

from llm.client import LLMClient, SYSTEM_PROMPT


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
