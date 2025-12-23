import pytest
import numpy as np
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from pathlib import Path
from rag.vector_store import VectorStore

import tempfile

@pytest.fixture
def persist_dir():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir

@pytest.fixture
def store(persist_dir):
    return VectorStore(persist_directory=persist_dir, collection_name="test_collection")

def test_initialization(store, persist_dir):
    assert str(store.persist_directory) == persist_dir
    assert store.collection_name == "test_collection"
    assert store.get_document_count() == 0

def test_add_documents(store):
    chunk_ids = ["id1", "id2"]
    texts = ["Text 1", "Text 2"]
    embeddings = [np.random.rand(384) for _ in range(2)]
    metadatas = [
        {"file_path": "file1.txt", "chunk_index": 0},
        {"file_path": "file2.txt", "chunk_index": 0}
    ]
    
    store.add_documents(chunk_ids, texts, embeddings, metadatas)
    assert store.get_document_count() == 2
    assert "file1.txt" in store.get_all_file_paths()
    assert "file2.txt" in store.get_all_file_paths()

def test_search(store):
    chunk_ids = ["id1", "id2"]
    texts = ["How to bake a cake", "The theory of relativity"]
    # Create very different embeddings
    emb1 = np.zeros(384)
    emb1[0] = 1.0
    emb2 = np.zeros(384)
    emb2[1] = 1.0
    
    embeddings = [emb1, emb2]
    metadatas = [{"topic": "cooking"}, {"topic": "physics"}]
    
    store.add_documents(chunk_ids, texts, embeddings, metadatas)
    
    # Search for cooking
    ids, docs, metas, scores = store.search(emb1, top_k=1)
    assert len(ids) == 1
    assert ids[0] == "id1"
    assert docs[0] == "How to bake a cake"
    
    # Test metadata filter
    ids, docs, metas, scores = store.search(emb1, top_k=5, where={"topic": "physics"})
    assert len(ids) == 1
    assert ids[0] == "id2"

def test_delete_document(store):
    store.add_document("id1", "text", np.random.rand(384), {"file_path": "f1"})
    assert store.get_document_count() == 1
    
    store.delete_document("id1")
    assert store.get_document_count() == 0

def test_delete_by_file(store):
    store.add_documents(
        ["id1", "id2"], 
        ["text1", "text2"], 
        [np.random.rand(384), np.random.rand(384)],
        [{"file_path": "f1"}, {"file_path": "f2"}]
    )
    assert store.get_document_count() == 2
    
    store.delete_by_file("f1")
    assert store.get_document_count() == 1
    assert store.get_all_file_paths() == ["f2"]

def test_clear_collection(store):
    store.add_document("id1", "text", np.random.rand(384), {"file_path": "f1"})
    assert store.get_document_count() == 1
    
    store.clear_collection()
    assert store.get_document_count() == 0
    assert store.collection_name == "test_collection"
