"""
LLM API client for text editor integration.
"""

from typing import Optional, Dict, List, Callable, Any
from enum import Enum
import ollama
from google import genai
# Use a package-relative import so importing `llm.client` works when the package
# is loaded as `llm` (avoids ModuleNotFoundError when running from project root)
from .system_prompt import SYSTEM_PROMPT
# Import API key manager so we can pick up a stored key by default
from api_key_manager import APIKeyManager


from api_key_manager import APIKeyManager

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    import openai
except ImportError:
    openai = None


def build_model_mapping() -> dict:
    """Build a dynamic model mapping from stored settings."""
    providers = {
        "local":        {"type": "local"},
        "anthropic":    {"type": "cloud"},
        "google":       {"type": "cloud"},
        "openai":       {"type": "cloud"},
        "ollama_cloud": {"type": "cloud", "host": "https://ollama.com"},
    }
    mapping = {}
    for provider, meta in providers.items():
        models = APIKeyManager.load_models(provider)
        for model_name in models:
            # Visual tweak: Show 'ollama' instead of 'ollama_cloud' in UI
            display_provider = "ollama" if provider == "ollama_cloud" else provider
            display_key = f"{model_name} ({display_provider})"
            mapping[display_key] = {
                "name": model_name,
                "type": meta["type"],
                "provider": provider,
                "host": meta.get("host") 
            }

    return mapping


# Default placeholder if no models are configured
DEFAULT_MODEL_MAPPING = {
    "Configure Models": {"name": "none", "type": "local", "provider": "local"}
}


def get_model_mapping() -> dict:
    """Get the current model mapping, or default placeholder if empty."""
    mapping = build_model_mapping()
    return mapping if mapping else DEFAULT_MODEL_MAPPING



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
            model_key: Key from MODEL_MAPPING (e.g., "Gemma3:4b", "Kimi K2:1T", etc...)
            api_key: API key for cloud models (required for cloud models)
            system_prompt: Custom system prompt (defaults to SYSTEM_PROMPT from system_prompt.py)
        """
        mapping = get_model_mapping()
        if model_key not in mapping:
            # If not in mapping, try to use the first available model
            if mapping:
                model_key = list(mapping.keys())[0]
            else:
                raise ValueError(f"Invalid model_key and no models configured.")
        
        self.model_key = model_key
        self.model_config = mapping[model_key]

        self.model_name = self.model_config["name"]
        self.model_type = ModelType(self.model_config["type"])
        self.provider = self.model_config["provider"]
        self.api_key = api_key
        self.system_prompt = system_prompt or SYSTEM_PROMPT
        self.temperature = 0.9
        self.top_p = 0.9
        
        # Validate cloud models have API key
        if self.model_type == ModelType.CLOUD and not self.api_key:
            raise ValueError(f"API key required for cloud model: {model_key}")
        
        self._client = None
        self._google_client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the appropriate client based on provider."""
        try:
            if self.provider == "google":
                # Initialize Google Gen AI client
                self._google_client = genai.Client(api_key=self.api_key)
            elif self.provider == "ollama_cloud":
                # For cloud-hosted Ollama models
                self._client = ollama.Client(
                    host=self.model_config.get("host", "https://ollama.com"),
                    headers={'Authorization': self.api_key}
                )
            elif self.provider == "anthropic":
                if anthropic is None:
                    raise ImportError("anthropic package not installed")
                self._anthropic_client = anthropic.Anthropic(api_key=self.api_key)
            elif self.provider == "openai":
                if openai is None:
                    raise ImportError("openai package not installed")
                self._openai_client = openai.OpenAI(api_key=self.api_key)
            else:
                # For local Ollama models (provider == "local")
                self._client = ollama.Client()

        except Exception as e:
            raise RuntimeError(f"Failed to initialize client for {self.provider}: {e}")
    
    def _decompose_messages(
        self, 
        messages: List[Dict[str, str]], 
        include_system: bool = True
    ) -> Dict[str, Any]:
        """
        Decompose messages into primary system prompt, extra context, and user/assistant messages.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            include_system: Whether to include the base system prompt
            
        Returns:
            Dict containing 'primary_system', 'extra_system', and 'other_messages'
        """
        primary_system = self.system_prompt if include_system else ""
        extra_system = []
        other_messages = []
        
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            
            if role == "system":
                if content and content != self.system_prompt:
                    extra_system.append(content)
            else:
                other_messages.append(msg)
                
        return {
            "primary_system": primary_system,
            "extra_system": extra_system,
            "other_messages": other_messages
        }

    def _prepare_messages(
        self, 
        messages: List[Dict[str, str]], 
        include_system: bool = True
    ) -> List[Dict[str, str]]:
        """
        Prepare messages with consolidated system prompt.
        
        Collects all system messages into a single combined system message at the start.
        This provides better compatibility with some cloud models like DeepSeek.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            include_system: Whether to include the base system prompt
            
        Returns:
            Messages list with consolidated system prompt prepended
        """
        decomposed = self._decompose_messages(messages, include_system)
        
        system_contents = []
        if decomposed["primary_system"]:
            system_contents.append(decomposed["primary_system"])
        
        system_contents.extend(decomposed["extra_system"])
        
        if not system_contents:
            return decomposed["other_messages"]
            
        # Join all system instructions into one block
        combined_system = "\n\n".join(system_contents)
        return [{"role": "system", "content": combined_system}] + decomposed["other_messages"]
    
    async def _stream_chat_ollama(
        self,
        messages: List[Dict[str, str]],
        on_token: Callable[[str], None],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        include_system: bool = True
    ) -> str:
        """Stream chat using Ollama client."""
        # For local models (like Gemma), we prepend extra context to the user message
        # as they often handle consolidated system prompts poorly.
        # For 'ollama' provider (cloud-hosted), we stick to consolidated system prompt.
        if self.provider == "local":
            prepared_messages = self._prepare_messages_decomposed(messages, include_system)
        else:
            prepared_messages = self._prepare_messages(messages, include_system)
            
        full_response = ""
        
        try:
            # Build options dict
            options = {
                "temperature": temperature if temperature is not None else self.temperature,
                "top_p": top_p if top_p is not None else self.top_p,
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
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        include_system: bool = True
    ) -> str:
        """Stream chat using Google Gen AI SDK."""
        try:
            # Convert messages to Google format
            google_messages = self._convert_to_google_format(messages, include_system)
            
            # Configure generation config
            config = {
                "temperature": temperature if temperature is not None else self.temperature,
                "top_p": top_p if top_p is not None else self.top_p,
                "system_instruction": self.system_prompt
            }
            if max_tokens:
                config["max_output_tokens"] = max_tokens
            
            # Start chat session with history
            chat = self._google_client.chats.create(
                model=self.model_name,
                history=google_messages["history"],
                config=config
            )
            
            # Send the last message and get streaming response
            response = chat.send_message(
                google_messages["last_message"],
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
    
    async def _stream_chat_anthropic(
        self,
        messages: List[Dict[str, str]],
        on_token: Callable[[str], None],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        include_system: bool = True
    ) -> str:
        """Stream chat using Anthropic SDK."""
        try:
            decomposed = self._decompose_messages(messages, include_system)
            system_prompt = "\n\n".join([decomposed["primary_system"]] + decomposed["extra_system"])
            
            with self._anthropic_client.messages.stream(
                model=self.model_name,
                max_tokens=max_tokens or 4096,
                temperature=temperature if temperature is not None else self.temperature,
                system=system_prompt,
                messages=decomposed["other_messages"]
            ) as stream:
                full_response = ""
                for text in stream.text_stream:
                    full_response += text
                    on_token(text)
                return full_response
        except Exception as e:
            raise RuntimeError(f"Error during Anthropic streaming: {e}")

    async def _stream_chat_openai(
        self,
        messages: List[Dict[str, str]],
        on_token: Callable[[str], None],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        include_system: bool = True
    ) -> str:
        """Stream chat using OpenAI SDK."""
        try:
            prepared_messages = self._prepare_messages(messages, include_system)
            stream = self._openai_client.chat.completions.create(
                model=self.model_name,
                messages=prepared_messages,
                max_tokens=max_tokens,
                temperature=temperature if temperature is not None else self.temperature,
                top_p=top_p if top_p is not None else self.top_p,
                stream=True
            )
            full_response = ""
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_response += token
                    on_token(token)
            return full_response
        except Exception as e:
            raise RuntimeError(f"Error during OpenAI streaming: {e}")

    
    def chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        include_system: bool = True
    ) -> str:
        """
        Non-streaming chat completion.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens to generate (optional)
            temperature: Sampling temperature (None to use instance default)
            top_p: Top-p sampling parameter (None to use instance default)
            include_system: Whether to include system prompt (default: True)
            
        Returns:
            Complete response text
        """
        if self.provider == "google":
            return self._chat_google(messages, max_tokens, temperature, top_p, include_system)
        elif self.provider == "anthropic":
            return self._chat_anthropic(messages, max_tokens, temperature, top_p, include_system)
        elif self.provider == "openai":
            return self._chat_openai(messages, max_tokens, temperature, top_p, include_system)
        else:
            return self._chat_ollama(messages, max_tokens, temperature, top_p, include_system)

    
    def _chat_ollama(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        include_system: bool = True
    ) -> str:
        """Chat using Ollama client."""
        # For local models (like Gemma), we prepend extra context to the user message
        # as they often handle consolidated system prompts poorly.
        # For 'ollama' provider (cloud-hosted), we stick to consolidated system prompt.
        if self.provider == "local":
            prepared_messages = self._prepare_messages_decomposed(messages, include_system)
        else:
            prepared_messages = self._prepare_messages(messages, include_system)
        
        try:
            # Build options dict
            options = {
                "temperature": temperature if temperature is not None else self.temperature,
                "top_p": top_p if top_p is not None else self.top_p,
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
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        include_system: bool = True
    ) -> str:
        """Chat using Google Gen AI SDK."""
        try:
            # Convert messages to Google format
            google_messages = self._convert_to_google_format(messages, include_system)
            
            # Configure generation config
            config = {
                "temperature": temperature if temperature is not None else self.temperature,
                "top_p": top_p if top_p is not None else self.top_p,
                "system_instruction": self.system_prompt
            }
            if max_tokens:
                config["max_output_tokens"] = max_tokens
            
            # Start chat session with history
            chat = self._google_client.chats.create(
                model=self.model_name,
                history=google_messages["history"],
                config=config
            )
            
            # Send the last message and get response
            response = chat.send_message(
                google_messages["last_message"]
            )
            
            return response.text
        
        except Exception as e:
            raise RuntimeError(f"Error during chat: {e}")

    def _chat_anthropic(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        include_system: bool = True
    ) -> str:
        """Chat using Anthropic SDK."""
        try:
            decomposed = self._decompose_messages(messages, include_system)
            system_prompt = "\n\n".join([decomposed["primary_system"]] + decomposed["extra_system"])
            
            response = self._anthropic_client.messages.create(
                model=self.model_name,
                max_tokens=max_tokens or 4096,
                temperature=temperature if temperature is not None else self.temperature,
                system=system_prompt,
                messages=decomposed["other_messages"]
            )
            return response.content[0].text
        except Exception as e:
            raise RuntimeError(f"Error during Anthropic chat: {e}")

    def _chat_openai(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        include_system: bool = True
    ) -> str:
        """Chat using OpenAI SDK."""
        try:
            prepared_messages = self._prepare_messages(messages, include_system)
            response = self._openai_client.chat.completions.create(
                model=self.model_name,
                messages=prepared_messages,
                max_tokens=max_tokens,
                temperature=temperature if temperature is not None else self.temperature,
                top_p=top_p if top_p is not None else self.top_p
            )
            return response.choices[0].message.content
        except Exception as e:
            raise RuntimeError(f"Error during OpenAI chat: {e}")

    
    def _convert_to_google_format(
        self, 
        messages: List[Dict[str, str]], 
        include_system: bool = True
    ) -> Dict:
        """Convert standard messages to Google Generative AI format."""
        decomposed = self._decompose_messages(messages, include_system)
        
        history = []
        last_message = ""
        
        other_messages = decomposed["other_messages"]
        for i, msg in enumerate(other_messages):
            role = msg["role"]
            content = msg["content"]
            
            # Convert 'assistant' to 'model' for Google
            if role == "assistant":
                role = "model"
            
            # Last user message is sent separately
            if i == len(other_messages) - 1 and role == "user":
                last_message = content
            else:
                history.append({
                    "role": role,
                    "parts": [{"text": content}]
                })

        # If we have extra system context, prepend it to the last message
        if decomposed["extra_system"] and last_message:
            context_block = "\n\n".join(decomposed["extra_system"])
            last_message = f"{context_block}\n\nUser query: {last_message}"
        
        return {
            "history": history,
            "last_message": last_message
        }

    def _prepare_messages_decomposed(
        self, 
        messages: List[Dict[str, str]], 
        include_system: bool = True
    ) -> List[Dict[str, str]]:
        """
        Prepare messages by keeping primary system prompt in the system role
        and prepending extra context to the last user message.
        
        This is useful for local models that don't follow complex system instructions.
        """
        decomposed = self._decompose_messages(messages, include_system)
        
        other_messages = decomposed["other_messages"].copy()
        
        # If we have extra system context, prepend it to the last user message
        if decomposed["extra_system"]:
            context_block = "\n\n".join(decomposed["extra_system"])
            
            # Find the last user message
            last_user_idx = -1
            for i in range(len(other_messages) - 1, -1, -1):
                if other_messages[i]["role"] == "user":
                    last_user_idx = i
                    break
            
            if last_user_idx != -1:
                original_content = other_messages[last_user_idx]["content"]
                other_messages[last_user_idx]["content"] = f"{context_block}\n\n{original_content}"
            else:
                # If no user message found (unlikely), add context as a user message
                other_messages.append({"role": "user", "content": context_block})
        
        # Result starts with the primary system prompt
        result = []
        if decomposed["primary_system"]:
            result.append({"role": "system", "content": decomposed["primary_system"]})
            
        result.extend(other_messages)
        return result
    
    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        on_token: Callable[[str], None],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        include_system: bool = True
    ) -> str:
        """
        Stream chat completion and call on_token for each token.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            on_token: Callback function called with each token
            max_tokens: Maximum tokens to generate (optional)
            temperature: Sampling temperature (None to use instance default)
            top_p: Top-p sampling parameter (None to use instance default)
            include_system: Whether to include system prompt (default: True)
            
        Returns:
            Complete response text
        """
        if self.provider == "google":
            return await self._stream_chat_google(messages, on_token, max_tokens, temperature, top_p, include_system)
        elif self.provider == "anthropic":
            return await self._stream_chat_anthropic(messages, on_token, max_tokens, temperature, top_p, include_system)
        elif self.provider == "openai":
            return await self._stream_chat_openai(messages, on_token, max_tokens, temperature, top_p, include_system)
        else:
            return await self._stream_chat_ollama(messages, on_token, max_tokens, temperature, top_p, include_system)



class LLMConfig:
    """Configuration for LLM client."""
    
    DEFAULT_MODELS = {
        "LOCAL": "Gemma3:4b",
        "FLASH": "Gemini-2.5-Flash",
        "DEEPSEEK": "Deepseek V3.2",
        "CLOUD": "Kimi K2:1T",
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
        self._model_key = model_key or self.DEFAULT_MODELS["LOCAL"]
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
        mapping = get_model_mapping()
        model_config = mapping.get(self._model_key, {})
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
    
    def apply_to_client(self, client: LLMClient):
        """Update an existing client with current configuration."""
        client.temperature = self.temperature
        client.top_p = self.top_p
        client.system_prompt = self.system_prompt
        # Note: model_key and api_key would require re-initialization of the provider client
        # which is handled by creating a new client if needed.