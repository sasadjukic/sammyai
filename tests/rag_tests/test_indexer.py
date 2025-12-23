import pytest
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from pathlib import Path
import tempfile
from rag.indexer import FileIndexer, Document

@pytest.fixture
def indexer():
    return FileIndexer(chunk_size=100, overlap=20)

def test_is_supported_file(indexer):
    assert indexer.is_supported_file("test.py") is True
    assert indexer.is_supported_file("README.md") is True
    assert indexer.is_supported_file("image.png") is False
    assert indexer.is_supported_file("no_extension") is False

def test_parse_file(indexer):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Hello\nWorld")
        temp_path = f.name
    
    try:
        content = indexer.parse_file(temp_path)
        assert content == "Hello\nWorld"
    finally:
        os.unlink(temp_path)

def test_chunk_text(indexer):
    text = "This is a long sentence that should be split into multiple chunks because it exceeds the chunk size of 100 characters. We need to make sure the overlap works correctly as well."
    metadata = {"file_path": "test.txt"}
    
    chunks = indexer.chunk_text(text, metadata)
    assert len(chunks) > 1
    assert isinstance(chunks[0], Document)
    assert chunks[0].metadata['file_path'] == "test.txt"
    assert chunks[0].metadata['chunk_index'] == 0
    assert chunks[1].metadata['chunk_index'] == 1
    
    # Check if there is overlap
    # The end of chunk 0 should be similar to start of chunk 1 roughly
    # (depending on where the split happened)

def test_index_file(indexer):
    content = "Line 1\nLine 2\nLine 3\n" * 10
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(content)
        temp_path = f.name
    
    try:
        chunks = indexer.index_file(temp_path)
        assert len(chunks) > 0
        assert chunks[0].text.startswith("Line 1")
        assert 'file_path' in chunks[0].metadata
        assert chunks[0].metadata['file_name'].endswith('.py')
    finally:
        os.unlink(temp_path)

def test_index_directory(indexer):
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some files
        f1 = Path(tmpdir) / "file1.py"
        f1.write_text("print('hello')\n" * 20)
        
        f2 = Path(tmpdir) / "file2.txt"
        f2.write_text("Some text here\n" * 20)
        
        f3 = Path(tmpdir) / "unsupported.exe"
        f3.write_text("binary data")
        
        chunks = indexer.index_directory(tmpdir, recursive=False)
        # Should only index .py and .txt
        files_indexed = set(c.metadata['file_name'] for c in chunks)
        assert "file1.py" in files_indexed
        assert "file2.txt" in files_indexed
        assert "unsupported.exe" not in files_indexed
