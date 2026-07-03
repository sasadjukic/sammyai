from types import SimpleNamespace

from llm.chat_manager import ChatManager, MessageRole


class FakeContextEngine:
    def build_context(self, query, *, cin_context, top_k):
        assert query == "What changed?"
        assert cin_context == "Pinned outline"
        assert top_k == 4
        return SimpleNamespace(
            system_messages=("Project context", "Retrieved context"),
        )


def test_chat_manager_inserts_context_engine_messages_before_conversation():
    manager = ChatManager(context_engine=FakeContextEngine())
    manager.create_session("project-context")
    manager.cin_context = "Pinned outline"
    manager.add_message(MessageRole.USER, "What changed?")

    messages = manager.get_messages_for_llm_with_context(
        query="What changed?",
        top_k=4,
    )

    assert messages == [
        {"role": "system", "content": "Project context"},
        {"role": "system", "content": "Retrieved context"},
        {"role": "user", "content": "What changed?"},
    ]
    assert manager.last_context_result is not None
