import pytest
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import shutil
from pathlib import Path
import tempfile
from rag.rag_system import RAGSystem, FormattedContext

import tempfile

@pytest.fixture
def rag_dirs():
    with tempfile.TemporaryDirectory() as base_dir:
        base_path = Path(base_dir)
        persist_dir = base_path / "index"
        cache_dir = base_path / "embeddings"
        
        persist_dir.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        yield str(persist_dir), str(cache_dir)

@pytest.fixture
def rag(rag_dirs):
    persist_dir, cache_dir = rag_dirs
    return RAGSystem(
        chunk_size=200, 
        overlap=20, 
        persist_dir=persist_dir, 
        cache_dir=cache_dir
    )

def test_index_file(rag):
    content = "This is a test file for the RAG system. It contains some text that will be indexed."
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(content)
        temp_path = f.name
    
    try:
        success = rag.index_file(temp_path)
        assert success is True
        
        stats = rag.get_stats()
        assert stats['indexed_files'] == 1
        assert stats['total_documents'] > 0
        assert temp_path in stats['files']
    finally:
        os.unlink(temp_path)

def test_get_context(rag):
    # Index two files with different content
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f1:
        f1.write("The capital of France is Paris. It is a beautiful city with many landmarks.")
        p1 = f1.name
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f2:
        f2.write("Python is a popular programming language known for its readability and large ecosystem.")
        p2 = f2.name
        
    try:
        rag.index_file(p1)
        rag.index_file(p2)
        
        # Query about Paris
        context = rag.get_context("What is the capital of France?", top_k=1)
        assert isinstance(context, FormattedContext)
        assert len(context.chunks) == 1
        assert "Paris" in context.chunks[0].text
        
        # Query about Python
        context = rag.get_context("Tell me about Python", top_k=1)
        assert "language" in context.chunks[0].text
    finally:
        os.unlink(p1)
        os.unlink(p2)

def test_active_file_boosting(rag):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f1:
        f1.write("Common topic text that appears in both files for testing.")
        p1 = f1.name
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f2:
        f2.write("Common topic text that appears in both files for testing.")
        p2 = f2.name
        
    try:
        rag.index_file(p1)
        rag.index_file(p2)
        
        # Mark p2 as active
        rag.mark_active_file(p2)
        
        context = rag.get_context("Common topic", top_k=5, boost_active_files=True)
        # The result from p2 should ideally be first due to boosting (since content is identical)
        assert context.chunks[0].metadata['file_path'] == str(Path(p2).absolute())
    finally:
        os.unlink(p1)
        os.unlink(p2)

def test_clear_index(rag):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("content")
        p = f.name
    try:
        rag.index_file(p)
        assert rag.get_stats()['total_documents'] > 0
        
        rag.clear_index()
        assert rag.get_stats()['total_documents'] == 0
    finally:
        os.unlink(p)
