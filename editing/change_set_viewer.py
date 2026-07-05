"""Reusable multi-file review dialog for structured change sets."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from .change_sets import ChangeSetPreview
from .diff_viewer import DiffSyntaxHighlighter


class ChangeSetReviewDialog(QDialog):
    """Display every file diff before a caller applies a change set."""

    def __init__(self, preview: ChangeSetPreview, parent=None):
        super().__init__(parent)
        self.preview = preview
        self.setWindowTitle("Review Change Set")
        self.resize(1_000, 700)

        layout = QVBoxLayout(self)
        self.description_label = QLabel(preview.description)
        self.description_label.setObjectName("changeSetDescription")
        layout.addWidget(self.description_label)

        self.summary_label = QLabel(
            f"{len(preview.files)} file(s) | "
            f"+{preview.additions} -{preview.deletions}"
        )
        self.summary_label.setObjectName("changeSetSummary")
        layout.addWidget(self.summary_label)

        content_layout = QHBoxLayout()
        self.file_list = QListWidget()
        self.file_list.setObjectName("changeSetFiles")
        self.file_list.setMinimumWidth(260)
        for file_preview in preview.files:
            self.file_list.addItem(
                f"{file_preview.kind.value.upper()}  "
                f"{file_preview.relative_path}"
            )
        content_layout.addWidget(self.file_list)

        self.diff_view = QTextEdit()
        self.diff_view.setObjectName("changeSetDiff")
        self.diff_view.setReadOnly(True)
        self.diff_highlighter = DiffSyntaxHighlighter(self.diff_view.document())
        content_layout.addWidget(self.diff_view, 1)
        layout.addLayout(content_layout, 1)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.reject_button = QPushButton("Reject")
        self.apply_button = QPushButton("Apply Change Set")
        self.reject_button.clicked.connect(self.reject)
        self.apply_button.clicked.connect(self.accept)
        button_layout.addWidget(self.reject_button)
        button_layout.addWidget(self.apply_button)
        layout.addLayout(button_layout)

        self.file_list.currentRowChanged.connect(self._show_file)
        if preview.files:
            self.file_list.setCurrentRow(0)
        else:
            self.apply_button.setEnabled(False)

    def _show_file(self, row: int) -> None:
        if row < 0 or row >= len(self.preview.files):
            self.diff_view.clear()
            return
        self.diff_view.setPlainText(self.preview.files[row].unified_diff)
