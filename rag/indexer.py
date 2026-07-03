"""
File Indexer - Handles parsing and chunking of files for RAG system
"""
import os
import subprocess
import logging
from pathlib import Path
from typing import List, Dict, Optional
import hashlib


logger = logging.getLogger(__name__)


class Document:
    """Represents a chunked document with metadata"""
    def __init__(self, chunk_id: str, text: str, metadata: Dict):
        self.chunk_id = chunk_id
        self.text = text
        self.metadata = metadata


class FileIndexer:
    """Indexes files by parsing and chunking them"""
    
    SUPPORTED_EXTENSIONS = {'.txt', '.pdf', '.md'}
    
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
            logger.warning("File not found: %s", file_path)
            return None
        
        if not self.is_supported_file(file_path):
            logger.warning("Unsupported file type: %s", file_path)
            return None
        
        # CRITICAL: Check file size before reading
        file_size = os.path.getsize(file_path)
        max_size = 50 * 1024 * 1024  # 50MB limit
        
        if file_size > max_size:
            print(f"⚠️  Skipping large file: {file_path} ({file_size / 1024:.1f} KB)")
            return None
        
        try:
            ext = Path(file_path).suffix.lower()
            if ext == '.pdf':
                # Use pdftotext to extract content
                result = subprocess.run(['pdftotext', file_path, '-'], capture_output=True, text=True)
                if result.returncode == 0:
                    return result.stdout
                else:
                    logger.error(
                        "Unable to parse PDF %s: pdftotext exited with %s",
                        file_path,
                        result.returncode,
                    )
                    return None
            else:
                # Default text parsing
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    return content
                except UnicodeDecodeError:
                    # Try with different encoding
                    with open(file_path, 'r', encoding='latin-1') as f:
                        content = f.read()
                    return content
        except Exception:
            logger.exception("Error reading file %s", file_path)
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
        
        # Safety: minimum progress per iteration to prevent infinite loops
        min_progress = max(1, self.overlap + 1)
        max_iterations = len(text) // min_progress + 100  # Safety limit
        iteration = 0
        
        while start < len(text):
            iteration += 1
            if iteration > max_iterations:
                print(f"⚠️ Chunking safety limit reached after {iteration} iterations")
                break
            
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
                
                # Only use boundary if it provides sufficient progress
                if break_pos > start + min_progress:
                    end = break_pos + 1
            
            # Ensure we don't go past the text
            end = min(end, len(text))
            
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
            
            # Calculate next start position, ensuring forward progress
            next_start = end - self.overlap
            if next_start <= start:
                next_start = start + min_progress
            start = next_start
        
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
        
        if not chunks:
             logger.warning("No chunks generated from %s", file_path)
        else:
             logger.info("Indexed %s: %s chunks created", file_path, len(chunks))
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
            logger.warning("Invalid directory: %s", directory_path)
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
        
        logger.info(
            "Indexed directory %s: %s total chunks",
            directory_path,
            len(all_chunks),
        )
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
