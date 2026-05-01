"""
API Key Manager for LLM integration.
Handles secure storage and retrieval of API keys using QSettings.
"""

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QMessageBox
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt


class APIKeyManager:
    """Manages API key storage and retrieval using QSettings."""
    
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



class APIKeyDialog(QDialog):
    """Dialog for entering and managing API keys."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("API Key Configuration")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setup_ui()
        self.load_existing_key()
    
    def setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Title and description
        title_label = QLabel("Cloud Model API Keys")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)
        
        description = QLabel(
            "Configure API keys for cloud-based LLM models. These keys are stored securely on your local machine."
        )
        description.setWordWrap(True)
        description.setStyleSheet("color: #888888; margin-bottom: 10px;")
        layout.addWidget(description)
        
        # Google API Key
        google_group_layout = QVBoxLayout()
        google_label = QLabel("Google API Key (for Gemini models):")
        google_label.setStyleSheet("font-weight: bold;")
        
        google_input_layout = QHBoxLayout()
        self.google_input = QLineEdit()
        self.google_input.setPlaceholderText("Enter your Google API key here...")
        self.google_input.setEchoMode(QLineEdit.Password)
        
        self.toggle_google_btn = QPushButton("👁")
        self.toggle_google_btn.setMaximumWidth(40)
        self.toggle_google_btn.clicked.connect(lambda: self._toggle_visibility(self.google_input, self.toggle_google_btn))
        
        google_input_layout.addWidget(self.google_input)
        google_input_layout.addWidget(self.toggle_google_btn)
        
        google_group_layout.addWidget(google_label)
        google_group_layout.addLayout(google_input_layout)
        layout.addLayout(google_group_layout)

        # Ollama/Cloud API Key
        ollama_group_layout = QVBoxLayout()
        ollama_label = QLabel("Ollama Cloud API Key (for Kimi and others):")
        ollama_label.setStyleSheet("font-weight: bold;")
        
        ollama_input_layout = QHBoxLayout()
        self.ollama_input = QLineEdit()
        self.ollama_input.setPlaceholderText("Enter your Ollama cloud API key here...")
        self.ollama_input.setEchoMode(QLineEdit.Password)
        
        self.toggle_ollama_btn = QPushButton("👁")
        self.toggle_ollama_btn.setMaximumWidth(40)
        self.toggle_ollama_btn.clicked.connect(lambda: self._toggle_visibility(self.ollama_input, self.toggle_ollama_btn))
        
        ollama_input_layout.addWidget(self.ollama_input)
        ollama_input_layout.addWidget(self.toggle_ollama_btn)
        
        ollama_group_layout.addWidget(ollama_label)
        ollama_group_layout.addLayout(ollama_input_layout)
        layout.addLayout(ollama_group_layout)
        
        # Status labels
        self.google_status = QLabel("")
        self.ollama_status = QLabel("")
        layout.addWidget(self.google_status)
        layout.addWidget(self.ollama_status)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setToolTip("Remove stored API key")
        self.clear_btn.clicked.connect(self._clear_key)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        
        self.save_btn = QPushButton("Save")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._save_key)
        
        button_layout.addWidget(self.clear_btn)
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.save_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def load_existing_key(self):
        """Load and display existing API keys if available."""
        google_key = APIKeyManager.load_api_key("google")
        if google_key:
            self.google_input.setText(google_key)
            self.google_status.setText("✓ Google API key is configured")
            self.google_status.setStyleSheet("color: #4CAF50; font-style: italic;")
        else:
            self.google_status.setText("⚠ No Google API key configured")
            self.google_status.setStyleSheet("color: #FFA500; font-style: italic;")

        ollama_key = APIKeyManager.load_api_key("ollama")
        if ollama_key:
            self.ollama_input.setText(ollama_key)
            self.ollama_status.setText("✓ Ollama cloud API key is configured")
            self.ollama_status.setStyleSheet("color: #4CAF50; font-style: italic;")
        else:
            self.ollama_status.setText("⚠ No Ollama cloud API key configured")
            self.ollama_status.setStyleSheet("color: #FFA500; font-style: italic;")
    
    def _toggle_visibility(self, line_edit, button):
        """Toggle between showing and hiding the API key."""
        if line_edit.echoMode() == QLineEdit.Password:
            line_edit.setEchoMode(QLineEdit.Normal)
            button.setText("🔒")
        else:
            line_edit.setEchoMode(QLineEdit.Password)
            button.setText("👁")
    
    def _save_key(self):
        """Save the API keys and close the dialog."""
        google_key = self.google_input.text().strip()
        ollama_key = self.ollama_input.text().strip()
        
        if google_key:
            APIKeyManager.save_api_key(google_key, "google")
        else:
            APIKeyManager.clear_api_key("google")

        if ollama_key:
            APIKeyManager.save_api_key(ollama_key, "ollama")
        else:
            APIKeyManager.clear_api_key("ollama")

        QMessageBox.information(
            self,
            "Settings Saved",
            "API keys have been updated successfully!"
        )
        self.accept()
    
    def _clear_key(self):
        """Clear all API keys after confirmation."""
        reply = QMessageBox.question(
            self,
            "Confirm Clear",
            "Are you sure you want to clear all stored API keys?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            APIKeyManager.clear_api_key("google")
            APIKeyManager.clear_api_key("ollama")
            self.google_input.clear()
            self.ollama_input.clear()
            self.load_existing_key()
            QMessageBox.information(
                self,
                "Cleared",
                "All API keys have been cleared successfully."
            )
