"""Model-backed coverage for indexing a larger writing document."""

from rag.rag_system import RAGSystem


def test_large_file_indexing(tmp_path):
    repeated_scene_notes = """
## Harbor confrontation

Mara hides her fear of open water while repairing the Meridian.
Ilya notices that she never looks over the rail during the storm.
The scene should preserve their distrust while hinting at mutual respect.
"""
    story_file = tmp_path / "large_story_notes.md"
    story_file.write_text(repeated_scene_notes * 60, encoding="utf-8")
    assert story_file.stat().st_size > 1_024

    rag = RAGSystem(
        chunk_size=500,
        overlap=50,
        persist_dir=str(tmp_path / "index"),
        cache_dir=str(tmp_path / "embeddings"),
    )
    try:
        assert rag.index_file(str(story_file)) is True
        stats = rag.get_stats()
        assert stats["total_documents"] > 1
        assert stats["indexed_files"] == 1

        context = rag.get_context("Why does Mara avoid the rail?", top_k=3)
        assert context.chunks
        assert any("open water" in chunk.text for chunk in context.chunks)
    finally:
        rag.close()
