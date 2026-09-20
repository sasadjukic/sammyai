"""A read-only, keyboard accessible review surface inside a document tab."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFontDatabase, QSyntaxHighlighter, QTextCharFormat, QTextCursor, QTextFormat
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget

from editing.review_session import HunkState
from ui.code_editor import _extract_color_from_stylesheet
from ui.editor_decorations import EditorDecorationManager


def review_color(token, property_name):
    return _extract_color_from_stylesheet(f"QLabel#review{token}", property_name)


class ReviewHighlighter(QSyntaxHighlighter):
    def __init__(self, view):
        super().__init__(view.document())
        self.view = view
        self.tokens = []
        self.formats = {}
        for token in ("Addition", "Deletion", "Pending", "Gutter"):
            fmt = QTextCharFormat()
            foreground = review_color(token, "color")
            background = review_color(token, "background-color")
            if foreground:
                fmt.setForeground(QColor(foreground))
            if background:
                fmt.setBackground(QColor(background))
            self.formats[token] = fmt

    def highlightBlock(self, text):
        index = self.currentBlock().blockNumber()
        if index >= len(self.tokens):
            return
        token = self.tokens[index]
        if token is None:
            return
        self.setFormat(0, len(text), self.formats[token])


class InlineReviewWidget(QWidget):
    decisions_changed = Signal()
    apply_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, review, description, parent=None):
        super().__init__(parent)
        self.setObjectName("inlineReview")
        self.review = review
        self.current_index = 0
        self._header_blocks = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        title = QLabel(f"Review changes · {review.change.relative_path}")
        title.setTextFormat(Qt.PlainText)
        title.setObjectName("reviewTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        self.description = QLabel(description if len(description) <= 240 else description[:237] + "…")
        self.description.setToolTip(description)
        self.description.setTextFormat(Qt.PlainText)
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        navigation = QHBoxLayout()
        self.previous_button = self._button("Previous", "Go to the previous hunk", lambda: self.navigate(-1))
        self.next_button = self._button("Next", "Go to the next hunk", lambda: self.navigate(1))
        self.hunk_label = QLabel()
        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.hunk_label, 1)
        navigation.addWidget(self.next_button)
        layout.addLayout(navigation)
        decisions = QHBoxLayout()
        self.accept_button = self._button("Accept Hunk", "Keep this proposed change", lambda: self.decide(HunkState.ACCEPTED))
        self.reject_button = self._button("Reject Hunk", "Keep the original text for this hunk", lambda: self.decide(HunkState.REJECTED))
        self.accept_all_button = self._button("Accept All", "Accept every hunk in this file", lambda: self.decide_all(HunkState.ACCEPTED))
        self.reject_all_button = self._button("Reject All", "Reject every hunk in this file", lambda: self.decide_all(HunkState.REJECTED))
        for button in (self.accept_button, self.reject_button, self.accept_all_button, self.reject_all_button):
            decisions.addWidget(button)
        layout.addLayout(decisions)
        self.view = QPlainTextEdit()
        self.view.setObjectName("inlineReviewText")
        self.view.setReadOnly(True)
        self.view.setAccessibleName("Inline diff: minus is removed text, plus is proposed text")
        self.view.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.view.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.decorations = EditorDecorationManager(self.view)
        self.view.decorations = self.decorations
        self.highlighter = ReviewHighlighter(self.view)
        layout.addWidget(self.view, 1)
        self.status_label = QLabel()
        self.status_label.setTextFormat(Qt.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("Review status")
        layout.addWidget(self.status_label)
        footer = QHBoxLayout()
        self.cancel_button = self._button("Cancel Review", "Discard decisions for this entire proposal and resume editing", self.cancel_requested.emit)
        self.apply_button = self._button("Apply Reviewed Changes", "Apply accepted hunks after all files have been reviewed", self.apply_requested.emit)
        footer.addWidget(self.cancel_button)
        footer.addStretch()
        footer.addWidget(self.apply_button)
        layout.addLayout(footer)
        self._render()
        self.view.cursorPositionChanged.connect(self._select_at_cursor)

    def _button(self, text, tooltip, callback):
        button = QPushButton(text)
        button.setToolTip(tooltip)
        button.setAccessibleName(text)
        button.clicked.connect(callback)
        return button

    def _render(self):
        rows, tokens = [], []
        self._header_blocks = []

        def append_text(text, prefix, token=None):
            for line in text.splitlines(keepends=True):
                rows.append(prefix + line.rstrip("\r\n"))
                tokens.append(token)
                if not line.endswith(("\n", "\r")):
                    rows.append("      [No newline at end of file]")
                    tokens.append("Gutter")

        original = self.review.change.before_content or ""
        position = 0
        for index, hunk in enumerate(self.review.hunks):
            append_text(original[position:hunk.start], "    ")
            self._header_blocks.append(len(rows))
            state = self.review.states[hunk.id]
            rows.append(f"@@ Hunk {index + 1} · {state.value.upper()} · −{hunk.original_start_line} / +{hunk.proposed_start_line} @@")
            tokens.append({HunkState.PENDING: "Pending", HunkState.ACCEPTED: "Addition", HunkState.REJECTED: "Deletion"}[state])
            append_text(hunk.removed, "−   ", "Deletion")
            append_text(hunk.inserted, "+   ", "Addition")
            if not hunk.removed and not hunk.inserted:
                rows.append(f"    [{self.review.change.kind.value.title()} empty file]")
                tokens.append("Gutter")
            position = hunk.end
        append_text(original[position:], "    ")
        self.highlighter.tokens = tokens
        self.view.setPlainText("\n".join(rows))
        self.highlighter.rehighlight()
        self._show_current()

    def _show_current(self):
        count = len(self.review.hunks)
        self.previous_button.setEnabled(count > 1)
        self.next_button.setEnabled(count > 1)
        self.accept_button.setEnabled(bool(count))
        self.reject_button.setEnabled(bool(count))
        if not count:
            self.hunk_label.setText("No text changes")
            return
        state = self.review.states[self.review.hunks[self.current_index].id]
        self.hunk_label.setText(f"Hunk {self.current_index + 1} of {count} · {state.value.title()}")
        cursor = QTextCursor(self.view.document().findBlockByNumber(self._header_blocks[self.current_index]))
        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        color = review_color("Current", "background-color")
        if color:
            selection.format.setBackground(QColor(color))
        self.decorations.set("review-current", [selection])

    def _select_at_cursor(self):
        block = self.view.textCursor().blockNumber()
        for index, header in enumerate(self._header_blocks):
            if header <= block:
                self.current_index = index
        self._show_current()

    def navigate(self, delta):
        if not self.review.hunks:
            return
        self.current_index = (self.current_index + delta) % len(self.review.hunks)
        self._scroll_to_current()

    def _scroll_to_current(self):
        if self._header_blocks:
            self.view.setTextCursor(QTextCursor(self.view.document().findBlockByNumber(self._header_blocks[self.current_index])))
            self.view.centerCursor()
        self._show_current()

    def decide(self, state):
        if self.review.hunks:
            self.review.decide(self.review.hunks[self.current_index].id, state)
            self._refresh_decisions()

    def decide_all(self, state):
        self.review.decide_all(state)
        self._refresh_decisions()

    def _refresh_decisions(self):
        index = self.current_index
        self.decorations.set("search", [])
        self.view.blockSignals(True)
        self._render()
        self.view.blockSignals(False)
        self.current_index = index
        self._scroll_to_current()
        self.view.textChanged.emit()
        self.decisions_changed.emit()

    def set_batch_status(self, pending, files, *, conflict=None, writes_files=True):
        self.apply_button.setEnabled(not pending and not conflict)
        self.apply_button.setText("Apply Reviewed Changes" if writes_files else "Apply to Draft")
        if conflict:
            self.status_label.setText(f"Conflict: {conflict}\nCancel this review and request a new proposal from the current text.")
        else:
            destination = "Saves accepted changes to disk." if writes_files else "Updates this draft; use Save to write it to disk."
            self.status_label.setText(f"{pending} pending hunk(s) across {files} file(s). {destination}")

    def dispose(self):
        # Stop deferred highlighting before the review document is deleted.
        self.highlighter.setDocument(None)
