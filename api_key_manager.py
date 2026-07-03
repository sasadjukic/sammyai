"""
API Key Manager for LLM integration.
Handles persistent storage and retrieval of API keys using QSettings.

QSettings is configuration storage, not an encrypted credential vault.
"""

from PySide6.QtCore import QSettings


class APIKeyManager:
    """Manages persistent API key configuration using QSettings."""
    
    ORGANIZATION = "SammyAI"
    APPLICATION = "TextEditor"
    
    @staticmethod
    def save_api_key(api_key: str, provider: str = "ollama") -> None:
        """
        Save the API key for a specific provider to persistent storage.
        
        Args:
            api_key: The API key to save
            provider: The key provider ("google" or "ollama")
        """
        settings = QSettings(APIKeyManager.ORGANIZATION, APIKeyManager.APPLICATION)
        settings.setValue(f"llm/api_key_{provider}", api_key)
    
    @staticmethod
    def load_api_key(provider: str = "ollama") -> str:
        """
        Load the API key for a specific provider from persistent storage.
        
        Args:
            provider: The key provider ("google", "ollama", "anthropic", "openai", or "ollama_cloud")
            
        Returns:
            The stored API key, or an empty string if not found
        """
        settings = QSettings(APIKeyManager.ORGANIZATION, APIKeyManager.APPLICATION)
        val = settings.value(f"llm/api_key_{provider}", "")
        return val if isinstance(val, str) else ""
    
    @staticmethod
    def clear_api_key(provider: str = "ollama") -> None:
        """Clear the stored API key for a specific provider."""
        settings = QSettings(APIKeyManager.ORGANIZATION, APIKeyManager.APPLICATION)
        settings.remove(f"llm/api_key_{provider}")
    
    @staticmethod
    def has_api_key(provider: str = "ollama") -> bool:
        """
        Check if an API key is currently stored for a specific provider.
        
        Args:
            provider: The key provider ("google" or "ollama")
            
        Returns:
            True if an API key exists, False otherwise
        """
        return bool(APIKeyManager.load_api_key(provider))

    @staticmethod
    def save_models(provider: str, models: list[str]) -> None:
        """Save a list of model names for a specific provider."""
        settings = QSettings(APIKeyManager.ORGANIZATION, APIKeyManager.APPLICATION)
        settings.setValue(f"llm/models_{provider}", models)

    @staticmethod
    def load_models(provider: str) -> list[str]:
        """Load a list of model names for a specific provider."""
        settings = QSettings(APIKeyManager.ORGANIZATION, APIKeyManager.APPLICATION)
        val = settings.value(f"llm/models_{provider}", [])
        if isinstance(val, list):
            return val
        elif isinstance(val, str) and val:
            return [val]
        return []

    @staticmethod
    def save_default_model(model_key: str) -> None:
        """Save the default model display key."""
        settings = QSettings(APIKeyManager.ORGANIZATION, APIKeyManager.APPLICATION)
        settings.setValue("llm/default_model", model_key)

    @staticmethod
    def load_default_model() -> str:
        """Load the default model display key."""
        settings = QSettings(APIKeyManager.ORGANIZATION, APIKeyManager.APPLICATION)
        val = settings.value("llm/default_model", "")
        return val if isinstance(val, str) else ""
