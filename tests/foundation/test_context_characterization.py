from types import SimpleNamespace

from llm.chat_manager import ChatManager, MessageRole


class FakeRAG:
    def get_context(self, query, top_k, boost_active_files):
        chunk = SimpleNamespace()
        return SimpleNamespace(
            chunks=[chunk],
            format_for_llm=lambda: "Mara is afraid of open water.",
        )


def test_rag_and_cin_context_precede_conversation_messages():
    manager = ChatManager(rag_system=FakeRAG())
    manager.create_session("context-order")
    manager.cin_context = "The Meridian is an airship."
    manager.add_message(MessageRole.USER, "What does Mara conceal?")

    messages = manager.get_messages_for_llm_with_context(
        query="What does Mara conceal?",
        top_k=3,
    )

    assert [message["role"] for message in messages] == [
        "system",
        "system",
        "user",
    ]
    assert "open water" in messages[0]["content"]
    assert "Meridian" in messages[1]["content"]
    assert messages[2]["content"] == "What does Mara conceal?"
