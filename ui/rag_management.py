"""Read-only project and legacy context index inspection."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)


class ContextIndexDialog(QDialog):
    """Inspect index attribution without deleting chunks or source files."""

    def __init__(self, rag_system, project_service=None, parent=None):
        super().__init__(parent)
        self.rag_system = rag_system
        self.project_service = project_service
        self.project = project_service.active_project if project_service else None
        self.entries = ()
        self.setWindowTitle("Indexed Files")
        self.setObjectName("contextIndexDialog")
        self.resize(760, 500)
        self.setMinimumSize(520, 380)
        layout = QVBoxLayout(self)
        title = QLabel("Context index")
        title.setObjectName("contextIndexTitle")
        layout.addWidget(title)
        description = QLabel(
            "Project files are synchronized automatically. Older unassigned entries "
            "are preserved for inspection. To use an external reference in a project, "
            "choose Project Context > Import Reference File…"
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.scope_combo = QComboBox()
        self.scope_combo.setAccessibleName("Index scope")
        if self.project:
            self.scope_combo.addItem("Active project", "active")
        self.scope_combo.addItem("All projects and legacy entries", "all")
        self.scope_combo.addItem("Unassigned legacy entries", "legacy")
        self.scope_combo.currentIndexChanged.connect(self._show_entries)
        layout.addWidget(self.scope_combo)
        self.file_list = QTreeWidget()
        self.file_list.setAccessibleName("Indexed files")
        self.file_list.setHeaderLabels(["File", "Project", "Chunks"])
        self.file_list.setRootIsDecorated(False)
        self.file_list.setAlternatingRowColors(True)
        self.file_list.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.file_list.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.file_list.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.file_list.currentItemChanged.connect(self._show_details)
        layout.addWidget(self.file_list, 1)
        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)
        self.details_label = QLabel("Select a file to inspect its source path.")
        self.details_label.setTextFormat(Qt.PlainText)
        self.details_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.details_label.setWordWrap(True)
        layout.addWidget(self.details_label)
        buttons = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip("Reload index metadata without changing the index")
        self.refresh_button.clicked.connect(self.load_files)
        self.copy_path_button = QPushButton("Copy Source Path")
        self.copy_path_button.setToolTip("Copy the original file path to the clipboard")
        self.copy_path_button.setEnabled(False)
        self.copy_path_button.clicked.connect(self._copy_source_path)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.copy_path_button)
        buttons.addStretch()
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        self.load_files()

    def load_files(self):
        try:
            self.entries = self.rag_system.get_indexed_files()
        except Exception as error:
            self.entries = ()
            self.file_list.clear()
            self.summary_label.setText("Unable to read the context index. Try Refresh.")
            self.details_label.setText(str(error))
            self.copy_path_button.setEnabled(False)
            return
        self._show_entries()

    def _project_label(self, project_id):
        if project_id is None:
            return "Unassigned (legacy)"
        project = self.project_service.get_project(project_id) if self.project_service else None
        return project.name if project else f"Project {project_id}"

    def _show_entries(self, *_args):
        scope = self.scope_combo.currentData()
        entries = [entry for entry in self.entries if (
            scope == "all"
            or (scope == "legacy" and entry.project_id is None)
            or (scope == "active" and self.project and entry.project_id == self.project.id)
        )]
        self.file_list.clear()
        project_labels = {project_id: self._project_label(project_id) for project_id in {entry.project_id for entry in entries}}
        for entry in entries:
            item = QTreeWidgetItem([
                Path(entry.file_path).name if entry.file_path else "Unknown source",
                project_labels[entry.project_id], str(entry.chunk_count),
            ])
            item.setData(0, Qt.UserRole, entry)
            item.setToolTip(0, entry.file_path or "Source path was not recorded")
            item.setToolTip(1, entry.project_id or "No project was assigned to these chunks")
            self.file_list.addTopLevelItem(item)
        self.summary_label.setText(
            f"{len(entries)} indexed source(s) · {sum(entry.chunk_count for entry in entries)} chunks"
            if entries else "No indexed files in this view."
        )
        self._show_details()

    def _show_details(self, *_args):
        item = self.file_list.currentItem()
        entry = item.data(0, Qt.UserRole) if item else None
        self.copy_path_button.setEnabled(bool(entry and entry.file_path))
        if entry is None:
            self.details_label.setText("Select a file to inspect its source path.")
            return
        attribution = f"Project ID: {entry.project_id}" if entry.project_id else "Unassigned legacy entry; excluded from project-scoped retrieval."
        self.details_label.setText(f"Source: {entry.file_path or '(not recorded)'}\n{attribution}")

    def _copy_source_path(self):
        item = self.file_list.currentItem()
        if item:
            entry = item.data(0, Qt.UserRole)
            if entry.file_path:
                QApplication.clipboard().setText(entry.file_path)
