"""
LLM Setup Dialog for SammyAI.
Handles configuration of local and cloud LLM providers and models.
"""

import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QComboBox, QScrollArea, 
    QWidget, QFrame, QMessageBox
)
from PySide6.QtCore import Qt, Signal, Slot
from api_key_manager import APIKeyManager
import ollama


class ModelRow(QWidget):
    """A row containing a model input field and a remove button."""
    removed = Signal()
    textChanged = Signal(str)

    def __init__(self, model_name="", is_local=False, parent=None):
        super().__init__(parent)
        self.is_local = is_local
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.input = QLineEdit(model_name)
        self.input.setProperty("class", "modelInput")
        self.input.setPlaceholderText("Enter model name...")
        self.input.textChanged.connect(self.textChanged.emit)
        
        self.remove_btn = QPushButton("✕")
        self.remove_btn.setProperty("class", "removeBtn")
        self.remove_btn.setFixedSize(30, 30)
        self.remove_btn.setCursor(Qt.PointingHandCursor)
        self.remove_btn.clicked.connect(self.removed.emit)

        layout.addWidget(self.input)
        layout.addWidget(self.remove_btn)

    def get_model_name(self):
        return self.input.text().strip()

    def set_validation_state(self, state: str):
        """state can be 'valid', 'invalid', or None"""
        if state == "valid":
            self.input.setProperty("class", "modelInput modelInputValid")
        elif state == "invalid":
            self.input.setProperty("class", "modelInput modelInputInvalid")
        else:
            self.input.setProperty("class", "modelInput")
        self.input.style().unpolish(self.input)
        self.input.style().polish(self.input)


class ProviderSection(QWidget):
    """A section for a specific LLM provider."""
    
    def __init__(self, provider_id, label, badge_text, is_cloud=True, parent=None):
        super().__init__(parent)
        self.provider_id = provider_id
        self.is_cloud = is_cloud
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(10)
        self.setProperty("class", "providerSection")

        # Header
        header_layout = QHBoxLayout()
        label_widget = QLabel(label)
        label_widget.setProperty("class", "providerLabel")
        
        badge = QLabel(badge_text)
        badge.setProperty("class", f"providerBadge {'badgeCloud' if is_cloud else 'badgeLocal'}")
        
        header_layout.addWidget(label_widget)
        header_layout.addWidget(badge)
        header_layout.addStretch()
        self.layout.addLayout(header_layout)

        # API Key (if cloud)
        if is_cloud:
            key_row = QHBoxLayout()
            key_row.setProperty("class", "apiKeyRow")
            
            key_label = QLabel("API key")
            key_label.setProperty("class", "apiKeyLabel")
            key_label.setFixedWidth(60)
            
            self.key_input = QLineEdit()
            self.key_input.setPlaceholderText("Enter API key...")
            self.key_input.setEchoMode(QLineEdit.Password)
            self.key_input.setProperty("class", "apiKeyInput")
            
            self.toggle_btn = QPushButton("👁")
            self.toggle_btn.setFixedSize(30, 30)
            self.toggle_btn.setCursor(Qt.PointingHandCursor)
            self.toggle_btn.clicked.connect(self._toggle_key_visibility)
            
            self.api_status = QLabel("")
            self.api_status.setProperty("class", "apiStatus")
            
            key_row.addWidget(key_label)
            key_row.addWidget(self.key_input)
            key_row.addWidget(self.toggle_btn)
            key_row.addWidget(self.api_status)
            self.layout.addLayout(key_row)
            
            self.key_input.textChanged.connect(self._update_api_status)

        # Models
        self.models_container = QVBoxLayout()
        self.models_container.setSpacing(5)
        self.layout.addLayout(self.models_container)
        
        self.add_btn = QPushButton(f"+ Add {'local ' if not is_cloud else ''}model")
        self.add_btn.setProperty("class", "addBtn")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.clicked.connect(lambda: self.add_model_row())
        self.layout.addWidget(self.add_btn)

        # Validation message (for local)
        if not is_cloud:
            self.validation_msg = QLabel("")
            self.validation_msg.setProperty("class", "validationMsg")
            self.validation_msg.setWordWrap(True)
            self.validation_msg.hide()
            self.layout.addWidget(self.validation_msg)
        else:
            self.note = QLabel("Cloud model names are not verified — double-check against documentation.")
            self.note.setProperty("class", "cloudNote")
            self.layout.addWidget(self.note)

        self.model_rows = []
        self._update_add_btn_state()


    def _toggle_key_visibility(self):
        if self.key_input.echoMode() == QLineEdit.Password:
            self.key_input.setEchoMode(QLineEdit.Normal)
            self.toggle_btn.setText("🔒")
        else:
            self.key_input.setEchoMode(QLineEdit.Password)
            self.toggle_btn.setText("👁")

    def _update_api_status(self):
        if not self.is_cloud: return
        if self.key_input.text().strip():
            self.api_status.setText("✓")
            self.api_status.setProperty("class", "apiStatus apiOk")
        else:
            self.api_status.setText("⚠ Not set")
            self.api_status.setProperty("class", "apiStatus apiMissing")
        self.api_status.style().unpolish(self.api_status)
        self.api_status.style().polish(self.api_status)
        self._update_add_btn_state()


    def add_model_row(self, name=""):
        if len(self.model_rows) >= 3:
            return
        
        row = ModelRow(name, is_local=not self.is_cloud)
        row.removed.connect(lambda: self.remove_model_row(row))
        row.textChanged.connect(self._on_models_changed)
        self.models_container.addWidget(row)
        self.model_rows.append(row)
        
        self._update_add_btn_state()
        self._on_models_changed()

    def remove_model_row(self, row):
        self.models_container.removeWidget(row)
        self.model_rows.remove(row)
        row.deleteLater()
        self._update_add_btn_state()
        self._on_models_changed()

    def _update_add_btn_state(self):
        can_add = len(self.model_rows) < 3
        
        # For cloud providers, also require an API key
        if self.is_cloud and not self.key_input.text().strip():
            can_add = False
            self.add_btn.setToolTip("Please enter an API key first")
        elif len(self.model_rows) >= 3:
            self.add_btn.setToolTip("Max 3 models reached")
        else:
            self.add_btn.setToolTip("")
            
        self.add_btn.setEnabled(can_add)


    def _on_models_changed(self):
        # Trigger parent update for default model list
        if hasattr(self.window(), "update_default_model_list"):
            self.window().update_default_model_list()
        
        # Local validation
        if not self.is_cloud:
            self._validate_local_models()

    def _validate_local_models(self):
        if self.is_cloud: return
        
        try:
            # Get list of installed models
            resp = ollama.list()
            # Handle both object-based (new) and dict-based (old) SDK responses
            models_raw = resp.models if hasattr(resp, 'models') else resp.get('models', [])
            
            available_models = []
            for m in models_raw:
                if hasattr(m, 'model'):
                    name = m.model
                elif isinstance(m, dict):
                    name = m.get('model', m.get('name', ''))
                else:
                    name = str(m)
                if name:
                    available_models.append(name)
            
            all_valid = True
            for row in self.model_rows:
                name = row.get_model_name()
                if not name: 
                    row.set_validation_state(None)
                    continue
                    
                # Exact match or match with :latest tag
                is_match = (name in available_models) or (f"{name}:latest" in available_models)
                
                if is_match:
                    row.set_validation_state("valid")
                else:
                    row.set_validation_state("invalid")
                    all_valid = False

            
            if not self.model_rows:
                self.validation_msg.hide()
            elif all_valid:
                self.validation_msg.setText("✓ Found in your local Ollama installation")
                self.validation_msg.setProperty("class", "validationMsg validationOk")
                self.validation_msg.show()
            else:
                self.validation_msg.setText("⚠ Not found in Ollama. Check spelling or run 'ollama pull' first.")
                self.validation_msg.setProperty("class", "validationMsg validationWarn")
                self.validation_msg.show()

        except Exception:
            for row in self.model_rows:
                row.set_validation_state("invalid")
            self.validation_msg.setText("Ollama server not found. Is it running?")
            self.validation_msg.setProperty("class", "validationMsg validationWarn")
            self.validation_msg.show()
            
        self.validation_msg.style().unpolish(self.validation_msg)
        self.validation_msg.style().polish(self.validation_msg)

    def get_models(self):
        return [row.get_model_name() for row in self.model_rows if row.get_model_name()]

    def get_api_key(self):
        return self.key_input.text().strip() if self.is_cloud else ""

    def is_valid(self):
        """Check if all models in this section are valid (for local only)."""
        if self.is_cloud: return True
        
        try:
            resp = ollama.list()
            models_raw = resp.models if hasattr(resp, 'models') else resp.get('models', [])
            available_models = []
            for m in models_raw:
                if hasattr(m, 'model'):
                    name = m.model
                elif isinstance(m, dict):
                    name = m.get('model', m.get('name', ''))
                else:
                    name = str(m)
                if name:
                    available_models.append(name)
            
            for row in self.model_rows:
                name = row.get_model_name()
                if not name: return False
                is_match = (name in available_models) or (f"{name}:latest" in available_models)
                if not is_match:
                    return False
            return True
        except Exception:
            return False



class LLMSetupDialog(QDialog):
    """The main LLM Setup Dialog."""
    settingsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LLM Setup")
        self.setMinimumWidth(540)
        self.setObjectName("llmSetupDialog")
        
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("llmSetupHeader")
        header_layout = QVBoxLayout(header)
        title = QLabel("LLM setup")
        title.setObjectName("llmSetupTitle")
        subtitle = QLabel("Configure your models")
        subtitle.setObjectName("llmSetupSubtitle")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        main_layout.addWidget(header)

        # Body (Scroll Area)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        body_widget = QWidget()
        body_widget.setObjectName("llmSetupBody")
        self.body_layout = QVBoxLayout(body_widget)
        self.body_layout.setContentsMargins(20, 0, 20, 10)
        
        self.sections = {}
        self.sections["local"] = ProviderSection("local", "Local", "Ollama", is_cloud=False)
        self.sections["anthropic"] = ProviderSection("anthropic", "Anthropic", "Cloud")
        self.sections["google"] = ProviderSection("google", "Google", "Cloud")
        self.sections["openai"] = ProviderSection("openai", "OpenAI", "Cloud")
        self.sections["ollama_cloud"] = ProviderSection("ollama_cloud", "Ollama cloud", "Cloud")
        
        for section in self.sections.values():
            self.body_layout.addWidget(section)
        
        scroll.setWidget(body_widget)
        main_layout.addWidget(scroll)

        # Footer
        footer = QFrame()
        footer.setObjectName("llmSetupFooter")
        footer_layout = QVBoxLayout(footer)
        
        default_row = QHBoxLayout()
        default_label = QLabel("Default model:")
        default_label.setProperty("class", "defaultLabel")
        self.default_combo = QComboBox()
        self.default_combo.setProperty("class", "defaultSelect")
        default_row.addWidget(default_label)
        default_row.addWidget(self.default_combo)
        footer_layout.addLayout(default_row)
        
        btns_layout = QHBoxLayout()
        btns_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setProperty("class", "footerBtn")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setCursor(Qt.PointingHandCursor)

        save_btn = QPushButton("Save")
        save_btn.setProperty("class", "btnPrimary")
        save_btn.clicked.connect(self.on_save)
        save_btn.setCursor(Qt.PointingHandCursor)
        
        btns_layout.addWidget(cancel_btn)
        btns_layout.addWidget(save_btn)
        footer_layout.addLayout(btns_layout)
        
        main_layout.addWidget(footer)

    def load_settings(self):
        # Load API keys
        for provider_id, section in self.sections.items():
            if section.is_cloud:
                key = APIKeyManager.load_api_key(provider_id)
                section.key_input.setText(key)
            
            models = APIKeyManager.load_models(provider_id)
            for model in models:
                section.add_model_row(model)

        # Load default model
        self.update_default_model_list()
        default_key = APIKeyManager.load_default_model()
        idx = self.default_combo.findText(default_key)
        if idx >= 0:
            self.default_combo.setCurrentIndex(idx)

    def update_default_model_list(self):
        current_text = self.default_combo.currentText()
        self.default_combo.clear()
        
        for provider_id, section in self.sections.items():
            for model_name in section.get_models():
                display_id = "ollama" if provider_id == "ollama_cloud" else provider_id
                self.default_combo.addItem(f"{model_name} ({display_id})")
        
        idx = self.default_combo.findText(current_text)
        if idx >= 0:
            self.default_combo.setCurrentIndex(idx)

    def on_save(self):
        # Validate local models before saving
        local_section = self.sections.get("local")
        if local_section and not local_section.is_valid():
            QMessageBox.warning(
                self, 
                "Invalid Configuration", 
                "One or more local models are not found in Ollama. Please fix or remove them before saving."
            )
            return

        # Save each provider
        for provider_id, section in self.sections.items():

            if section.is_cloud:
                APIKeyManager.save_api_key(section.get_api_key(), provider_id)
            APIKeyManager.save_models(provider_id, section.get_models())
        
        # Save default model
        APIKeyManager.save_default_model(self.default_combo.currentText())
        
        self.settingsChanged.emit()
        self.accept()
