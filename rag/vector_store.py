"""
Vector Store - Manages vector database using ChromaDB
"""
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Optional, Tuple
import numpy as np
from pathlib import Path


class VectorStore:
    """Manages vector storage and similarity search using ChromaDB"""
    
    def __init__(self, persist_directory: str = "cache/index", collection_name: str = "documents"):
        """
        Initialize vector store
        
        Args:
            persist_directory: Directory to persist the database
            collection_name: Name of the collection to use
        """
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name
        self._client = None
        self._collection = None

    @property
    def client(self):
        """Lazy-loaded ChromaDB client"""
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=str(self.persist_directory),
                settings=Settings(anonymized_telemetry=False)
            )
        return self._client

    @property
    def collection(self):
        """Lazy-loaded ChromaDB collection"""
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            print(f"Lazy-loaded Chroma collection '{self.collection_name}' with {self._collection.count()} documents")
        return self._collection

    @collection.setter
    def collection(self, value):
        """Allow explicit collection setting (needed for clear_collection)"""
        self._collection = value
    
    def add_documents(self, 
                      chunk_ids: List[str], 
                      texts: List[str], 
                      embeddings: List[np.ndarray], 
                      metadatas: List[Dict]) -> None:
        """
        Add multiple documents to the vector store
        
        Args:
            chunk_ids: List of unique IDs for each chunk
            texts: List of text content
            embeddings: List of embedding vectors
            metadatas: List of metadata dictionaries
        """
        if not chunk_ids or len(chunk_ids) != len(texts) != len(embeddings) != len(metadatas):
            raise ValueError("All input lists must have the same length")
        
        # Convert numpy arrays to lists for ChromaDB
        embeddings_list = [emb.tolist() if isinstance(emb, np.ndarray) else emb 
                          for emb in embeddings]
        
        # ChromaDB expects string values in metadata
        clean_metadatas = []
        for metadata in metadatas:
            clean_meta = {}
            for key, value in metadata.items():
                if isinstance(value, (str, int, float, bool)):
                    clean_meta[key] = value
                else:
                    clean_meta[key] = str(value)
            clean_metadatas.append(clean_meta)
        
        try:
            self.collection.add(
                ids=chunk_ids,
                embeddings=embeddings_list,
                documents=texts,
                metadatas=clean_metadatas
            )
            print(f"Added {len(chunk_ids)} documents to vector store")
        except Exception as e:
            print(f"Error adding documents: {e}")
            raise
    
    def add_document(self, 
                     chunk_id: str, 
                     text: str, 
                     embedding: np.ndarray, 
                     metadata: Dict) -> None:
        """
        Add a single document to the vector store
        
        Args:
            chunk_id: Unique ID for the chunk
            text: Text content
            embedding: Embedding vector
            metadata: Metadata dictionary
        """
        self.add_documents([chunk_id], [text], [embedding], [metadata])
    
    def search(self, 
               query_embedding: np.ndarray, 
               top_k: int = 5,
               where: Optional[Dict] = None) -> Tuple[List[str], List[str], List[Dict], List[float]]:
        """
        Search for similar documents
        
        Args:
            query_embedding: Query embedding vector
            top_k: Number of results to return
            where: Optional metadata filter
            
        Returns:
            Tuple of (ids, documents, metadatas, distances)
        """
        # Convert numpy array to list
        query_list = query_embedding.tolist() if isinstance(query_embedding, np.ndarray) else query_embedding
        
        try:
            results = self.collection.query(
                query_embeddings=[query_list],
                n_results=min(top_k, self.collection.count()),
                where=where
            )
            
            # Extract results
            ids = results['ids'][0] if results['ids'] else []
            documents = results['documents'][0] if results['documents'] else []
            metadatas = results['metadatas'][0] if results['metadatas'] else []
            distances = results['distances'][0] if results['distances'] else []
            
            # Convert distances to similarity scores (1 - distance for cosine)
            similarities = [1 - d for d in distances]
            
            return ids, documents, metadatas, similarities
            
        except Exception as e:
            print(f"Error searching: {e}")
            return [], [], [], []
    
    def delete_document(self, chunk_id: str) -> None:
        """
        Delete a document by ID
        
        Args:
            chunk_id: ID of the chunk to delete
        """
        try:
            self.collection.delete(ids=[chunk_id])
            print(f"Deleted document {chunk_id}")
        except Exception as e:
            print(f"Error deleting document: {e}")
    
    def delete_by_file(self, file_path: str) -> None:
        """
        Delete all chunks belonging to a specific file
        
        Args:
            file_path: Path of the file whose chunks should be deleted
        """
        try:
            # Query all documents from this file
            results = self.collection.get(
                where={"file_path": file_path}
            )
            
            if results['ids']:
                self.collection.delete(ids=results['ids'])
                print(f"Deleted {len(results['ids'])} chunks from {file_path}")
            else:
                print(f"No chunks found for {file_path}")
                
        except Exception as e:
            print(f"Error deleting file chunks: {e}")
    
    def update_document(self, 
                       chunk_id: str, 
                       text: str, 
                       embedding: np.ndarray, 
                       metadata: Dict) -> None:
        """
        Update an existing document
        
        Args:
            chunk_id: ID of the chunk to update
            text: New text content
            embedding: New embedding vector
            metadata: New metadata
        """
        # ChromaDB doesn't have native update, so we delete and re-add
        self.delete_document(chunk_id)
        self.add_document(chunk_id, text, embedding, metadata)
    
    def get_document_count(self) -> int:
        """Get the total number of documents in the store"""
        return self.collection.count()
    
    def get_all_file_paths(self) -> List[str]:
        """Get list of all unique file paths in the store"""
        try:
            results = self.collection.get()
            if results['metadatas']:
                file_paths = set(meta.get('file_path', '') for meta in results['metadatas'])
                return sorted(list(file_paths))
            return []
        except Exception as e:
            print(f"Error getting file paths: {e}")
            return []
    
    def clear_collection(self) -> None:
        """Clear all documents from the collection"""
        try:
            # Delete the collection and recreate it
            self.client.delete_collection(name=self.collection_name)
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            print("Collection cleared")
        except Exception as e:
            print(f"Error clearing collection: {e}")


# Example usage
if __name__ == "__main__":
    # Initialize vector store
    store = VectorStore()
    
    # Example: Add some documents
    chunk_ids = ["chunk1", "chunk2", "chunk3"]
    texts = [
        "Python is a high-level programming language",
        "Machine learning uses algorithms to learn patterns",
        "Vector databases store embeddings efficiently"
    ]
    
    # Create dummy embeddings (in real use, these come from EmbeddingManager)
    embeddings = [np.random.rand(384) for _ in range(3)]
    
    metadatas = [
        {"file_path": "test1.py", "chunk_index": 0},
        {"file_path": "test2.py", "chunk_index": 0},
        {"file_path": "test3.py", "chunk_index": 0}
    ]
    
    # Add documents
    store.add_documents(chunk_ids, texts, embeddings, metadatas)
    
    # Search
    query_embedding = np.random.rand(384)
    ids, docs, metas, scores = store.search(query_embedding, top_k=2)
    
    print(f"\nSearch results:")
    for i, (doc_id, doc, meta, score) in enumerate(zip(ids, docs, metas, scores)):
        print(f"\nResult {i+1}:")
        print(f"  ID: {doc_id}")
        print(f"  Text: {doc[:50]}...")
        print(f"  Score: {score:.4f}")
        print(f"  File: {meta.get('file_path', 'N/A')}")
    
    print(f"\nTotal documents: {store.get_document_count()}")
    print(f"Indexed files: {store.get_all_file_paths()}")