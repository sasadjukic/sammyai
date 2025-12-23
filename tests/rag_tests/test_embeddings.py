import pytest
import numpy as np
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from pathlib import Path
from rag.embeddings import EmbeddingManager

import tempfile

@pytest.fixture
def cache_dir():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir

@pytest.fixture
def manager(cache_dir):
    return EmbeddingManager(model_name="all-MiniLM-L6-v2", cache_dir=cache_dir)

def test_initialization(manager, cache_dir):
    assert manager.model_name == "all-MiniLM-L6-v2"
    assert str(manager.cache_dir) == cache_dir
    assert manager.get_embedding_dimension() > 0

def test_generate_embedding(manager):
    text = "Hello world"
    embedding = manager.generate_embedding(text)
    assert isinstance(embedding, np.ndarray)
    assert embedding.shape == (manager.get_embedding_dimension(),)
    
    # Test empty text
    empty_emb = manager.generate_embedding("")
    assert np.all(empty_emb == 0)

def test_batch_generate(manager):
    texts = ["First sentence", "Second one", ""]
    embeddings = manager.batch_generate(texts, show_progress=False)
    assert len(embeddings) == 3
    assert embeddings[2].shape == (manager.get_embedding_dimension(),)
    assert np.all(embeddings[2] == 0)
    assert not np.all(embeddings[0] == 0)

def test_compute_similarity(manager):
    emb1 = manager.generate_embedding("The cat sits outside")
    emb2 = manager.generate_embedding("A feline is resting outdoors")
    emb3 = manager.generate_embedding("The weather is sunny today")
    
    sim12 = manager.compute_similarity(emb1, emb2)
    sim13 = manager.compute_similarity(emb1, emb3)
    
    assert 0 <= sim12 <= 1
    assert 0 <= sim13 <= 1
    assert sim12 > sim13  # Similar sentences should have higher score

def test_caching(manager):
    texts = ["Cache test 1", "Cache test 2"]
    embeddings = manager.batch_generate(texts, show_progress=False)
    
    cache_key = "test_file_cache"
    manager.cache_embeddings(cache_key, embeddings)
    
    # Check if file exists
    cache_file = manager.cache_dir / f"{cache_key}.pkl"
    assert cache_file.exists()
    
    # Load from cache
    loaded_embeddings = manager.load_cached_embeddings(cache_key)
    assert len(loaded_embeddings) == len(embeddings)
    for original, loaded in zip(embeddings, loaded_embeddings):
        assert np.array_equal(original, loaded)

def test_clear_cache(manager):
    manager.cache_embeddings("t1", [np.zeros(10)])
    manager.cache_embeddings("t2", [np.zeros(10)])
    
    files = list(manager.cache_dir.glob("*.pkl"))
    assert len(files) == 2
    
    manager.clear_cache()
    files = list(manager.cache_dir.glob("*.pkl"))
    assert len(files) == 0
