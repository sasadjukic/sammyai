"""
LLM API client for text editor integration.
Starts with a local Ollama instance but eventually may support multiple providers (Gemini, OpenAI, etc.)
"""

from typing import Optional, Dict, List, Callable
from enum import Enum
import ollama
# Use a package-relative import so importing `llm.client` works when the package
# is loaded as `llm` (avoids ModuleNotFoundError when running from project root)
from .system_prompt import SYSTEM_PROMPT


# Model configuration
MODEL_MAPPING = {
    "Gemma3:4b": {"name": "gemma3:4b", "type": "local"},
    "Kimi K2:1T": {"name": "kimi-k2:1t", "type": "cloud"}
}


class ModelType(Enum):
    """Enum for model types."""
    LOCAL = "local"
    CLOUD = "cloud"


class LLMClient:
    """Client for LLM API interactions using Ollama."""
    
    def __init__(
        self, 
        model_key: str = "Gemma3:4b",
        api_key: Optional[str] = None,
        system_prompt: Optional[str] = None
    ):
        """
        Initialize the LLM client.
        
        Args:
            model_key: Key from MODEL_MAPPING (e.g., "Gemma3:4b" or "Kimi K2:1T")
            api_key: API key for cloud models (required for cloud models)
            system_prompt: Custom system prompt (defaults to SYSTEM_PROMPT from system_prompt.py)
        """
        if model_key not in MODEL_MAPPING:
            raise ValueError(f"Invalid model_key. Must be one of: {list(MODEL_MAPPING.keys())}")
        
        self.model_key = model_key
        self.model_config = MODEL_MAPPING[model_key]
        self.model_name = self.model_config["name"]
        self.model_type = ModelType(self.model_config["type"])
        self.api_key = api_key
        self.system_prompt = system_prompt or SYSTEM_PROMPT
        
        # Validate cloud models have API key
        if self.model_type == ModelType.CLOUD and not self.api_key:
            raise ValueError(f"API key required for cloud model: {model_key}")
        
        self._client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the Ollama client."""
        try:
            # For local models, use default Ollama client
            if self.model_type == ModelType.LOCAL:
                self._client = ollama.Client()
            # For cloud models, configure with API key if needed
            else:
                # Cloud models via Ollama may require custom configuration
                self._client = ollama.Client()
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Ollama client: {e}")
    
    def _prepare_messages(
        self, 
        messages: List[Dict[str, str]], 
        include_system: bool = True
    ) -> List[Dict[str, str]]:
        """
        Prepare messages with system prompt.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            include_system: Whether to include system prompt
            
        Returns:
            Messages list with system prompt prepended if needed
        """
        if not include_system:
            return messages
        
        # Check if system message already exists
        has_system = any(msg.get("role") == "system" for msg in messages)
        
        if not has_system:
            return [{"role": "system", "content": self.system_prompt}] + messages
        
        return messages
    
    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        on_token: Callable[[str], None],
        max_tokens: Optional[int] = None,
        temperature: float = 0.9,
        top_p: float = 0.9,
        include_system: bool = True
    ) -> str:
        """
        Stream chat completion and call on_token for each token.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            on_token: Callback function called with each token
            max_tokens: Maximum tokens to generate (optional)
            temperature: Sampling temperature (default: 0.9)
            top_p: Top-p sampling parameter (default: 0.9)
            include_system: Whether to include system prompt (default: True)
            
        Returns:
            Complete response text
        """
        prepared_messages = self._prepare_messages(messages, include_system)
        full_response = ""
        
        try:
            # Build options dict
            options = {
                "temperature": temperature,
                "top_p": top_p,
            }
            if max_tokens:
                options["num_predict"] = max_tokens
            
            # Stream response from Ollama
            stream = self._client.chat(
                model=self.model_name,
                messages=prepared_messages,
                stream=True,
                options=options
            )
            
            for chunk in stream:
                if "message" in chunk and "content" in chunk["message"]:
                    token = chunk["message"]["content"]
                    full_response += token
                    on_token(token)
        
        except Exception as e:
            raise RuntimeError(f"Error during streaming chat: {e}")
        
        return full_response
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: float = 0.9,
        top_p: float = 0.9,
        include_system: bool = True
    ) -> str:
        """
        Non-streaming chat completion.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens to generate (optional)
            temperature: Sampling temperature (default: 0.9)
            top_p: Top-p sampling parameter (default: 0.9)
            include_system: Whether to include system prompt (default: True)
            
        Returns:
            Complete response text
        """
        prepared_messages = self._prepare_messages(messages, include_system)
        
        try:
            # Build options dict
            options = {
                "temperature": temperature,
                "top_p": top_p,
            }
            if max_tokens:
                options["num_predict"] = max_tokens
            
            # Get response from Ollama
            response = self._client.chat(
                model=self.model_name,
                messages=prepared_messages,
                stream=False,
                options=options
            )
            
            return response["message"]["content"]
        
        except Exception as e:
            raise RuntimeError(f"Error during chat: {e}")


class LLMConfig:
    """Configuration for LLM client."""
    
    DEFAULT_MODELS = {
        ModelType.LOCAL: "Gemma3:4b",
        ModelType.CLOUD: "Kimi K2:1T",
    }
    
    def __init__(
        self,
        model_key: Optional[str] = None,
        api_key: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.9,
        top_p: float = 0.9,
        system_prompt: Optional[str] = None
    ):
        """
        Initialize LLM configuration.
        
        Args:
            model_key: Key from MODEL_MAPPING (defaults to local model)
            api_key: API key for cloud models
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (default: 0.9)
            top_p: Top-p sampling parameter (default: 0.9)
            system_prompt: Custom system prompt (defaults to SYSTEM_PROMPT)
        """
        self.model_key = model_key or self.DEFAULT_MODELS[ModelType.LOCAL]
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.system_prompt = system_prompt or SYSTEM_PROMPT
    
    def create_client(self) -> LLMClient:
        """
        Create an LLMClient instance from this configuration.
        
        Returns:
            Configured LLMClient instance
        """
        return LLMClient(
            model_key=self.model_key,
            api_key=self.api_key,
            system_prompt=self.system_prompt
        )