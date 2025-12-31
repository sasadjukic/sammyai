"""
LLM API client for text editor integration.
Starts with a local Ollama instance but eventually may support multiple providers (Gemini, OpenAI, etc.)
"""

from typing import Optional, Dict, List, Callable
from enum import Enum
import ollama
import google.generativeai as genai
# Use a package-relative import so importing `llm.client` works when the package
# is loaded as `llm` (avoids ModuleNotFoundError when running from project root)
from .system_prompt import SYSTEM_PROMPT
# Import API key manager so we can pick up a stored key by default
from api_key_manager import APIKeyManager


# Model configuration
MODEL_MAPPING = {
    "Gemma3:4b": {"name": "gemma3:4b", "type": "local", "provider": "local"},
    "Gemini 2.5 Flash": {"name": "gemini-2.5-flash", "type": "cloud", "provider": "google"},
    "Kimi K2:1T": {"name": "kimi-k2:1t", "type": "cloud", "provider": "ollama"}
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
        self.provider = self.model_config["provider"]
        self.api_key = api_key
        self.system_prompt = system_prompt or SYSTEM_PROMPT
        
        # Validate cloud models have API key
        if self.model_type == ModelType.CLOUD and not self.api_key:
            raise ValueError(f"API key required for cloud model: {model_key}")
        
        self._client = None
        self._google_model = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the appropriate client based on provider."""
        try:
            if self.provider == "google":
                # Initialize Google Generative AI client
                genai.configure(api_key=self.api_key)
                self._google_model = genai.GenerativeModel(self.model_name)
            else:
                # For local models and Ollama-based cloud models
                self._client = ollama.Client()
        except Exception as e:
            raise RuntimeError(f"Failed to initialize client for {self.provider}: {e}")
    
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
        
        # Ensure the system prompt is present at the start.
        # We only skip adding it if the first message is already the system prompt.
        if messages and messages[0].get("role") == "system" and messages[0].get("content") == self.system_prompt:
            return messages
        
        return [{"role": "system", "content": self.system_prompt}] + messages
    
    async def _stream_chat_ollama(
        self,
        messages: List[Dict[str, str]],
        on_token: Callable[[str], None],
        max_tokens: Optional[int] = None,
        temperature: float = 0.9,
        top_p: float = 0.9,
        include_system: bool = True
    ) -> str:
        """Stream chat using Ollama client."""
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
    
    async def _stream_chat_google(
        self,
        messages: List[Dict[str, str]],
        on_token: Callable[[str], None],
        max_tokens: Optional[int] = None,
        temperature: float = 0.9,
        top_p: float = 0.9,
        include_system: bool = True
    ) -> str:
        """Stream chat using Google Generative AI."""
        try:
            # Convert messages to Google format
            google_messages = self._convert_to_google_format(messages, include_system)
            
            # Configure generation settings
            generation_config = {
                "temperature": temperature,
                "top_p": top_p,
            }
            if max_tokens:
                generation_config["max_output_tokens"] = max_tokens
            
            # Start chat session with history
            chat = self._google_model.start_chat(history=google_messages["history"])
            
            # Send the last message and get streaming response
            response = chat.send_message(
                google_messages["last_message"],
                generation_config=generation_config,
                stream=True
            )
            
            full_response = ""
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    on_token(chunk.text)
            
            return full_response
        
        except Exception as e:
            raise RuntimeError(f"Error during streaming chat: {e}")
    
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
        if self.provider == "google":
            return self._chat_google(messages, max_tokens, temperature, top_p, include_system)
        else:
            return self._chat_ollama(messages, max_tokens, temperature, top_p, include_system)
    
    def _chat_ollama(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: float = 0.9,
        top_p: float = 0.9,
        include_system: bool = True
    ) -> str:
        """Chat using Ollama client."""
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
    
    def _chat_google(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: float = 0.9,
        top_p: float = 0.9,
        include_system: bool = True
    ) -> str:
        """Chat using Google Generative AI."""
        try:
            # Convert messages to Google format
            google_messages = self._convert_to_google_format(messages, include_system)
            
            # Configure generation settings
            generation_config = {
                "temperature": temperature,
                "top_p": top_p,
            }
            if max_tokens:
                generation_config["max_output_tokens"] = max_tokens
            
            # Start chat session with history
            chat = self._google_model.start_chat(history=google_messages["history"])
            
            # Send the last message and get response
            response = chat.send_message(
                google_messages["last_message"],
                generation_config=generation_config
            )
            
            return response.text
        
        except Exception as e:
            raise RuntimeError(f"Error during chat: {e}")
    
    def _convert_to_google_format(
        self, 
        messages: List[Dict[str, str]], 
        include_system: bool = True
    ) -> Dict:
        """Convert standard messages to Google Generative AI format.
        
        Google uses a different format:
        - System prompt is set via system_instruction in the model
        - Chat history uses 'user' and 'model' roles (not 'assistant')
        - Messages are in parts format
        """
        prepared_messages = self._prepare_messages(messages, include_system)
        
        history = []
        last_message = ""
        
        for i, msg in enumerate(prepared_messages):
            role = msg["role"]
            content = msg["content"]
            
            # Skip system messages (already in system_instruction)
            if role == "system":
                continue
            
            # Convert 'assistant' to 'model' for Google
            if role == "assistant":
                role = "model"
            
            # Last user message is sent separately
            if i == len(prepared_messages) - 1 and role == "user":
                last_message = content
            else:
                history.append({
                    "role": role,
                    "parts": [content]
                })
        
        return {
            "history": history,
            "last_message": last_message
        }
    
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
        if self.provider == "google":
            return await self._stream_chat_google(messages, on_token, max_tokens, temperature, top_p, include_system)
        else:
            return await self._stream_chat_ollama(messages, on_token, max_tokens, temperature, top_p, include_system)


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
        self._model_key = model_key or self.DEFAULT_MODELS[ModelType.LOCAL]
        self._api_key = api_key
        
        # If an API key is not provided explicitly, attempt to load a stored key
        # from the application's API key manager based on the provider.
        if not self._api_key:
            self._refresh_api_key()
            
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.system_prompt = system_prompt or SYSTEM_PROMPT

    @property
    def model_key(self) -> str:
        return self._model_key

    @model_key.setter
    def model_key(self, value: str):
        if value != self._model_key:
            self._model_key = value
            self._refresh_api_key()

    @property
    def api_key(self) -> Optional[str]:
        return self._api_key

    @api_key.setter
    def api_key(self, value: Optional[str]):
        self._api_key = value

    def _refresh_api_key(self):
        """Refresh the API key based on current model_key provider."""
        model_config = MODEL_MAPPING.get(self._model_key, {})
        provider = model_config.get("provider", "local")
        
        if provider == "local":
            self._api_key = None
        else:
            self._api_key = APIKeyManager.load_api_key(provider)
    
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