"""
Chat Panel Widget for LLM integration in the text editor.
Provides a chat interface similar to VS Code and Antigravity.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
    QLineEdit, QPushButton, QLabel, QScrollArea, QFrame, QComboBox,
    QApplication, QMenu
)
from PySide6.QtCore import Qt, Signal, QThread, QRect, QSize
from PySide6.QtGui import QFont, QTextCursor, QPixmap, QPainter, QColor, QIcon
from PySide6.QtSvg import QSvgRenderer
import asyncio
import os
from typing import Optional


class ChatPanel(QWidget):
    """Chat panel widget for LLM interaction."""
    
    # Signal emitted when a message is sent
    message_sent = Signal(str)
    # Signal emitted when user selects a different model
    model_selected = Signal(str)
    
    # Signal emitted when "Clear Chat" is requested
    clear_chat_requested = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(500)
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
        header_layout.setSpacing(8)

        # Icon
        self.icon_label = QLabel()
        self.icon_label.setObjectName("chatHeaderIcon")
        self._setup_header_icon()
        
        # Text
        self.text_label = QLabel("SammyAI")
        self.text_label.setObjectName("chatHeaderText")
        
        header_layout.addWidget(self.icon_label)
        header_layout.addWidget(self.text_label)
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
        
        header_layout.addStretch()
        header_layout.addWidget(self.model_combo)
        header_layout.addWidget(self.close_button)
        layout.addLayout(header_layout)
        
        # Chat history display
        self.chat_display = QTextEdit()
        self.chat_display.setObjectName("chatDisplay")
        self.chat_display.setReadOnly(True)
        self.chat_display.setPlaceholderText("Chat history will appear here...")
        layout.addWidget(self.chat_display)
        
        # History controls row
        history_controls_layout = QHBoxLayout()
        history_controls_layout.setSpacing(10)
        
        self.clear_button = QPushButton("Clear Chat")
        self.clear_button.setToolTip("Clear chat history")
        
        self.copy_button = QPushButton("Copy Chat")
        self.copy_button.setToolTip("Copy entire chat history to clipboard")
        
        self.rag_button = QPushButton("RAG")
        self.rag_button.setToolTip("RAG Context Management")
        
        self.cin_button = QPushButton("CIN")
        self.cin_button.setToolTip("Context Injection Management")
        
        self.dbe_button = QPushButton("DBE")
        self.dbe_button.setToolTip("Diff-Based Editing Controls")
        
        history_controls_layout.addWidget(self.clear_button)
        history_controls_layout.addWidget(self.copy_button)
        history_controls_layout.addWidget(self.rag_button)
        history_controls_layout.addWidget(self.cin_button)
        history_controls_layout.addWidget(self.dbe_button)
        history_controls_layout.addStretch()
        layout.addLayout(history_controls_layout)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setObjectName("chatStatus")
        layout.addWidget(self.status_label)
        
        # Input area
        input_layout = QVBoxLayout()
        input_layout.setSpacing(5)
        
        self.input_field = QTextEdit()
        self.input_field.setObjectName("chatInput")
        self.input_field.setPlaceholderText("Type your message here...")
        self.input_field.setMaximumHeight(100)
        self.input_field.setMinimumHeight(60)
        input_layout.addWidget(self.input_field)
        
        # Send button (parented to input_field to appear inside)
        self.send_button = QPushButton(self.input_field)
        self.send_button.setObjectName("sendButton")
        self.send_button.setCursor(Qt.PointingHandCursor)
        self.send_button.setToolTip("Send message (Ctrl+Enter)")
        self._setup_send_button_ui()
        
        layout.addLayout(input_layout)

        self.setObjectName("chatPanel")

        # Styles moved to ui/styles/dark_theme.qss

        # Connect signals
        self.send_button.clicked.connect(self._on_send_clicked)
        self.clear_button.clicked.connect(self._on_clear_clicked)
        self.copy_button.clicked.connect(self._on_copy_clicked)

        # Install event filter for Ctrl+Enter
        self.input_field.installEventFilter(self)
    
    def eventFilter(self, obj, event):
        """Handle keyboard events and resizing in the input field."""
        if obj == self.input_field:
            if event.type() == event.Type.KeyPress:
                if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                    if event.modifiers() & Qt.ControlModifier:
                        self._on_send_clicked()
                        return True
            elif event.type() == event.Type.Resize:
                self._update_send_button_position()
        return super().eventFilter(obj, event)
    
    def _update_send_button_position(self):
        """Position the send button in the bottom right of the input field."""
        if not self.send_button:
            return
            
        margin = 8
        button_size = self.send_button.size()
        rect = self.input_field.rect()
        
        # Position at bottom right, accounting for scrollbar if visible
        x = rect.width() - button_size.width() - margin
        # If scrollbar is visible, shift button to the left
        if self.input_field.verticalScrollBar().isVisible():
            x -= self.input_field.verticalScrollBar().width()
            
        y = rect.height() - button_size.height() - margin
        self.send_button.move(x, y)

    def _setup_send_button_ui(self):
        """Load, tint and set the send arrow icon."""
        try:
            icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons", "send_arrow.svg")
            if not os.path.exists(icon_path):
                # Fallback text if icon missing
                self.send_button.setText("➤")
                return

            size = 24
            color = "#81c1d9"

            renderer = QSvgRenderer(icon_path)
            pix = QPixmap(size, size)
            pix.fill(Qt.transparent)

            painter = QPainter(pix)
            renderer.render(painter, QRect(0, 0, size, size))
            
            # Tint the icon
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(pix.rect(), QColor(color))
            painter.end()

            self.send_button.setIcon(QIcon(pix))
            self.send_button.setIconSize(QSize(size, size))
            self.send_button.setFixedSize(size + 8, size + 8)
            self.send_button.setText("") 
        except Exception as e:
            print(f"Failed to load send icon: {e}")
            self.send_button.setText("Send")
    
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
        self.clear_chat_requested.emit()
    
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
                                 f"<b style='color: #e9a5a5;'>You:</b><br>"
                                 f"<span style='color: #dddddd;'>{self._escape_html(message)}</span>"
                                 f"</div>")
        self._scroll_to_bottom()
    
    def add_assistant_message(self, message: str):
        """Add an assistant message to the chat display."""
        self.chat_display.append(f"<div style='margin-bottom: 10px;'>"
                                 f"<b style='color: #81c1d9;'>Sammy:</b><br>"
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

    def _setup_header_icon(self):
        """Load, tint and set the dialogue icon."""
        try:
            # Path to the icon
            icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons", "dialogue.svg")
            
            if not os.path.exists(icon_path):
                return

            # Target size (matching font-size 18px)
            size = 20
            color = "#81c1d9"

            renderer = QSvgRenderer(icon_path)
            pix = QPixmap(size, size)
            pix.fill(Qt.transparent)

            painter = QPainter(pix)
            renderer.render(painter, QRect(0, 0, size, size))
            
            # Tint the icon
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(pix.rect(), QColor(color))
            painter.end()

            self.icon_label.setPixmap(pix)
            self.icon_label.setFixedSize(size, size)
        except Exception as e:
            print(f"Failed to load header icon: {e}")
