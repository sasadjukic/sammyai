"""Native PySide6 chat panel used by SammyAI's LLM workflows."""

from __future__ import annotations

import math
import os

from PySide6.QtCore import QEvent, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from sammyai_core.resources import asset_path


class AutoGrowingTextEdit(QTextEdit):
    """A text editor that grows with its document up to a practical limit."""

    MINIMUM_HEIGHT = 54
    MAXIMUM_HEIGHT = 180

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(self.MINIMUM_HEIGHT)
        self.setMaximumHeight(self.MAXIMUM_HEIGHT)
        self.document().contentsChanged.connect(self.update_editor_height)
        self.update_editor_height()

    def update_editor_height(self) -> None:
        """Fit the editor to its content while retaining a maximum height."""
        document_height = self.document().documentLayout().documentSize().height()
        frame = self.frameWidth() * 2
        margins = self.contentsMargins()
        chrome = frame + margins.top() + margins.bottom() + 14
        height = max(
            self.MINIMUM_HEIGHT,
            min(self.MAXIMUM_HEIGHT, math.ceil(document_height + chrome)),
        )
        self.setFixedHeight(height)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded
            if height >= self.MAXIMUM_HEIGHT
            else Qt.ScrollBarAlwaysOff
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self.update_editor_height()


def _copy_icon(color: str, size: int = 16) -> QIcon:
    """Draw a small copy icon without introducing another asset dependency."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.4))
    painter.drawRoundedRect(5, 2, 8, 9, 1, 1)
    painter.drawRoundedRect(2, 5, 8, 9, 1, 1)
    painter.end()
    return QIcon(pixmap)


class ChatMessage(QFrame):
    """One independently actionable message in the conversation."""

    copied = Signal(str)

    ROLE_LABELS = {
        "user": "You",
        "assistant": "Sammy",
        "system": "SammyAI",
        "thinking": "SammyAI",
    }

    def __init__(
        self,
        role: str,
        text: str,
        *,
        copyable: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.role = role
        self.message_text = text
        self.setObjectName("chatMessage")
        self.setProperty("role", role)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(7)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)

        self.role_label = QLabel(self.ROLE_LABELS.get(role, role.title()))
        self.role_label.setObjectName("messageRole")
        self.role_label.setProperty("role", role)
        header.addWidget(self.role_label)
        header.addStretch()

        self.copy_button: QPushButton | None = None
        if copyable:
            self.copy_button = QPushButton()
            self.copy_button.setObjectName("messageCopyButton")
            self.copy_button.setIcon(_copy_icon("#b8c1c0"))
            self.copy_button.setIconSize(QSize(16, 16))
            self.copy_button.setFixedSize(28, 26)
            self.copy_button.setCursor(Qt.PointingHandCursor)
            self.copy_button.setToolTip("Copy this message")
            self.copy_button.setAccessibleName("Copy message")
            self.copy_button.clicked.connect(self._copy_message)
            header.addWidget(self.copy_button)

        layout.addLayout(header)

        self.message_label = QLabel(text)
        self.message_label.setObjectName("messageText")
        self.message_label.setTextFormat(Qt.PlainText)
        self.message_label.setWordWrap(True)
        self.message_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse
        )
        self.message_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addWidget(self.message_label)

    def set_message_text(self, text: str) -> None:
        self.message_text = text
        self.message_label.setText(text)

    def _copy_message(self) -> None:
        QApplication.clipboard().setText(self.message_text)
        self.copied.emit(self.message_text)


class ChatTranscript(QScrollArea):
    """Scrollable structured transcript with a QTextEdit-compatible text view."""

    message_copied = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chatDisplay")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.content = QWidget()
        self.content.setObjectName("chatTranscriptContent")
        self.message_layout = QVBoxLayout(self.content)
        self.message_layout.setContentsMargins(2, 4, 6, 4)
        self.message_layout.setSpacing(10)
        self.message_layout.addStretch()
        self.setWidget(self.content)

        self.messages: list[ChatMessage] = []

    def add_message(
        self,
        role: str,
        text: str,
        *,
        copyable: bool = True,
    ) -> ChatMessage:
        message = ChatMessage(role, text, copyable=copyable, parent=self.content)
        message.copied.connect(self.message_copied)
        self.messages.append(message)
        self.message_layout.insertWidget(self.message_layout.count() - 1, message)
        self.scroll_to_bottom()
        return message

    def remove_message(self, message: ChatMessage | None) -> None:
        if message is None or message not in self.messages:
            return
        self.messages.remove(message)
        self.message_layout.removeWidget(message)
        message.setParent(None)
        message.deleteLater()

    def clear(self) -> None:
        for message in list(self.messages):
            self.remove_message(message)

    def toPlainText(self) -> str:  # noqa: N802 - compatibility with QTextEdit
        sections = []
        for message in self.messages:
            if message.role == "thinking":
                continue
            role = ChatMessage.ROLE_LABELS.get(message.role, message.role.title())
            sections.append(f"{role}:\n{message.message_text}")
        return "\n\n".join(sections)

    def append_to_last_message(self, text: str) -> None:
        for message in reversed(self.messages):
            if message.role != "thinking":
                message.set_message_text(message.message_text + text)
                self.scroll_to_bottom()
                return

    def scroll_to_bottom(self) -> None:
        QTimer.singleShot(
            0,
            lambda: self.verticalScrollBar().setValue(
                self.verticalScrollBar().maximum()
            ),
        )


class ChatPanel(QWidget):
    """Responsive chat panel for LLM and agent interaction."""

    message_sent = Signal(str)
    model_selected = Signal(str)
    agent_selected = Signal(str)
    new_chat_requested = Signal()
    # Retained for compatibility with integrations written before the redesign.
    clear_chat_requested = Signal()
    close_requested = Signal()

    COLOR_USER = "#e9a5a5"
    COLOR_ASSISTANT = "#81c1d9"
    COLOR_SYSTEM = "#b8c1c0"
    COLOR_TEXT = "#eeeeee"
    COLOR_ICON = "#81c1d9"

    ICONS_DIR: str | None = None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(500)
        self.setMaximumWidth(1000)
        ChatPanel.ICONS_DIR = str(asset_path("icons"))
        self._thinking_message: ChatMessage | None = None
        self._conversation_started = False
        self.setup_ui()

    def setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.container = QFrame()
        self.container.setObjectName("chatContainer")
        main_layout.addWidget(self.container)

        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(18, 16, 18, 18)
        self.layout.setSpacing(12)

        self._build_header()
        self._build_conversation_area()
        self._build_composer()

        self.setObjectName("chatPanel")
        self._set_conversation_started(False)

    def _build_header(self) -> None:
        self.header = QFrame()
        self.header.setObjectName("chatHeader")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(2, 0, 0, 0)
        header_layout.setSpacing(8)

        self.icon_label = QLabel()
        self.icon_label.setObjectName("chatHeaderIcon")
        self._setup_header_icon()

        self.text_label = QLabel("SammyAI")
        self.text_label.setObjectName("chatHeaderText")

        self.new_chat_button = QPushButton("+  New Chat")
        self.new_chat_button.setObjectName("newChatButton")
        self.new_chat_button.setToolTip("Start a new chat and clear session context")
        self.new_chat_button.setCursor(Qt.PointingHandCursor)
        # Compatibility for integrations that previously referenced clear_button.
        self.clear_button = self.new_chat_button

        self.close_button = QPushButton("×")
        self.close_button.setObjectName("chatCloseButton")
        self.close_button.setFixedSize(30, 30)
        self.close_button.setToolTip("Collapse chat panel")
        self.close_button.setAccessibleName("Collapse chat panel")
        self.close_button.setCursor(Qt.PointingHandCursor)

        header_layout.addWidget(self.icon_label)
        header_layout.addWidget(self.text_label)
        header_layout.addStretch()
        header_layout.addWidget(self.new_chat_button)
        header_layout.addWidget(self.close_button)
        self.layout.addWidget(self.header)

        self.new_chat_button.clicked.connect(self._on_clear_clicked)
        self.close_button.clicked.connect(self._on_close_clicked)

    def _build_conversation_area(self) -> None:
        self.conversation_area = QWidget()
        self.conversation_area.setObjectName("chatConversationArea")
        self.conversation_layout = QVBoxLayout(self.conversation_area)
        self.conversation_layout.setContentsMargins(0, 0, 0, 0)
        self.conversation_layout.setSpacing(10)

        self.empty_state = QWidget()
        self.empty_state.setObjectName("chatEmptyState")
        self.empty_state.setMinimumHeight(78)
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.setSpacing(7)
        empty_layout.setAlignment(Qt.AlignCenter)

        self.empty_title = QLabel("What would you like to work on?")
        self.empty_title.setObjectName("chatEmptyTitle")
        self.empty_title.setAlignment(Qt.AlignCenter)
        self.empty_title.setWordWrap(True)
        self.empty_hint = QLabel(
            "Ask a question, develop an idea, or work with your project files."
        )
        self.empty_hint.setObjectName("chatEmptyHint")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setMinimumSize(420, 36)
        self.empty_hint.setMaximumWidth(560)
        empty_layout.addWidget(self.empty_title)
        empty_layout.addWidget(self.empty_hint)

        self.chat_display = ChatTranscript()
        self.chat_display.message_copied.connect(self._on_message_copied)

        self.status_label = QLabel("")
        self.status_label.setObjectName("chatStatus")
        self.status_label.setWordWrap(True)

        self.layout.addWidget(self.conversation_area, 1)

    def _build_composer(self) -> None:
        self.composer_host = QWidget()
        self.composer_host.setObjectName("chatComposerHost")
        host_layout = QHBoxLayout(self.composer_host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(0)
        host_layout.addStretch(1)

        self.composer = QFrame()
        self.composer.setObjectName("chatComposer")
        self.composer.setMaximumWidth(800)
        self.composer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        composer_layout = QVBoxLayout(self.composer)
        composer_layout.setContentsMargins(12, 10, 10, 9)
        composer_layout.setSpacing(7)

        self.input_field = AutoGrowingTextEdit()
        self.input_field.setObjectName("chatInput")
        self.input_field.setPlaceholderText("Ask SammyAI…")
        self.input_field.installEventFilter(self)
        composer_layout.addWidget(self.input_field)

        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(7)

        self.attach_button = QPushButton("+")
        self.attach_button.setObjectName("attachButton")
        self.attach_button.setFixedSize(32, 30)
        self.attach_button.setCursor(Qt.PointingHandCursor)
        self.attach_button.setToolTip(
            "Attach a temporary external reference to this conversation"
        )
        self.attach_button.setAccessibleName("Attach reference")
        self.cin_button = self.attach_button

        self.agent_combo = QComboBox()
        self.agent_combo.setObjectName("agentSelector")
        self.agent_combo.setToolTip("Choose the workflow for the next message")
        self.agent_combo.setMinimumWidth(115)
        self.agent_combo.setMaximumWidth(155)
        try:
            from sammyai_core.agent_workflows import AgentType

            for agent_type in AgentType:
                self.agent_combo.addItem(agent_type.display_name, agent_type.value)
        except ImportError:
            self.agent_combo.addItem("Assistant", "general")
        self.agent_combo.currentIndexChanged.connect(self._on_agent_changed)

        try:
            from llm.client import get_model_mapping

            model_keys = list(get_model_mapping().keys())
        except (ImportError, AttributeError):
            model_keys = []

        self.model_combo = QComboBox()
        self.model_combo.setObjectName("modelSelector")
        self.model_combo.setToolTip("Select LLM model")
        self.model_combo.addItems(model_keys)
        self.model_combo.setMinimumWidth(125)
        self.model_combo.setMaximumWidth(200)
        if model_keys:
            self.model_combo.setCurrentIndex(0)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)

        self.send_button = QPushButton()
        self.send_button.setObjectName("sendButton")
        self.send_button.setCursor(Qt.PointingHandCursor)
        self.send_button.setToolTip("Send message (Enter)")
        self.send_button.setAccessibleName("Send message")
        self._setup_send_button_ui()
        self.send_button.clicked.connect(self._on_send_clicked)

        controls_layout.addWidget(self.attach_button)
        controls_layout.addWidget(self.agent_combo)
        controls_layout.addStretch()
        controls_layout.addWidget(self.model_combo)
        controls_layout.addWidget(self.send_button)
        composer_layout.addLayout(controls_layout)

        host_layout.addWidget(self.composer, 100)
        host_layout.addStretch(1)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt API
        if obj == self.input_field and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if not (event.modifiers() & Qt.ShiftModifier):
                    self._on_send_clicked()
                    return True
        return super().eventFilter(obj, event)

    def _set_conversation_started(self, started: bool) -> None:
        """Move the single composer between its empty and active positions."""
        self._conversation_started = started
        while self.conversation_layout.count():
            item = self.conversation_layout.takeAt(0)
            if item.widget():
                item.widget().hide()

        if started:
            self.chat_display.show()
            self.status_label.show()
            self.composer_host.show()
            self.conversation_layout.addWidget(self.chat_display, 1)
            self.conversation_layout.addWidget(self.status_label)
            self.conversation_layout.addWidget(self.composer_host)
        else:
            self.empty_state.show()
            self.status_label.show()
            self.composer_host.show()
            self.chat_display.hide()
            self.conversation_layout.addStretch(3)
            self.conversation_layout.addWidget(self.empty_state)
            self.conversation_layout.addSpacing(12)
            self.conversation_layout.addWidget(self.composer_host)
            self.conversation_layout.addWidget(
                self.status_label, 0, Qt.AlignHCenter
            )
            self.conversation_layout.addStretch(4)

    def _ensure_conversation_started(self) -> None:
        if not self._conversation_started:
            self._set_conversation_started(True)

    def _setup_send_button_ui(self) -> None:
        try:
            icon_path = os.path.join(self.ICONS_DIR or "", "send_arrow.svg")
            size = 22
            icon = self._load_and_tint_icon(icon_path, size, self.COLOR_ICON)
            if icon:
                self.send_button.setIcon(icon)
                self.send_button.setIconSize(QSize(size, size))
                self.send_button.setFixedSize(34, 32)
                self.send_button.setText("")
            else:
                self.send_button.setText("Send")
        except FileNotFoundError:
            self.send_button.setText("Send")

    def _load_and_tint_icon(
        self, icon_path: str, size: int, color: str
    ) -> QIcon | None:
        try:
            if not os.path.exists(icon_path):
                return None
            renderer = QSvgRenderer(icon_path)
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter, QRect(0, 0, size, size))
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(pixmap.rect(), QColor(color))
            painter.end()
            return QIcon(pixmap)
        except (FileNotFoundError, OSError):
            return None

    def _setup_header_icon(self) -> None:
        try:
            icon_path = os.path.join(self.ICONS_DIR or "", "dialogue.svg")
            size = 20
            icon = self._load_and_tint_icon(icon_path, size, self.COLOR_ICON)
            if icon:
                self.icon_label.setPixmap(icon.pixmap(QSize(size, size)))
                self.icon_label.setFixedSize(size, size)
        except FileNotFoundError:
            return

    def _on_send_clicked(self) -> None:
        message = self.input_field.toPlainText().strip()
        if not message:
            return
        self.message_sent.emit(message)
        self.input_field.clear()
        self.input_field.update_editor_height()

    def _on_model_changed(self, model_key: str) -> None:
        if not model_key:
            return
        self.model_selected.emit(model_key)

    def _on_agent_changed(self, index: int) -> None:
        agent_type = self.agent_combo.itemData(index)
        if agent_type:
            self.agent_selected.emit(str(agent_type))

    def _on_clear_clicked(self) -> None:
        if self._thinking_message is not None:
            return
        self.chat_display.clear()
        self._thinking_message = None
        self.status_label.setText("New chat ready")
        self._set_conversation_started(False)
        self.input_field.setFocus()
        self.new_chat_requested.emit()
        self.clear_chat_requested.emit()

    def _on_close_clicked(self) -> None:
        self.close_requested.emit()

    def _on_message_copied(self) -> None:
        self.set_status("Message copied to clipboard")

    def add_user_message(self, message: str) -> None:
        self._ensure_conversation_started()
        self.chat_display.add_message("user", message)

    def add_assistant_message(self, message: str) -> None:
        self._ensure_conversation_started()
        self.chat_display.add_message("assistant", message)

    def add_system_message(self, message: str) -> None:
        self._ensure_conversation_started()
        self.chat_display.add_message("system", message, copyable=False)

    def append_to_last_message(self, text: str) -> None:
        self.chat_display.append_to_last_message(text)

    def set_status(self, status: str) -> None:
        self.status_label.setText(status)

    def set_input_enabled(self, enabled: bool) -> None:
        self.input_field.setEnabled(enabled)
        self.send_button.setEnabled(enabled)

    def set_thinking(self, thinking: bool) -> None:
        if thinking and self._thinking_message is None:
            self._ensure_conversation_started()
            self._thinking_message = self.chat_display.add_message(
                "thinking",
                "Sammy is thinking…",
                copyable=False,
            )
            self.new_chat_button.setEnabled(False)
        elif not thinking and self._thinking_message is not None:
            self.chat_display.remove_message(self._thinking_message)
            self._thinking_message = None
            self.new_chat_button.setEnabled(True)

    def _scroll_to_bottom(self) -> None:
        """Compatibility helper for existing integrations."""
        self.chat_display.scroll_to_bottom()

    @staticmethod
    def _escape_html(text: str) -> str:
        """Retained for third-party integrations that used the old helper."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )

    def refresh_model_dropdown(self) -> None:
        try:
            from llm.client import get_model_mapping

            model_keys = list(get_model_mapping().keys())
            self.model_combo.blockSignals(True)
            current_text = self.model_combo.currentText()
            self.model_combo.clear()
            self.model_combo.addItems(model_keys)

            from api_key_manager import APIKeyManager

            default_model = APIKeyManager.load_default_model()
            if current_text in model_keys:
                index = self.model_combo.findText(current_text)
            elif default_model in model_keys:
                index = self.model_combo.findText(default_model)
            else:
                index = 0 if model_keys else -1
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
            self.model_combo.blockSignals(False)
            if self.model_combo.currentText() != current_text:
                self._on_model_changed(self.model_combo.currentText())
        except (ImportError, AttributeError) as error:
            print(f"Failed to refresh model dropdown: {error}")
