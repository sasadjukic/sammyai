"""
Embedding Manager - Generates vector embeddings for text chunks
"""
import os
# Limit CPU threads for better stability on machines with limited RAM
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"
os.environ["OPENBLAS_NUM_THREADS"] = "4"

from typing import List, Optional
import numpy as np
from sentence_transformers import SentenceTransformer
import pickle
from pathlib import Path


class EmbeddingManager:
    """Manages embedding generation using sentence-transformers"""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", cache_dir: str = "cache/embeddings"):
        """
        Initialize embedding manager
        
        Args:
            model_name: Name of the sentence-transformer model
            cache_dir: Directory to cache embeddings
        """
        self.model_name = model_name
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)
        print(f"Model loaded. Embedding dimension: {self.model.get_sentence_embedding_dimension()}")
    
    def generate_embedding(self, text: str) -> np.ndarray:
        """
        Generate embedding for a single text
        
        Args:
            text: Text to embed
            
        Returns:
            Numpy array of embedding vector
        """
        if not text or not text.strip():
            # Return zero vector for empty text
            dim = self.model.get_sentence_embedding_dimension()
            return np.zeros(dim)
        
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding
    
    def batch_generate(self, texts: List[str], batch_size: int = 32, show_progress: bool = False) -> List[np.ndarray]:
        """
        Generate embeddings for multiple texts efficiently
        
        Args:
            texts: List of texts to embed
            batch_size: Batch size for processing
            show_progress: Whether to show progress bar
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        # Filter out empty texts but keep track of indices
        valid_texts = []
        valid_indices = []
        for i, text in enumerate(texts):
            if text and text.strip():
                valid_texts.append(text)
                valid_indices.append(i)
        
        if not valid_texts:
            # All texts are empty
            dim = self.model.get_sentence_embedding_dimension()
            return [np.zeros(dim) for _ in texts]
        
        # Generate embeddings for valid texts
        embeddings = self.model.encode(
            valid_texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            convert_to_numpy=True
        )
        
        # Reconstruct full list with zero vectors for empty texts
        dim = self.model.get_sentence_embedding_dimension()
        result = [np.zeros(dim) for _ in texts]
        for i, embedding in zip(valid_indices, embeddings):
            result[i] = embedding
        
        return result
    
    def cache_embeddings(self, cache_key: str, embeddings: List[np.ndarray]) -> None:
        """
        Cache embeddings to disk
        
        Args:
            cache_key: Unique key for this cache entry (e.g., file path)
            embeddings: List of embeddings to cache
        """
        cache_file = self.cache_dir / f"{cache_key}.pkl"
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(embeddings, f)
            print(f"Cached embeddings to {cache_file}")
        except Exception as e:
            print(f"Error caching embeddings: {e}")
    
    def load_cached_embeddings(self, cache_key: str) -> Optional[List[np.ndarray]]:
        """
        Load cached embeddings from disk
        
        Args:
            cache_key: Unique key for this cache entry
            
        Returns:
            List of embeddings if cached, None otherwise
        """
        cache_file = self.cache_dir / f"{cache_key}.pkl"
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'rb') as f:
                embeddings = pickle.load(f)
            print(f"Loaded cached embeddings from {cache_file}")
            return embeddings
        except Exception as e:
            print(f"Error loading cached embeddings: {e}")
            return None
    
    def clear_cache(self) -> None:
        """Clear all cached embeddings"""
        for cache_file in self.cache_dir.glob("*.pkl"):
            try:
                cache_file.unlink()
                print(f"Deleted cache file: {cache_file}")
            except Exception as e:
                print(f"Error deleting {cache_file}: {e}")
    
    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings produced by this model"""
        return self.model.get_sentence_embedding_dimension()
    
    def compute_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Compute cosine similarity between two embeddings
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Cosine similarity score (0 to 1)
        """
        # Normalize vectors
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        # Compute cosine similarity
        similarity = np.dot(embedding1, embedding2) / (norm1 * norm2)
        return float(similarity)


# Example usage
if __name__ == "__main__":
    # Initialize embedding manager
    manager = EmbeddingManager()
    
    # Test single embedding
    text = "This is a test sentence for embedding generation."
    embedding = manager.generate_embedding(text)
    print(f"\nSingle embedding shape: {embedding.shape}")
    print(f"First 5 values: {embedding[:5]}")
    
    # Test batch embeddings
    texts = [
        "Python is a programming language",
        "Machine learning is fascinating",
        "Natural language processing uses embeddings"
    ]
    embeddings = manager.batch_generate(texts, show_progress=False)
    print(f"\nBatch embeddings: {len(embeddings)} embeddings generated")
    
    # Test similarity
    similarity = manager.compute_similarity(embeddings[0], embeddings[1])
    print(f"\nSimilarity between text 0 and 1: {similarity:.4f}")
    
    similarity = manager.compute_similarity(embeddings[0], embeddings[2])
    print(f"Similarity between text 0 and 2: {similarity:.4f}")