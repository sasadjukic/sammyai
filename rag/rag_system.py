"""
RAG System - Main interface using separate retriever and context builder modules
"""
from typing import List, Dict, Optional, Set
from pathlib import Path
import hashlib
import logging
import time

# Import our RAG components
try:
    from .indexer import FileIndexer, Document
    from .embeddings import EmbeddingManager
    from .vector_store import VectorStore
    from .retriever import ContextRetriever
    from .context_builder import ContextBuilder, FormattedContext
except ImportError:
    # For standalone testing
    from indexer import FileIndexer, Document
    from embeddings import EmbeddingManager
    from vector_store import VectorStore
    from retriever import ContextRetriever
    from context_builder import ContextBuilder, FormattedContext


logger = logging.getLogger(__name__)


class RAGSystem:
    """Main RAG system that coordinates all components"""
    
    def __init__(self, 
                 chunk_size: int = 300,
                 overlap: int = 30,
                 embedding_model: str = "all-MiniLM-L6-v2",
                 persist_dir: str = "cache/index",
                 cache_dir: str = "cache/embeddings",
                 max_context_tokens: int = 4000,
                 max_documents: int = 1000000,
                 embedding_batch_size: int = 8,
                 max_chunks_per_file: int = 150000):
        """
        Initialize RAG system
        
        Args:
            chunk_size: Size of text chunks in characters
            overlap: Overlap between chunks in characters
            embedding_model: Name of the embedding model to use
            persist_dir: Directory for vector database
            cache_dir: Directory for embedding cache
            max_context_tokens: Maximum tokens for context
            max_documents: Maximum number of chunks in the index
            embedding_batch_size: Batch size for generating embeddings (smaller reduces RAM spikes)
            max_chunks_per_file: Maximum chunks allowed per file to prevent RAM spikes
        """
        logger.info("Initializing RAG system")
        
        # Initialize core components
        self.indexer = FileIndexer(chunk_size=chunk_size, overlap=overlap)
        self.embedding_manager = EmbeddingManager(model_name=embedding_model, cache_dir=cache_dir)
        self.vector_store = VectorStore(persist_directory=persist_dir)
        
        # Initialize retrieval and context building
        self.retriever = ContextRetriever(self.vector_store, self.embedding_manager)
        self.context_builder = ContextBuilder(max_tokens=max_context_tokens)
        self.max_documents = max_documents
        self.embedding_batch_size = embedding_batch_size
        self.max_chunks_per_file = max_chunks_per_file
        
        # Cooldown and caching for get_context
        self._last_context_time = 0
        self._last_context_query = None
        self._last_context_result = None
        self._context_cooldown = 2.0  # seconds
        
        logger.info("RAG system ready")
    
    def _get_file_hash(self, file_path: str) -> str:
        """Generate a cache key for the content and embedding configuration."""
        digest = hashlib.sha256()
        digest.update(str(Path(file_path).absolute()).encode("utf-8"))
        with open(file_path, "rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        digest.update(self.embedding_manager.model_name.encode("utf-8"))
        digest.update(str(self.indexer.chunk_size).encode("ascii"))
        digest.update(str(self.indexer.overlap).encode("ascii"))
        return digest.hexdigest()

    def _invalidate_context_cache(self) -> None:
        self._last_context_time = 0
        self._last_context_query = None
        self._last_context_result = None
    
    def index_file(
        self,
        file_path: str,
        force_reindex: bool = False,
        *,
        project_id: str | None = None,
        relative_path: str | None = None,
        content_hash: str | None = None,
    ) -> bool:
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
            
            # SAFETY CHECK: Document limit
            current_count = self.vector_store.get_document_count()
            if current_count >= self.max_documents and not force_reindex:
                print(f"❌ Document limit reached ({current_count}/{self.max_documents})")
                print("   Clear index with rag.clear_index() or increase max_documents")
                return False
            
            # Check if already indexed (unless force_reindex)
            if not force_reindex:
                existing_files = self.vector_store.get_all_file_paths()
                if file_path in existing_files:
                    logger.info("File already indexed: %s", file_path)
                    return True
            else:
                existing_metadata = self.vector_store.get_file_metadata(file_path)
                if existing_metadata:
                    project_id = project_id or existing_metadata.get("project_id")
                    relative_path = (
                        relative_path or existing_metadata.get("relative_path")
                    )
                # Delete existing chunks for this file
                self.vector_store.delete_by_file(file_path)
                current_count = self.vector_store.get_document_count()
            
            # Step 1: Parse and chunk the file
            logger.info("Parsing and chunking %s", file_path)
            chunks = self.indexer.index_file(file_path)
            if not chunks:
                logger.warning("No chunks created for %s", file_path)
                return False

            for chunk in chunks:
                if project_id is not None:
                    chunk.metadata["project_id"] = project_id
                if relative_path is not None:
                    chunk.metadata["relative_path"] = relative_path
                if content_hash is not None:
                    chunk.metadata["content_hash"] = content_hash
            
            # Limit chunks per file
            if len(chunks) > self.max_chunks_per_file:
                print(f"⚠️ File too large: {len(chunks)} chunks. Limiting to first {self.max_chunks_per_file} chunks.")
                chunks = chunks[:self.max_chunks_per_file]
            
            # SAFETY CHECK: Don't index if it would exceed limit
            if current_count + len(chunks) > self.max_documents:
                print(f"❌ Indexing would exceed limit ({current_count + len(chunks)}/{self.max_documents})")
                return False
            
            # Step 2: Generate embeddings
            texts = [chunk.text for chunk in chunks]
            
            # Try to load from cache
            cache_key = self._get_file_hash(file_path)
            embeddings = self.embedding_manager.load_cached_embeddings(cache_key)
            
            if embeddings is None or len(embeddings) != len(texts):
                # Generate new embeddings
                logger.info(
                    "Generating embeddings for %s chunks (batch size: %s)",
                    len(texts),
                    self.embedding_batch_size,
                )
                embeddings = self.embedding_manager.batch_generate(texts, batch_size=self.embedding_batch_size)
                
                # Cache embeddings
                self.embedding_manager.cache_embeddings(cache_key, embeddings)
            
            # Step 3: Store in vector database
            chunk_ids = [chunk.chunk_id for chunk in chunks]
            metadatas = [chunk.metadata for chunk in chunks]
            
            self.vector_store.add_documents(chunk_ids, texts, embeddings, metadatas)
            self._invalidate_context_cache()
            
            logger.info("Successfully indexed %s", file_path)
            return True
            
        except Exception:
            logger.exception("Error indexing file %s", file_path)
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
            logger.warning("Invalid directory: %s", directory_path)
            return 0
        
        files = path.rglob('*') if recursive else path.glob('*')
        
        indexed_count = 0
        for file_path in files:
            if file_path.is_file() and self.indexer.is_supported_file(str(file_path)):
                if self.index_file(str(file_path)):
                    indexed_count += 1
        
        logger.info("Indexed %s files from %s", indexed_count, directory_path)
        return indexed_count
    
    def remove_file(self, file_path: str) -> None:
        """
        Remove a file from the index
        
        Args:
            file_path: Path to the file to remove
        """
        file_path = str(Path(file_path).absolute())
        self.vector_store.delete_by_file(file_path)
        self._invalidate_context_cache()
        
        # Remove from active files in retriever
        self.retriever.remove_active_file(file_path)
    
    def mark_active_file(self, file_path: str) -> None:
        """
        Mark a file as currently active (open in editor)
        
        Args:
            file_path: Path to the active file
        """
        file_path = str(Path(file_path).absolute())
        self.retriever.add_active_file(file_path)
    
    def unmark_active_file(self, file_path: str) -> None:
        """
        Unmark a file as active (closed in editor)
        
        Args:
            file_path: Path to the file
        """
        file_path = str(Path(file_path).absolute())
        self.retriever.remove_active_file(file_path)
    
    def get_context(self, 
                   query: str, 
                   top_k: int = 5,
                   retrieval_method: str = "vector",
                   format_style: str = "detailed",
                   boost_active_files: bool = True,
                   min_score: float = 0.0,
                   filters: Optional[Dict] = None,
                   project_id: str | None = None) -> FormattedContext:
        """
        Retrieve and format relevant context for a query
        
        Args:
            query: User's query
            top_k: Number of chunks to retrieve
            retrieval_method: "vector", "keyword", or "hybrid"
            format_style: "detailed", "compact", or "minimal"
            boost_active_files: Whether to boost results from active files
            min_score: Minimum relevance score threshold
            filters: Optional metadata filters
            
        Returns:
            FormattedContext object with formatted context
        """
        # Check cooldown and cache
        scoped_filters = dict(filters or {})
        if project_id is not None:
            scoped_filters["project_id"] = project_id
        effective_filters = scoped_filters or None
        cache_key = (
            query,
            top_k,
            retrieval_method,
            format_style,
            boost_active_files,
            min_score,
            repr(effective_filters),
        )

        current_time = time.time()
        if (cache_key == self._last_context_query and
            current_time - self._last_context_time < self._context_cooldown and
            self._last_context_result is not None):
            return self._last_context_result

        # Step 1: Retrieve relevant chunks
        retrieval_results = self.retriever.retrieve(
            query=query,
            top_k=top_k,
            method=retrieval_method,
            filters=effective_filters,
            boost_active_files=boost_active_files,
            min_score=min_score
        )
        
        # Step 2: Build formatted context
        formatted_context = self.context_builder.build_context(
            retrieval_results=retrieval_results,
            query=query,
            include_metadata=True,
            format_style=format_style
        )
        
        # Update cache
        self._last_context_time = current_time
        self._last_context_query = cache_key
        self._last_context_result = formatted_context
        
        return formatted_context
    
    def search_similar(self, 
                      query: str, 
                      top_k: int = 10,
                      file_filter: Optional[str] = None) -> List[Dict]:
        """
        Search for similar content (for UI display)
        
        Args:
            query: Search query
            top_k: Number of results
            file_filter: Optional file extension filter (e.g., ".py")
            
        Returns:
            List of search results with metadata
        """
        filters = None
        if file_filter:
            filters = {"file_extension": file_filter}
        
        results = self.retriever.retrieve(
            query=query,
            top_k=top_k,
            method="vector",
            filters=filters,
            boost_active_files=False,
            min_score=0.0
        )
        
        return [
            {
                'text': r.text,
                'file': Path(r.metadata.get('file_path', '')).name,
                'score': r.score,
                'metadata': r.metadata
            }
            for r in results
        ]
    
    def get_stats(self) -> Dict:
        """Get statistics about the RAG system"""
        indexed_files = self.vector_store.get_all_file_paths()
        
        return {
            'total_documents': self.vector_store.get_document_count(),
            'indexed_files': len(indexed_files),
            'active_files': len(self.retriever.active_files),
            'embedding_dimension': self.embedding_manager.get_embedding_dimension(),
            'files': indexed_files,
            'active_file_list': list(self.retriever.active_files)
        }
    
    def get_file_structure_summary(self) -> str:
        """Get a summary of indexed file structure"""
        indexed_files = self.vector_store.get_all_file_paths()
        return self.context_builder.add_file_structure_summary(indexed_files)
    
    def clear_index(self) -> None:
        """Clear all indexed data"""
        self.vector_store.clear_collection()
        self.embedding_manager.clear_cache()
        self.retriever.active_files.clear()
        self._invalidate_context_cache()
        logger.info("RAG index and embedding cache cleared")

    def close(self) -> None:
        """Release persistent database handles before application shutdown."""
        self.vector_store.close()


# Example usage
if __name__ == "__main__":
    # Initialize RAG system
    rag = RAGSystem()
    
    # Index a file
    success = rag.index_file("example.py")
    print(f"Indexing success: {success}")
    
    # Mark as active
    rag.mark_active_file("example.py")
    
    # Get stats
    stats = rag.get_stats()
    print(f"\nRAG Stats:")
    print(f"  Total chunks: {stats['total_documents']}")
    print(f"  Indexed files: {stats['indexed_files']}")
    print(f"  Active files: {stats['active_files']}")
    
    # Get file structure
    print("\nFile Structure:")
    print(rag.get_file_structure_summary())
    
    # Search with different methods
    query = "How do I handle errors in Python?"
    
    # Vector search with detailed format
    print(f"\n{'='*60}")
    print("DETAILED FORMAT (Vector Search)")
    print('='*60)
    context = rag.get_context(
        query=query,
        top_k=3,
        retrieval_method="vector",
        format_style="detailed",
        boost_active_files=True
    )
    print(context.context_text)
    print(f"\nStats: {context.total_tokens} tokens, Truncated: {context.truncated}")
    
    # Compact format
    print(f"\n{'='*60}")
    print("COMPACT FORMAT")
    print('='*60)
    context = rag.get_context(
        query=query,
        top_k=3,
        format_style="compact"
    )
    print(context.context_text)
