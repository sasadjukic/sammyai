"""
Chat Panel Widget for LLM integration in the text editor.
Provides a chat interface similar to VS Code and Antigravity.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
    QLineEdit, QPushButton, QLabel, QScrollArea, QFrame, QComboBox,
    QApplication
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont, QTextCursor
import asyncio
from typing import Optional


class ChatPanel(QWidget):
    """Chat panel widget for LLM interaction."""
    
    # Signal emitted when a message is sent
    message_sent = Signal(str)
    # Signal emitted when user selects a different model
    model_selected = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(300)
        self.setMaximumWidth(1000)
        self.setup_ui()
        self._thinking_cursor = None
    
    def setup_ui(self):
        """Set up the chat panel UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Container frame to allow background styling for the "layout"
        self.container = QFrame()
        self.container.setObjectName("chatContainer")
        
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        main_layout.addWidget(self.container)
        
        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("💬 SammyAI")
        header_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #dddddd;")
        # Model selection combo box
        try:
            # Import here to avoid cyclic imports at module import time
            from llm.client import MODEL_MAPPING
            model_keys = list(MODEL_MAPPING.keys())
        except Exception:
            model_keys = []

        self.model_combo = QComboBox()
        self.model_combo.setToolTip("Select LLM model")
        self.model_combo.addItems(model_keys)
        if model_keys:
            self.model_combo.setCurrentIndex(0)
        self.model_combo.setMaximumWidth(200)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)

        self.close_button = QPushButton("✕")
        self.close_button.setMaximumWidth(30)
        self.close_button.setToolTip("Close chat panel")
        
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        header_layout.addWidget(self.model_combo)
        header_layout.addWidget(self.close_button)
        layout.addLayout(header_layout)
        
        # Chat history display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setPlaceholderText("Chat history will appear here...")
        layout.addWidget(self.chat_display)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888888; font-style: italic; font-size: 11px;")
        layout.addWidget(self.status_label)
        
        # Input area
        input_layout = QVBoxLayout()
        input_layout.setSpacing(5)
        
        self.input_field = QTextEdit()
        self.input_field.setPlaceholderText("Type your message here...")
        self.input_field.setMaximumHeight(100)
        self.input_field.setMinimumHeight(60)
        input_layout.addWidget(self.input_field)
        
        # Button row
        button_layout = QHBoxLayout()
        
        self.clear_button = QPushButton("Clear Chat")
        self.clear_button.setToolTip("Clear chat history")
        
        self.send_button = QPushButton("Send")
        self.send_button.setDefault(True)
        self.send_button.setToolTip("Send message (Ctrl+Enter)")
        
        button_layout.addWidget(self.clear_button)
        
        self.copy_button = QPushButton("Copy Chat")
        self.copy_button.setToolTip("Copy entire chat history to clipboard")
        button_layout.addWidget(self.copy_button)
        
        button_layout.addStretch()
        button_layout.addWidget(self.send_button)
        
        input_layout.addLayout(button_layout)
        layout.addLayout(input_layout)

        self.setObjectName("chatPanel")

        # Apply scoped stylesheet
        self.setStyleSheet(
            """
            #chatContainer { background-color: #2d2d2d; }
            #chatPanel { background-color: transparent; color: #dddddd; }
            #chatContainer QTextEdit { background-color: #2d2d2d; color: #dddddd; border: 1px solid #444444; }
            #chatContainer QPushButton { 
                background-color: transparent; 
                color: #dddddd; 
                border: 1px solid #444444; 
                border-radius: 4px; 
                padding: 6px 12px; 
            }
            #chatContainer QPushButton:hover { 
                background-color: #3a3a3a; 
                border-color: #666666; 
            }
            #chatContainer QComboBox { 
                background-color: #3d3d3d; 
                color: #eeeeee; 
                border: 1px solid #444444; 
                border-radius: 4px;
                padding: 4px; 
            }
            #chatContainer QComboBox:hover { 
                background-color: #444444; 
            }
            #chatContainer QComboBox:on { 
                background-color: #444444; 
            }
            #chatContainer QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                color: #eeeeee;
                selection-background-color: #444444;
                border: 1px solid #444444;
            }
            #chatContainer QLabel { color: #dddddd; }
            #chatContainer QScrollArea { background-color: transparent; }
            """
        )

        # Connect signals
        self.send_button.clicked.connect(self._on_send_clicked)
        self.clear_button.clicked.connect(self._on_clear_clicked)
        self.copy_button.clicked.connect(self._on_copy_clicked)

        # Install event filter for Ctrl+Enter
        self.input_field.installEventFilter(self)
    
    def eventFilter(self, obj, event):
        """Handle keyboard events in the input field."""
        if obj == self.input_field and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                if event.modifiers() & Qt.ControlModifier:
                    self._on_send_clicked()
                    return True
        return super().eventFilter(obj, event)
    
    def _on_send_clicked(self):
        """Handle send button click."""
        message = self.input_field.toPlainText().strip()
        if message:
            self.message_sent.emit(message)
            self.input_field.clear()

    def _on_model_changed(self, model_key: str):
        """Handle model selection changes from the combo box."""
        # Emit signal so the parent can attempt to switch LLMs
        self.model_selected.emit(model_key)
        # Give immediate feedback in the panel
        self.set_status(f"Selected model: {model_key}")
    
    def _on_clear_clicked(self):
        """Handle clear button click."""
        self.chat_display.clear()
        self.status_label.setText("Chat history cleared")
    
    def _on_copy_clicked(self):
        """Handle copy button click."""
        chat_text = self.chat_display.toPlainText()
        if chat_text:
            QApplication.clipboard().setText(chat_text)
            self.status_label.setText("Chat history copied to clipboard")
        else:
            self.status_label.setText("No chat history to copy")
    
    def add_user_message(self, message: str):
        """Add a user message to the chat display."""
        self.chat_display.append(f"<div style='margin-bottom: 10px;'>"
                                 f"<b style='color: #3EE07B;'>You:</b><br>"
                                 f"<span style='color: #dddddd;'>{self._escape_html(message)}</span>"
                                 f"</div>")
        self._scroll_to_bottom()
    
    def add_assistant_message(self, message: str):
        """Add an assistant message to the chat display."""
        self.chat_display.append(f"<div style='margin-bottom: 10px;'>"
                                 f"<b style='color: #4F91F7;'>Sammy:</b><br>"
                                 f"<span style='color: #dddddd;'>{self._escape_html(message)}</span>"
                                 f"</div>")
        self._scroll_to_bottom()
    
    def add_system_message(self, message: str):
        """Add a system message to the chat display."""
        self.chat_display.append(f"<div style='margin-bottom: 10px;'>"
                                 f"<i style='color: #888888;'>{self._escape_html(message)}</i>"
                                 f"</div>")
        self._scroll_to_bottom()
    
    def append_to_last_message(self, text: str):
        """Append text to the last message (for streaming)."""
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.chat_display.setTextCursor(cursor)
        self.chat_display.insertPlainText(text)
        self._scroll_to_bottom()
    
    def set_status(self, status: str):
        """Set the status label text."""
        self.status_label.setText(status)
    
    def set_input_enabled(self, enabled: bool):
        """Enable or disable the input field and send button."""
        self.input_field.setEnabled(enabled)
        self.send_button.setEnabled(enabled)

    def set_thinking(self, thinking: bool):
        """Show or hide the 'Sammy is thinking...' message."""
        if thinking:
            if self._thinking_cursor is None:
                # Add the thinking message
                self.chat_display.append("<div id='thinking_msg' style='margin-bottom: 10px;'>"
                                         "<i style='color: #888888;'>Sammy is thinking...</i>"
                                         "</div>")
                self._scroll_to_bottom()
                
                # Record the position to remove it later
                # We move a cursor to the end and then find the block we just added
                cursor = self.chat_display.textCursor()
                cursor.movePosition(QTextCursor.End)
                
                # We'll use a specific technique to remove the last block
                self._thinking_cursor = cursor
        else:
            if self._thinking_cursor is not None:
                # Remove the last block (the thinking message)
                cursor = self.chat_display.textCursor()
                cursor.movePosition(QTextCursor.End)
                cursor.select(QTextCursor.BlockUnderCursor)
                cursor.removeSelectedText()
                # Also remove the unnecessary empty line append leaves
                cursor.deletePreviousChar()
                self._thinking_cursor = None
                self._scroll_to_bottom()
    
    def _scroll_to_bottom(self):
        """Scroll the chat display to the bottom."""
        scrollbar = self.chat_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        return (text.replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;")
                   .replace("\n", "<br>"))
