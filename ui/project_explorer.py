"""Project filesystem explorer for SammyAI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QFileSystemModel,
    QLabel,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from sammyai_core.projects import Project


class ProjectExplorer(QWidget):
    """Read-only tree view rooted at the active project's directory."""

    file_activated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("projectExplorer")
        self._project: Project | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.project_name_label = QLabel("No project open")
        self.project_name_label.setObjectName("projectExplorerName")
        self.project_name_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.project_name_label)

        self.project_path_label = QLabel(
            "Open or create a project to browse its files."
        )
        self.project_path_label.setObjectName("projectExplorerPath")
        self.project_path_label.setWordWrap(True)
        self.project_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.project_path_label)

        self.model = QFileSystemModel(self)
        self.model.setReadOnly(True)
        self.model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)
        self.model.setResolveSymlinks(False)

        self.tree = QTreeView()
        self.tree.setObjectName("projectFileTree")
        self.tree.setModel(self.model)
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(False)
        self.tree.setIndentation(16)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.AscendingOrder)
        for column in range(1, self.model.columnCount()):
            self.tree.hideColumn(column)
        self.tree.activated.connect(self._on_activated)
        self.tree.hide()
        layout.addWidget(self.tree, 1)

    @property
    def project(self) -> Project | None:
        return self._project

    def set_project(self, project: Project) -> None:
        self._project = project
        root = str(project.root_path)
        root_index = self.model.setRootPath(root)
        self.tree.setRootIndex(root_index)
        self.project_name_label.setText(project.name)
        self.project_name_label.setToolTip(root)
        self.project_path_label.setText(root)
        self.project_path_label.setToolTip(root)
        self.tree.show()

    def clear_project(self) -> None:
        self._project = None
        self.tree.hide()
        self.project_name_label.setText("No project open")
        self.project_name_label.setToolTip("")
        self.project_path_label.setText(
            "Open or create a project to browse its files."
        )
        self.project_path_label.setToolTip("")

    def _on_activated(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        file_info = self.model.fileInfo(index)
        if file_info.isFile():
            self.file_activated.emit(str(Path(file_info.absoluteFilePath())))
