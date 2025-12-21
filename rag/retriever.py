"""
Retriever - Handles searching and ranking of text chunks
"""
from typing import List, Dict, Optional, Set, NamedTuple, Tuple
import numpy as np
from pathlib import Path

class RetrievalResult(NamedTuple):
    """Represents a single retrieval result"""
    chunk_id: str
    text: str
    metadata: Dict
    score: float

class ContextRetriever:
    """Coordinates search across vector store with additional ranking logic"""
    
    def __init__(self, vector_store, embedding_manager):
        """
        Initialize the retriever
        
        Args:
            vector_store: Initialized VectorStore instance
            embedding_manager: Initialized EmbeddingManager instance
        """
        self.vector_store = vector_store
        self.embedding_manager = embedding_manager
        self.active_files: Set[str] = set()
        
    def add_active_file(self, file_path: str) -> None:
        """Add a file to the active files list (boosted in search)"""
        self.active_files.add(str(Path(file_path).absolute()))
        
    def remove_active_file(self, file_path: str) -> None:
        """Remove a file from the active files list"""
        abs_path = str(Path(file_path).absolute())
        if abs_path in self.active_files:
            self.active_files.remove(abs_path)
            
    def retrieve(self, 
                 query: str, 
                 top_k: int = 5, 
                 method: str = "vector",
                 filters: Optional[Dict] = None,
                 boost_active_files: bool = True,
                 min_score: float = 0.0) -> List[RetrievalResult]:
        """
        Retrieve relevant chunks for a query
        
        Args:
            query: User's search query
            top_k: Number of results to return
            method: Retrieval method ("vector" is currently supported)
            filters: Metadata filters for the search
            boost_active_files: Whether to boost results from active files
            min_score: Minimum threshold for relevance score
            
        Returns:
            List of RetrievalResult objects
        """
        if not query or not query.strip():
            return []
            
        # Step 1: Generate query embedding
        query_embedding = self.embedding_manager.generate_embedding(query)
        
        # Step 2: Search vector store
        # we retrieve more than top_k initially if we plan to re-rank/boost
        search_k = top_k * 2 if boost_active_files else top_k
        
        ids, documents, metadatas, similarities = self.vector_store.search(
            query_embedding=query_embedding,
            top_k=search_k,
            where=filters
        )
        
        results = []
        for i in range(len(ids)):
            score = similarities[i]
            metadata = metadatas[i]
            
            # Step 3: Apply boosting for active files
            if boost_active_files:
                file_path = metadata.get('file_path')
                if file_path in self.active_files:
                    # Apply a 20% boost to active files
                    score = min(1.0, score * 1.2)
            
            # Step 4: Filter by min_score
            if score >= min_score:
                results.append(RetrievalResult(
                    chunk_id=ids[i],
                    text=documents[i],
                    metadata=metadata,
                    score=score
                ))
                
        # Step 5: Sort by boosted score and return top_k
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

if __name__ == "__main__":
    # Minimal test if run standalone
    print("ContextRetriever module loaded")
