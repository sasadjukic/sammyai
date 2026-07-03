"""Basic model-backed RAG smoke test."""

from rag.rag_system import RAGSystem


def test_indexing(tmp_path):
    story_file = tmp_path / "chapter.md"
    story_file.write_text(
        "Mara steers the airship Meridian through a violent electrical storm.",
        encoding="utf-8",
    )
    rag = RAGSystem(
        persist_dir=str(tmp_path / "index"),
        cache_dir=str(tmp_path / "embeddings"),
    )
    try:
        assert rag.index_file(str(story_file)) is True
        context = rag.get_context("Who steers the Meridian?", top_k=2)
        assert context.chunks
        assert "Mara" in context.format_for_llm()
    finally:
        rag.close()
