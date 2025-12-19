"""
File Indexer - Handles parsing and chunking of files for RAG system
"""
import os
from pathlib import Path
from typing import List, Dict, Optional
import hashlib


class Document:
    """Represents a chunked document with metadata"""
    def __init__(self, chunk_id: str, text: str, metadata: Dict):
        self.chunk_id = chunk_id
        self.text = text
        self.metadata = metadata


class FileIndexer:
    """Indexes files by parsing and chunking them"""
    
    SUPPORTED_EXTENSIONS = {
        '.py', '.txt', '.md', '.json', '.yaml', '.yml',
        '.js', '.jsx', '.ts', '.tsx', '.html', '.css',
        '.cpp', '.c', '.h', '.java', '.go', '.rs'
    }
    
    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        """
        Initialize the file indexer
        
        Args:
            chunk_size: Number of characters per chunk
            overlap: Number of overlapping characters between chunks
        """
        self.chunk_size = chunk_size
        self.overlap = overlap
    
    def is_supported_file(self, file_path: str) -> bool:
        """Check if file type is supported"""
        ext = Path(file_path).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS
    
    def parse_file(self, file_path: str) -> Optional[str]:
        """
        Parse file and extract text content
        
        Args:
            file_path: Path to the file
            
        Returns:
            File content as string, or None if parsing fails
        """
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            return None
        
        if not self.is_supported_file(file_path):
            print(f"Unsupported file type: {file_path}")
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return content
        except UnicodeDecodeError:
            # Try with different encoding
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    content = f.read()
                return content
            except Exception as e:
                print(f"Error reading file {file_path}: {e}")
                return None
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return None
    
    def extract_metadata(self, file_path: str) -> Dict:
        """
        Extract metadata from file
        
        Args:
            file_path: Path to the file
            
        Returns:
            Dictionary with file metadata
        """
        path = Path(file_path)
        stat = path.stat()
        
        return {
            'file_path': str(path.absolute()),
            'file_name': path.name,
            'file_extension': path.suffix,
            'file_size': stat.st_size,
            'modified_time': stat.st_mtime,
            'created_time': stat.st_ctime,
        }
    
    def chunk_text(self, text: str, metadata: Dict) -> List[Document]:
        """
        Split text into overlapping chunks
        
        Args:
            text: Text content to chunk
            metadata: File metadata to attach to each chunk
            
        Returns:
            List of Document objects
        """
        if not text or not text.strip():
            return []
        
        chunks = []
        start = 0
        chunk_index = 0
        
        while start < len(text):
            # Calculate end position
            end = start + self.chunk_size
            
            # If not at the end, try to break at a natural boundary
            if end < len(text):
                # Look for paragraph break first
                break_pos = text.rfind('\n\n', start, end)
                if break_pos == -1:
                    # Look for line break
                    break_pos = text.rfind('\n', start, end)
                if break_pos == -1:
                    # Look for sentence end
                    break_pos = text.rfind('. ', start, end)
                if break_pos == -1:
                    # Look for any space
                    break_pos = text.rfind(' ', start, end)
                
                if break_pos > start:
                    end = break_pos + 1
            
            # Extract chunk
            chunk_text = text[start:end].strip()
            
            if chunk_text:
                # Create unique chunk ID
                chunk_id = self._generate_chunk_id(
                    metadata['file_path'], 
                    chunk_index
                )
                
                # Add chunk-specific metadata
                chunk_metadata = metadata.copy()
                chunk_metadata.update({
                    'chunk_index': chunk_index,
                    'start_char': start,
                    'end_char': end,
                    'chunk_length': len(chunk_text)
                })
                
                chunks.append(Document(chunk_id, chunk_text, chunk_metadata))
                chunk_index += 1
            
            # Move to next chunk with overlap
            start = end - self.overlap
            
            # Avoid infinite loop on very small texts
            if start <= 0 and end >= len(text):
                break
        
        return chunks
    
    def _generate_chunk_id(self, file_path: str, chunk_index: int) -> str:
        """Generate unique ID for a chunk"""
        content = f"{file_path}:{chunk_index}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def index_file(self, file_path: str) -> List[Document]:
        """
        Main method to index a file: parse and chunk
        
        Args:
            file_path: Path to the file to index
            
        Returns:
            List of Document chunks
        """
        # Parse file
        content = self.parse_file(file_path)
        if content is None:
            return []
        
        # Extract metadata
        metadata = self.extract_metadata(file_path)
        
        # Chunk the content
        chunks = self.chunk_text(content, metadata)
        
        print(f"Indexed {file_path}: {len(chunks)} chunks created")
        return chunks
    
    def index_directory(self, directory_path: str, recursive: bool = True) -> List[Document]:
        """
        Index all supported files in a directory
        
        Args:
            directory_path: Path to directory
            recursive: Whether to search subdirectories
            
        Returns:
            List of all document chunks from all files
        """
        all_chunks = []
        path = Path(directory_path)
        
        if not path.exists() or not path.is_dir():
            print(f"Invalid directory: {directory_path}")
            return []
        
        # Get all files
        if recursive:
            files = path.rglob('*')
        else:
            files = path.glob('*')
        
        # Index each file
        for file_path in files:
            if file_path.is_file() and self.is_supported_file(str(file_path)):
                chunks = self.index_file(str(file_path))
                all_chunks.extend(chunks)
        
        print(f"Indexed directory {directory_path}: {len(all_chunks)} total chunks")
        return all_chunks


# Example usage
if __name__ == "__main__":
    indexer = FileIndexer(chunk_size=500, overlap=50)
    
    # Index a single file
    chunks = indexer.index_file("example.py")
    
    for i, chunk in enumerate(chunks[:3]):  # Show first 3 chunks
        print(f"\n--- Chunk {i} ---")
        print(f"ID: {chunk.chunk_id}")
        print(f"Text preview: {chunk.text[:100]}...")
        print(f"Metadata: {chunk.metadata}")

