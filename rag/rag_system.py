"""
RAG System - Main interface that combines indexing, embeddings, and retrieval
"""
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import hashlib

# Import our RAG components (assuming they're in the same package)
try:
    from .indexer import FileIndexer, Document
    from .embeddings import EmbeddingManager
    from .vector_store import VectorStore
except ImportError:
    # For standalone testing
    from indexer import FileIndexer, Document
    from embeddings import EmbeddingManager
    from vector_store import VectorStore


class RetrievedContext:
    """Represents retrieved context for a query"""
    def __init__(self, chunks: List[Dict], query: str):
        self.chunks = chunks
        self.query = query
    
    def format_for_llm(self, max_chunks: int = 5) -> str:
        """
        Format retrieved context for LLM consumption
        
        Args:
            max_chunks: Maximum number of chunks to include
            
        Returns:
            Formatted context string
        """
        if not self.chunks:
            return ""
        
        context_parts = ["Here is relevant context from the indexed files:"]
        context_parts.append("")
        
        for i, chunk in enumerate(self.chunks[:max_chunks]):
            file_name = Path(chunk['metadata'].get('file_path', 'unknown')).name
            chunk_idx = chunk['metadata'].get('chunk_index', 0)
            score = chunk.get('score', 0)
            
            context_parts.append(f"[Source {i+1}: {file_name} (chunk {chunk_idx}, relevance: {score:.2f})]")
            context_parts.append(chunk['text'])
            context_parts.append("")
        
        return "\n".join(context_parts)


class RAGSystem:
    """Main RAG system that coordinates all components"""
    
    def __init__(self, 
                 chunk_size: int = 500,
                 overlap: int = 50,
                 embedding_model: str = "all-MiniLM-L6-v2",
                 persist_dir: str = "cache/index",
                 cache_dir: str = "cache/embeddings"):
        """
        Initialize RAG system
        
        Args:
            chunk_size: Size of text chunks in characters
            overlap: Overlap between chunks in characters
            embedding_model: Name of the embedding model to use
            persist_dir: Directory for vector database
            cache_dir: Directory for embedding cache
        """
        print("Initializing RAG system...")
        
        # Initialize components
        self.indexer = FileIndexer(chunk_size=chunk_size, overlap=overlap)
        self.embedding_manager = EmbeddingManager(model_name=embedding_model, cache_dir=cache_dir)
        self.vector_store = VectorStore(persist_directory=persist_dir)
        
        # Track active files (files currently open in editor)
        self.active_files = set()
        
        print("RAG system ready")
    
    def _get_file_hash(self, file_path: str) -> str:
        """Generate hash of file path for cache key"""
        return hashlib.md5(file_path.encode()).hexdigest()
    
    def index_file(self, file_path: str, force_reindex: bool = False) -> bool:
        """
        Index a single file
        
        Args:
            file_path: Path to the file
            force_reindex: If True, reindex even if already indexed
            
        Returns:
            True if indexing succeeded, False otherwise
        """
        try:
            file_path = str(Path(file_path).absolute())
            
            # Check if already indexed (unless force_reindex)
            if not force_reindex:
                existing_files = self.vector_store.get_all_file_paths()
                if file_path in existing_files:
                    print(f"File already indexed: {file_path}")
                    return True
            else:
                # Delete existing chunks for this file
                self.vector_store.delete_by_file(file_path)
            
            # Step 1: Parse and chunk the file
            chunks = self.indexer.index_file(file_path)
            if not chunks:
                print(f"No chunks created for {file_path}")
                return False
            
            # Step 2: Generate embeddings
            texts = [chunk.text for chunk in chunks]
            
            # Try to load from cache
            cache_key = self._get_file_hash(file_path)
            embeddings = self.embedding_manager.load_cached_embeddings(cache_key)
            
            if embeddings is None or len(embeddings) != len(texts):
                # Generate new embeddings
                print(f"Generating embeddings for {len(texts)} chunks...")
                embeddings = self.embedding_manager.batch_generate(texts)
                
                # Cache embeddings
                self.embedding_manager.cache_embeddings(cache_key, embeddings)
            
            # Step 3: Store in vector database
            chunk_ids = [chunk.chunk_id for chunk in chunks]
            metadatas = [chunk.metadata for chunk in chunks]
            
            self.vector_store.add_documents(chunk_ids, texts, embeddings, metadatas)
            
            print(f"Successfully indexed {file_path}")
            return True
            
        except Exception as e:
            print(f"Error indexing file {file_path}: {e}")
            return False
    
    def index_directory(self, directory_path: str, recursive: bool = True) -> int:
        """
        Index all supported files in a directory
        
        Args:
            directory_path: Path to directory
            recursive: Whether to index subdirectories
            
        Returns:
            Number of files successfully indexed
        """
        path = Path(directory_path)
        if not path.exists() or not path.is_dir():
            print(f"Invalid directory: {directory_path}")
            return 0
        
        files = path.rglob('*') if recursive else path.glob('*')
        
        indexed_count = 0
        for file_path in files:
            if file_path.is_file() and self.indexer.is_supported_file(str(file_path)):
                if self.index_file(str(file_path)):
                    indexed_count += 1
        
        print(f"Indexed {indexed_count} files from {directory_path}")
        return indexed_count
    
    def remove_file(self, file_path: str) -> None:
        """
        Remove a file from the index
        
        Args:
            file_path: Path to the file to remove
        """
        file_path = str(Path(file_path).absolute())
        self.vector_store.delete_by_file(file_path)
        
        # Clear cache
        cache_key = self._get_file_hash(file_path)
        # Note: We don't delete the cache file, just let it be overwritten if needed
        
        # Remove from active files
        self.active_files.discard(file_path)
    
    def mark_active_file(self, file_path: str) -> None:
        """
        Mark a file as currently active (open in editor)
        
        Args:
            file_path: Path to the active file
        """
        file_path = str(Path(file_path).absolute())
        self.active_files.add(file_path)
    
    def unmark_active_file(self, file_path: str) -> None:
        """
        Unmark a file as active (closed in editor)
        
        Args:
            file_path: Path to the file
        """
        file_path = str(Path(file_path).absolute())
        self.active_files.discard(file_path)
    
    def get_context(self, query: str, top_k: int = 5, boost_active: bool = True) -> RetrievedContext:
        """
        Retrieve relevant context for a query
        
        Args:
            query: User's query
            top_k: Number of chunks to retrieve
            boost_active: Whether to boost results from active files
            
        Returns:
            RetrievedContext object with retrieved chunks
        """
        # Generate query embedding
        query_embedding = self.embedding_manager.generate_embedding(query)
        
        # Search vector store
        ids, texts, metadatas, scores = self.vector_store.search(
            query_embedding, 
            top_k=top_k * 2 if boost_active else top_k  # Get more if boosting
        )
        
        # Combine results
        chunks = []
        for chunk_id, text, metadata, score in zip(ids, texts, metadatas, scores):
            # Boost score if from active file
            if boost_active and metadata.get('file_path') in self.active_files:
                score = score * 1.5  # 50% boost for active files
            
            chunks.append({
                'id': chunk_id,
                'text': text,
                'metadata': metadata,
                'score': score
            })
        
        # Re-sort by score after boosting
        if boost_active:
            chunks.sort(key=lambda x: x['score'], reverse=True)
        
        # Take top_k after boosting
        chunks = chunks[:top_k]
        
        return RetrievedContext(chunks, query)
    
    def get_stats(self) -> Dict:
        """Get statistics about the RAG system"""
        indexed_files = self.vector_store.get_all_file_paths()
        
        return {
            'total_documents': self.vector_store.get_document_count(),
            'indexed_files': len(indexed_files),
            'active_files': len(self.active_files),
            'embedding_dimension': self.embedding_manager.get_embedding_dimension(),
            'files': indexed_files
        }
    
    def clear_index(self) -> None:
        """Clear all indexed data"""
        self.vector_store.clear_collection()
        self.embedding_manager.clear_cache()
        self.active_files.clear()
        print("Index and cache cleared")


# Example usage
if __name__ == "__main__":
    # Initialize RAG system
    rag = RAGSystem()
    
    # Index a file
    success = rag.index_file("example.py")
    print(f"Indexing success: {success}")
    
    # Get stats
    stats = rag.get_stats()
    print(f"\nRAG Stats:")
    print(f"  Total chunks: {stats['total_documents']}")
    print(f"  Indexed files: {stats['indexed_files']}")
    print(f"  Files: {stats['files']}")
    
    # Search for context
    query = "How do I handle errors in Python?"
    context = rag.get_context(query, top_k=3)
    
    print(f"\nQuery: {query}")
    print(f"Retrieved {len(context.chunks)} chunks")
    
    print("\nFormatted context for LLM:")
    print(context.format_for_llm())
