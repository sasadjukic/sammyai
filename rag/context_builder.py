"""
Context Builder - Formats retrieved chunks into a context string for the LLM
"""
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path
try:
    from .retriever import RetrievalResult
except ImportError:
    from retriever import RetrievalResult


@dataclass
class FormattedContext:
    """Represents the final formatted context sent to the LLM"""
    chunks: List[RetrievalResult]
    context_text: str
    total_tokens: int
    truncated: bool = False
    
    def format_for_llm(self) -> str:
        """Returns the context text ready for insertion into a prompt"""
        return self.context_text

class ContextBuilder:
    """Handles formatting and token management of retrieved chunks"""
    
    def __init__(self, max_tokens: int = 4000):
        """
        Initialize the context builder
        
        Args:
            max_tokens: Maximum allowed tokens for the context
        """
        self.max_tokens = max_tokens
        
    def _estimate_tokens(self, text: str) -> int:
        """Rough estimation of token count (4 characters per token)"""
        return len(text) // 4
        
    def build_context(self, 
                      retrieval_results: List[RetrievalResult], 
                      query: str, 
                      include_metadata: bool = True, 
                      format_style: str = "detailed") -> FormattedContext:
        """
        Build a formatted context string from retrieval results
        
        Args:
            retrieval_results: List of chunks retrieved from search
            query: The original user query
            include_metadata: Whether to include file source information
            format_style: Styling of the output ("detailed", "compact", "minimal")
            
        Returns:
            FormattedContext object
        """
        if not retrieval_results:
            return FormattedContext(
                chunks=[],
                context_text="No relevant information found in the project.",
                total_tokens=0,
                truncated=False
            )
            
        context_parts = []
        current_tokens = 0
        used_chunks = []
        truncated = False
        
        # Header
        header = f"Relevant information from project files for query: '{query}'\n\n"
        current_tokens += self._estimate_tokens(header)
        context_parts.append(header)
        
        for i, result in enumerate(retrieval_results):
            # Calculate footer/separator if needed
            separator = "\n" + "-"*40 + "\n"
            
            # Format chunk based on style
            chunk_content = ""
            if format_style == "detailed":
                file_path = result.metadata.get('file_path', 'Unknown')
                file_name = Path(file_path).name
                chunk_index = result.metadata.get('chunk_index', 0)
                relevance = f"{result.score:.2f}"
                
                chunk_header = f"FILE: {file_name} (Source: {file_path})\n"
                chunk_header += f"RELEVANCE: {relevance}\n"
                chunk_header += f"CONTENT:\n"
                chunk_content = chunk_header + result.text + "\n"
                
            elif format_style == "compact":
                file_name = Path(result.metadata.get('file_path', 'unknown')).name
                chunk_content = f"[{file_name}]: {result.text}\n"
                
            else: # minimal
                chunk_content = result.text + "\n"
                
            chunk_tokens = self._estimate_tokens(chunk_content + separator)
            
            if current_tokens + chunk_tokens > self.max_tokens:
                truncated = True
                break
                
            context_parts.append(chunk_content)
            context_parts.append(separator)
            current_tokens += chunk_tokens
            used_chunks.append(result)
            
        context_text = "".join(context_parts)
        
        return FormattedContext(
            chunks=used_chunks,
            context_text=context_text,
            total_tokens=current_tokens,
            truncated=truncated
        )
        
    def add_file_structure_summary(self, indexed_files: List[str]) -> str:
        """Returns a string summarizing the files currently in the index"""
        if not indexed_files:
            return "No files indexed yet."
            
        summary = "Indexed files in project:\n"
        for file in indexed_files:
            summary += f"- {file}\n"
        return summary

if __name__ == "__main__":
    print("ContextBuilder module loaded")
