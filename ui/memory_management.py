"""Persistent-memory management and summary-review dialogs."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from sammyai_core.memory import (
    ConversationSummaryDraft,
    Memory,
    MemoryError,
    MemoryKind,
    MemoryStatus,
    ProjectMemoryService,
    ProvenanceType,
)


class MemoryEditDialog(QDialog):
    def __init__(self, memory: Memory | None = None, parent=None):
        super().__init__(parent)
        self.memory = memory
        self.setWindowTitle("Edit Memory" if memory else "Add Memory")
        self.resize(560, 420)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.kind_combo = QComboBox()
        for kind in MemoryKind:
            self.kind_combo.addItem(kind.display_name, kind.value)
        self.title_input = QLineEdit()
        self.content_input = QTextEdit()
        self.confidence_input = QDoubleSpinBox()
        self.confidence_input.setRange(0.0, 1.0)
        self.confidence_input.setSingleStep(0.05)
        self.confidence_input.setValue(1.0)
        self.status_combo = QComboBox()
        for status in MemoryStatus:
            self.status_combo.addItem(status.value.title(), status.value)

        form.addRow("Type:", self.kind_combo)
        form.addRow("Title:", self.title_input)
        form.addRow("Content:", self.content_input)
        form.addRow("Confidence:", self.confidence_input)
        form.addRow("Status:", self.status_combo)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        save = QPushButton("Save")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self._accept_if_valid)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

        if memory is not None:
            self.kind_combo.setCurrentIndex(
                self.kind_combo.findData(memory.kind.value)
            )
            self.title_input.setText(memory.title)
            self.content_input.setPlainText(memory.content)
            self.confidence_input.setValue(memory.confidence)
            self.status_combo.setCurrentIndex(
                self.status_combo.findData(memory.status.value)
            )

    def values(self) -> tuple[MemoryKind, str, str, float, MemoryStatus]:
        return (
            MemoryKind(self.kind_combo.currentData()),
            self.title_input.text().strip(),
            self.content_input.toPlainText().strip(),
            self.confidence_input.value(),
            MemoryStatus(self.status_combo.currentData()),
        )

    def _accept_if_valid(self) -> None:
        _kind, title, content, _confidence, _status = self.values()
        if not title or not content:
            QMessageBox.warning(
                self,
                "Incomplete Memory",
                "A title and content are required.",
            )
            return
        self.accept()


class SummaryReviewDialog(QDialog):
    """Allow users to edit a summary and choose durable memory suggestions."""

    def __init__(self, draft: ConversationSummaryDraft, parent=None):
        super().__init__(parent)
        self.draft = draft
        self.setWindowTitle("Review Conversation Memory")
        self.resize(900, 650)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.title_input = QLineEdit(draft.title)
        self.summary_input = QTextEdit()
        self.summary_input.setPlainText(draft.content)
        form.addRow("Title:", self.title_input)
        form.addRow("Summary:", self.summary_input)
        layout.addLayout(form)

        layout.addWidget(
            QLabel(
                "Select the durable facts or decisions to save as structured "
                "project memory:"
            )
        )
        self.suggestions_table = QTableWidget(
            len(draft.suggested_memories),
            4,
        )
        self.suggestions_table.setHorizontalHeaderLabels(
            ["Save", "Type", "Title", "Content"]
        )
        self.suggestions_table.horizontalHeader().setSectionResizeMode(
            3,
            QHeaderView.Stretch,
        )
        for row, suggestion in enumerate(draft.suggested_memories):
            include = QTableWidgetItem()
            include.setFlags(
                Qt.ItemIsEnabled
                | Qt.ItemIsSelectable
                | Qt.ItemIsUserCheckable
            )
            include.setCheckState(Qt.Checked)
            self.suggestions_table.setItem(row, 0, include)
            self.suggestions_table.setItem(
                row,
                1,
                QTableWidgetItem(suggestion.kind.display_name),
            )
            self.suggestions_table.item(row, 1).setFlags(
                self.suggestions_table.item(row, 1).flags()
                & ~Qt.ItemIsEditable
            )
            self.suggestions_table.setItem(
                row,
                2,
                QTableWidgetItem(suggestion.title),
            )
            self.suggestions_table.setItem(
                row,
                3,
                QTableWidgetItem(suggestion.content),
            )
        layout.addWidget(self.suggestions_table)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        save = QPushButton("Save Approved Memory")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self._accept_if_valid)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def reviewed_draft(self) -> ConversationSummaryDraft:
        suggestions = tuple(
            replace(
                suggestion,
                title=self.suggestions_table.item(row, 2).text().strip(),
                content=self.suggestions_table.item(row, 3).text().strip(),
            )
            for row, suggestion in enumerate(self.draft.suggested_memories)
        )
        return replace(
            self.draft,
            title=self.title_input.text().strip(),
            content=self.summary_input.toPlainText().strip(),
            suggested_memories=suggestions,
        )

    def selected_memory_indices(self) -> tuple[int, ...]:
        return tuple(
            row
            for row in range(self.suggestions_table.rowCount())
            if self.suggestions_table.item(row, 0).checkState() == Qt.Checked
        )

    def _accept_if_valid(self) -> None:
        if (
            not self.title_input.text().strip()
            or not self.summary_input.toPlainText().strip()
        ):
            QMessageBox.warning(
                self,
                "Incomplete Summary",
                "A summary title and content are required.",
            )
            return
        self.accept()


class MemoryManagementDialog(QDialog):
    def __init__(self, memory_service: ProjectMemoryService, parent=None):
        super().__init__(parent)
        self.memory_service = memory_service
        self.memories: list[Memory] = []
        self.setWindowTitle("Project Memory")
        self.resize(1_000, 700)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_memories_tab(), "Memories")
        self.tabs.addTab(self._build_summaries_tab(), "Conversation Summaries")
        layout.addWidget(self.tabs)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        close_row.addWidget(close)
        layout.addLayout(close_row)

        self.refresh()

    def _build_memories_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        filters = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search memories...")
        self.kind_filter = QComboBox()
        self.kind_filter.addItem("All Types", None)
        for kind in MemoryKind:
            self.kind_filter.addItem(kind.display_name, kind.value)
        self.status_filter = QComboBox()
        self.status_filter.addItem("Active", MemoryStatus.ACTIVE.value)
        self.status_filter.addItem("Archived", MemoryStatus.ARCHIVED.value)
        self.status_filter.addItem("All Statuses", None)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        self.search_input.returnPressed.connect(self.refresh)
        self.kind_filter.currentIndexChanged.connect(self.refresh)
        self.status_filter.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self.search_input, 1)
        filters.addWidget(self.kind_filter)
        filters.addWidget(self.status_filter)
        filters.addWidget(refresh)
        layout.addLayout(filters)

        self.memory_table = QTableWidget(0, 5)
        self.memory_table.setHorizontalHeaderLabels(
            ["Type", "Title", "Status", "Confidence", "Updated"]
        )
        self.memory_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.memory_table.setSelectionMode(QTableWidget.SingleSelection)
        self.memory_table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.Stretch,
        )
        self.memory_table.itemSelectionChanged.connect(
            self._show_selected_memory
        )
        layout.addWidget(self.memory_table, 2)

        self.memory_detail = QTextEdit()
        self.memory_detail.setReadOnly(True)
        layout.addWidget(self.memory_detail, 1)

        buttons = QHBoxLayout()
        add = QPushButton("Add")
        edit = QPushButton("Edit")
        toggle = QPushButton("Archive / Reactivate")
        delete = QPushButton("Delete")
        add.clicked.connect(self._add_memory)
        edit.clicked.connect(self._edit_memory)
        toggle.clicked.connect(self._toggle_memory_status)
        delete.clicked.connect(self._delete_memory)
        buttons.addWidget(add)
        buttons.addWidget(edit)
        buttons.addWidget(toggle)
        buttons.addStretch()
        buttons.addWidget(delete)
        layout.addLayout(buttons)
        return tab

    def _build_summaries_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.summary_table = QTableWidget(0, 3)
        self.summary_table.setHorizontalHeaderLabels(
            ["Title", "Messages", "Updated"]
        )
        self.summary_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.summary_table.setSelectionMode(QTableWidget.SingleSelection)
        self.summary_table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.Stretch,
        )
        self.summary_table.itemSelectionChanged.connect(
            self._show_selected_summary
        )
        layout.addWidget(self.summary_table, 2)
        self.summary_detail = QTextEdit()
        self.summary_detail.setReadOnly(True)
        layout.addWidget(self.summary_detail, 1)
        delete = QPushButton("Delete Summary")
        delete.clicked.connect(self._delete_summary)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(delete)
        layout.addLayout(row)
        self.summaries = []
        return tab

    def refresh(self, *_args) -> None:
        try:
            kind_data = self.kind_filter.currentData()
            status_data = self.status_filter.currentData()
            self.memories = self.memory_service.list_memories(
                kind=MemoryKind(kind_data) if kind_data else None,
                status=MemoryStatus(status_data) if status_data else None,
                search=self.search_input.text(),
            )
            self.summaries = self.memory_service.list_summaries()
        except MemoryError as error:
            QMessageBox.warning(self, "Project Memory", str(error))
            return

        self.memory_table.setRowCount(len(self.memories))
        for row, memory in enumerate(self.memories):
            values = (
                memory.kind.display_name,
                memory.title,
                memory.status.value.title(),
                f"{memory.confidence:.2f}",
                memory.updated_at.astimezone().strftime("%Y-%m-%d %H:%M"),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if column == 0:
                    item.setData(Qt.UserRole, memory.id)
                self.memory_table.setItem(row, column, item)

        self.summary_table.setRowCount(len(self.summaries))
        for row, summary in enumerate(self.summaries):
            values = (
                summary.title,
                str(summary.message_count),
                summary.updated_at.astimezone().strftime("%Y-%m-%d %H:%M"),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if column == 0:
                    item.setData(Qt.UserRole, summary.id)
                self.summary_table.setItem(row, column, item)

        self.memory_detail.clear()
        self.summary_detail.clear()

    def _selected_memory(self) -> Memory | None:
        row = self.memory_table.currentRow()
        return self.memories[row] if 0 <= row < len(self.memories) else None

    def _selected_summary(self):
        row = self.summary_table.currentRow()
        return self.summaries[row] if 0 <= row < len(self.summaries) else None

    def _show_selected_memory(self) -> None:
        memory = self._selected_memory()
        if memory is None:
            self.memory_detail.clear()
            return
        provenance = "\n".join(
            f"- {source.source_type.value.title()}: {source.source_label}"
            + (f"\n  {source.excerpt}" if source.excerpt else "")
            for source in memory.provenance
        ) or "- No provenance recorded"
        self.memory_detail.setPlainText(
            f"{memory.content}\n\nProvenance:\n{provenance}"
        )

    def _show_selected_summary(self) -> None:
        summary = self._selected_summary()
        self.summary_detail.setPlainText(summary.content if summary else "")

    def _add_memory(self) -> None:
        dialog = MemoryEditDialog(parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        kind, title, content, confidence, _status = dialog.values()
        try:
            self.memory_service.create_memory(
                kind,
                title,
                content,
                confidence=confidence,
                source_type=ProvenanceType.USER,
                source_label="Manual entry",
            )
        except MemoryError as error:
            QMessageBox.warning(self, "Unable to Save Memory", str(error))
        self.refresh()

    def _edit_memory(self) -> None:
        memory = self._selected_memory()
        if memory is None:
            return
        dialog = MemoryEditDialog(memory, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.memory_service.update_memory(
                memory.id,
                kind=dialog.values()[0],
                title=dialog.values()[1],
                content=dialog.values()[2],
                confidence=dialog.values()[3],
                status=dialog.values()[4],
            )
        except MemoryError as error:
            QMessageBox.warning(self, "Unable to Update Memory", str(error))
        self.refresh()

    def _toggle_memory_status(self) -> None:
        memory = self._selected_memory()
        if memory is None:
            return
        status = (
            MemoryStatus.ARCHIVED
            if memory.status == MemoryStatus.ACTIVE
            else MemoryStatus.ACTIVE
        )
        try:
            self.memory_service.update_memory(
                memory.id,
                kind=memory.kind,
                title=memory.title,
                content=memory.content,
                confidence=memory.confidence,
                status=status,
            )
        except MemoryError as error:
            QMessageBox.warning(self, "Unable to Update Memory", str(error))
        self.refresh()

    def _delete_memory(self) -> None:
        memory = self._selected_memory()
        if memory is None:
            return
        if (
            QMessageBox.question(
                self,
                "Delete Memory",
                f"Delete '{memory.title}' and its provenance?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        self.memory_service.delete_memory(memory.id)
        self.refresh()

    def _delete_summary(self) -> None:
        summary = self._selected_summary()
        if summary is None:
            return
        if (
            QMessageBox.question(
                self,
                "Delete Summary",
                f"Delete '{summary.title}'?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        self.memory_service.delete_summary(summary.id)
        self.refresh()
