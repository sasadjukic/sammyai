from types import SimpleNamespace

from rag.rag_system import RAGSystem


def test_embedding_cache_key_changes_with_file_content(tmp_path):
    document = tmp_path / "chapter.md"
    document.write_text("The first version.", encoding="utf-8")

    rag = RAGSystem.__new__(RAGSystem)
    rag.embedding_manager = SimpleNamespace(model_name="test-embeddings")
    rag.indexer = SimpleNamespace(chunk_size=500, overlap=50)

    first_key = rag._get_file_hash(str(document))
    document.write_text("A substantially revised version.", encoding="utf-8")
    second_key = rag._get_file_hash(str(document))

    assert first_key != second_key


def test_embedding_cache_key_changes_with_chunking_configuration(tmp_path):
    document = tmp_path / "chapter.md"
    document.write_text("A stable document.", encoding="utf-8")

    rag = RAGSystem.__new__(RAGSystem)
    rag.embedding_manager = SimpleNamespace(model_name="test-embeddings")
    rag.indexer = SimpleNamespace(chunk_size=500, overlap=50)
    first_key = rag._get_file_hash(str(document))

    rag.indexer.chunk_size = 1_000

    assert rag._get_file_hash(str(document)) != first_key
