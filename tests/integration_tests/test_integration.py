"""Integration coverage for RAG context injection into a chat session."""

from pathlib import Path

from llm.chat_manager import ChatManager, MessageRole
from rag.rag_system import RAGSystem


def test_rag_integration(tmp_path: Path):
    story_file = tmp_path / "story_bible.md"
    story_file.write_text(
        """
# Story Bible

Mara is the navigator of the airship Meridian.
She hides her fear of open water from the rest of the crew.
""".strip(),
        encoding="utf-8",
    )

    rag = RAGSystem(
        chunk_size=200,
        overlap=20,
        persist_dir=str(tmp_path / "index"),
        cache_dir=str(tmp_path / "embeddings"),
    )
    try:
        assert rag.index_file(str(story_file)) is True
        rag.mark_active_file(str(story_file))

        stats = rag.get_stats()
        assert stats["indexed_files"] == 1
        assert stats["total_documents"] > 0

        chat_manager = ChatManager(rag_system=rag)
        chat_manager.create_session()
        query = "What is Mara afraid of?"
        chat_manager.add_message(MessageRole.USER, query)

        messages = chat_manager.get_messages_for_llm_with_context(
            query=query,
            top_k=2,
        )

        context_messages = [
            message
            for message in messages
            if message["role"] == "system"
            and "relevant context" in message["content"].lower()
        ]
        assert len(context_messages) == 1
        assert "open water" in context_messages[0]["content"]
    finally:
        rag.close()
