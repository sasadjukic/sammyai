"""
Chat Panel Widget for LLM integration in the text editor.
Provides a chat interface similar to VS Code and Antigravity.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
    QLineEdit, QPushButton, QLabel, QScrollArea, QFrame
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont, QTextCursor
import asyncio
from typing import Optional


class ChatPanel(QWidget):
    """Chat panel widget for LLM interaction."""
    
    # Signal emitted when a message is sent
    message_sent = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(300)
        self.setMaximumWidth(500)
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the chat panel UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("💬 Sammy AI Assistant")
        header_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        
        self.close_button = QPushButton("✕")
        self.close_button.setMaximumWidth(30)
        self.close_button.setToolTip("Close chat panel")
        
        header_layout.addWidget(header_label)
        header_layout.addStretch()
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
        button_layout.addStretch()
        button_layout.addWidget(self.send_button)
        
        input_layout.addLayout(button_layout)
        layout.addLayout(input_layout)
        
        self.setLayout(layout)
        
        # Connect signals
        self.send_button.clicked.connect(self._on_send_clicked)
        self.clear_button.clicked.connect(self._on_clear_clicked)
        
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
    
    def _on_clear_clicked(self):
        """Handle clear button click."""
        self.chat_display.clear()
        self.status_label.setText("Chat history cleared")
    
    def add_user_message(self, message: str):
        """Add a user message to the chat display."""
        self.chat_display.append(f"<div style='margin-bottom: 10px;'>"
                                 f"<b style='color: #4A90E2;'>You:</b><br>"
                                 f"<span style='color: #CCCCCC;'>{self._escape_html(message)}</span>"
                                 f"</div>")
        self._scroll_to_bottom()
    
    def add_assistant_message(self, message: str):
        """Add an assistant message to the chat display."""
        self.chat_display.append(f"<div style='margin-bottom: 10px;'>"
                                 f"<b style='color: #50C878;'>Sammy:</b><br>"
                                 f"<span style='color: #CCCCCC;'>{self._escape_html(message)}</span>"
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
