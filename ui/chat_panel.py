"""Native PySide6 chat panel used by SammyAI's LLM workflows."""

from __future__ import annotations

from collections.abc import Callable, Iterable
import math
import os
import random
import re

from PySide6.QtCore import (
    QEvent,
    QRect,
    QRectF,
    QSize,
    QStringListModel,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QTextCursor
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QCompleter,
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


FILE_MENTION_PATTERN = re.compile(r"(?<![\w@])@([^\s,;]*)$")
FILE_REFERENCE_EXTENSIONS = frozenset({".md", ".txt"})
GENERIC_WELCOME_MESSAGES = (
    "What would you like to work on?",
    "What shall we create today?",
    "Where would you like to begin?",
    "What story are we shaping today?",
)


class ElidedLabel(QLabel):
    """A single-line label that preserves its full text for accessibility."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_text = text
        self.setTextFormat(Qt.PlainText)
        self._update_display_text()

    @property
    def full_text(self) -> str:
        return self._full_text

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API
        self._full_text = text
        self.setAccessibleName(text)
        self._update_display_text()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._update_display_text()

    def _update_display_text(self) -> None:
        available_width = max(0, self.contentsRect().width())
        display_text = self.fontMetrics().elidedText(
            self._full_text,
            Qt.ElideRight,
            available_width,
        )
        QLabel.setText(self, display_text)
        self.setToolTip(self._full_text if display_text != self._full_text else "")


class AutoGrowingTextEdit(QTextEdit):
    """A text editor that grows with its document up to a practical limit."""

    MINIMUM_HEIGHT = 54
    MAXIMUM_HEIGHT = 180

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_file_provider: Callable[[], Iterable[str]] | None = None
        self._project_files: tuple[str, ...] = ()
        self._active_mention_start: int | None = None
        self._suppress_file_completion = False

        self._file_completion_model = QStringListModel(self)
        self.file_completer = QCompleter(self._file_completion_model, self)
        self.file_completer.setWidget(self)
        self.file_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.file_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.file_completer.setMaxVisibleItems(10)
        self.file_completer.popup().setObjectName("fileReferencePopup")
        self.file_completer.activated[str].connect(self._insert_file_reference)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(self.MINIMUM_HEIGHT)
        self.setMaximumHeight(self.MAXIMUM_HEIGHT)
        self.document().contentsChanged.connect(self.update_editor_height)
        self.textChanged.connect(self._update_file_completions)
        self.update_editor_height()

    def set_project_file_provider(
        self,
        provider: Callable[[], Iterable[str]] | None,
    ) -> None:
        """Set the active-project file source used when a new @mention begins."""
        self._project_file_provider = provider
        self._project_files = ()
        self._active_mention_start = None
        self.file_completer.popup().hide()

    def set_project_files(self, paths: Iterable[str]) -> None:
        """Set a static project file list, primarily for embedded integrations."""
        normalized = {
            str(path).replace("\\", "/").strip("/")
            for path in paths
            if str(path).replace("\\", "/").lower().endswith(
                tuple(FILE_REFERENCE_EXTENSIONS)
            )
        }
        self._project_files = tuple(sorted(normalized, key=str.casefold))

    def _refresh_project_files(self) -> None:
        if self._project_file_provider is None:
            return
        try:
            self.set_project_files(self._project_file_provider())
        except (OSError, RuntimeError):
            self._project_files = ()

    def _mention_at_cursor(self) -> tuple[int, str] | None:
        cursor_position = self.textCursor().position()
        match = FILE_MENTION_PATTERN.search(
            self.toPlainText()[:cursor_position]
        )
        if match is None:
            return None
        return match.start(), match.group(1).replace("\\", "/")

    @staticmethod
    def _completion_score(path: str, query: str) -> int | None:
        if not query:
            return 0
        folded_query = query.casefold()
        folded_path = path.casefold()
        filename = folded_path.rsplit("/", 1)[-1]
        if filename.startswith(folded_query):
            return 0
        if folded_path.startswith(folded_query):
            return 1
        if any(part.startswith(folded_query) for part in folded_path.split("/")):
            return 2
        return None

    def _update_file_completions(self) -> None:
        if self._suppress_file_completion:
            return
        mention = self._mention_at_cursor()
        if mention is None:
            self._active_mention_start = None
            self.file_completer.popup().hide()
            return

        mention_start, query = mention
        if mention_start != self._active_mention_start:
            self._active_mention_start = mention_start
            self._refresh_project_files()

        ranked = []
        for path in self._project_files:
            score = self._completion_score(path, query)
            if score is not None:
                ranked.append((score, path.rsplit("/", 1)[-1].casefold(), path))
        candidates = [path for _score, _name, path in sorted(ranked)]
        self._file_completion_model.setStringList(candidates)
        if not candidates:
            self.file_completer.popup().hide()
            return

        self.file_completer.setCompletionPrefix("")
        popup = self.file_completer.popup()
        popup.setCurrentIndex(self._file_completion_model.index(0, 0))
        completion_rect = self.cursorRect()
        popup_width = (
            popup.sizeHintForColumn(0)
            + popup.verticalScrollBar().sizeHint().width()
            + 16
        )
        completion_rect.setWidth(min(max(220, popup_width), self.width()))
        self.file_completer.complete(completion_rect)

    def has_visible_file_completions(self) -> bool:
        return self.file_completer.popup().isVisible()

    def hide_file_completions(self) -> None:
        self.file_completer.popup().hide()

    def accept_current_file_completion(self) -> bool:
        popup = self.file_completer.popup()
        index = popup.currentIndex()
        if not index.isValid() and self._file_completion_model.rowCount() > 0:
            index = self._file_completion_model.index(0, 0)
        if not index.isValid():
            return False
        path = self._file_completion_model.data(index)
        if not path:
            return False
        self._insert_file_reference(str(path))
        return True

    def _insert_file_reference(self, path: str) -> None:
        mention = self._mention_at_cursor()
        if mention is None:
            return
        mention_start, _query = mention
        reference = f'@"{path}"' if any(char.isspace() for char in path) else f"@{path}"
        cursor = self.textCursor()
        cursor.setPosition(mention_start)
        cursor.setPosition(self.textCursor().position(), QTextCursor.KeepAnchor)
        self._suppress_file_completion = True
        try:
            cursor.insertText(reference)
            self.setTextCursor(cursor)
            self._active_mention_start = None
            self.file_completer.popup().hide()
        finally:
            self._suppress_file_completion = False

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


class ActivitySpinner(QWidget):
    """Small native Qt progress spinner used while an agent is working."""

    FRAME_INTERVAL_MS = 80
    ROTATION_STEP_DEGREES = 30

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        color: str = "#aea2db",
        size: int = 18,
    ) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self._angle = 0
        self.setFixedSize(size, size)
        self.setAccessibleName("SammyAI is working")

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(self.FRAME_INTERVAL_MS)
        self._timer.timeout.connect(self._advance)

    @property
    def angle(self) -> int:
        return self._angle

    def is_running(self) -> bool:
        return self._timer.isActive()

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
            self.update()

    def stop(self) -> None:
        self._timer.stop()

    def _advance(self) -> None:
        self._angle = (
            self._angle - self.ROTATION_STEP_DEGREES
        ) % 360
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        diameter = min(self.width(), self.height()) - 4
        ring = QRectF(
            (self.width() - diameter) / 2,
            (self.height() - diameter) / 2,
            diameter,
            diameter,
        )

        track_pen = QPen(QColor(174, 162, 219, 55), 2)
        track_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(track_pen)
        painter.drawEllipse(ring)

        progress_pen = QPen(self._color, 2.4)
        progress_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(progress_pen)
        painter.drawArc(ring, self._angle * 16, 110 * 16)
        painter.end()


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
        self.activity_indicator: ActivitySpinner | None = None
        if role == "thinking":
            body = QHBoxLayout()
            body.setContentsMargins(0, 0, 0, 0)
            body.setSpacing(8)
            self.activity_indicator = ActivitySpinner(self)
            body.addWidget(self.activity_indicator, 0, Qt.AlignVCenter)
            body.addWidget(self.message_label, 1)
            layout.addLayout(body)
            self.activity_indicator.start()
        else:
            layout.addWidget(self.message_label)

    def set_message_text(self, text: str) -> None:
        self.message_text = text
        self.message_label.setText(text)

    def stop_activity(self) -> None:
        if self.activity_indicator is not None:
            self.activity_indicator.stop()

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
        message.stop_activity()
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
        self._project_name: str | None = None
        self._welcome_text = ""
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

        self.empty_title = ElidedLabel()
        self.empty_title.setObjectName("chatEmptyTitle")
        self.empty_title.setAlignment(Qt.AlignCenter)
        self.empty_title.setWordWrap(False)
        self.empty_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._refresh_welcome_message()
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
            if self.input_field.has_visible_file_completions():
                if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
                    return self.input_field.accept_current_file_completion()
                if event.key() == Qt.Key_Escape:
                    self.input_field.hide_file_completions()
                    return True
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

    def set_project_file_provider(
        self,
        provider: Callable[[], Iterable[str]] | None,
    ) -> None:
        self.input_field.set_project_file_provider(provider)

    def set_project_name(self, project_name: str | None) -> None:
        """Personalize the empty-chat greeting for the active project."""
        cleaned_name = project_name.strip() if project_name else ""
        self._project_name = cleaned_name or None
        self._refresh_welcome_message()

    def _refresh_welcome_message(self) -> None:
        if self._project_name:
            welcome_text = f"How can I help with {self._project_name}?"
        else:
            alternatives = tuple(
                message
                for message in GENERIC_WELCOME_MESSAGES
                if message != self._welcome_text
            )
            welcome_text = random.choice(alternatives or GENERIC_WELCOME_MESSAGES)
        self._welcome_text = welcome_text
        self.empty_title.setText(welcome_text)

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
        self._refresh_welcome_message()
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
