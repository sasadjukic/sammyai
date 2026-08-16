"""Project filesystem explorer for SammyAI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QFileSystemModel,
    QLabel,
    QMenu,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from sammyai_core.projects import Project


class ProjectExplorer(QWidget):
    """Project-scoped tree view with file-specific context actions."""

    file_activated = Signal(str)
    copy_requested = Signal(str)
    paste_requested = Signal(str, str)
    rename_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("projectExplorer")
        self._project: Project | None = None
        self._copied_file: Path | None = None

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
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        for column in range(1, self.model.columnCount()):
            self.tree.hideColumn(column)
        self.tree.activated.connect(self._on_activated)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.hide()
        layout.addWidget(self.tree, 1)

    @property
    def project(self) -> Project | None:
        return self._project

    @property
    def copied_file(self) -> Path | None:
        return self._copied_file

    def set_project(self, project: Project) -> None:
        if self._project is None or self._project.id != project.id:
            self._copied_file = None
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
        self._copied_file = None
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

    def set_copied_file(self, path: str | Path | None) -> None:
        self._copied_file = Path(path) if path is not None else None

    def update_copied_file_after_rename(
        self,
        source: str | Path,
        target: str | Path,
    ) -> None:
        if self._copied_file == Path(source):
            self._copied_file = Path(target)

    def clear_copied_file_if(self, path: str | Path) -> None:
        if self._copied_file == Path(path):
            self._copied_file = None

    def _show_context_menu(self, position) -> None:
        index = self.tree.indexAt(position)
        if index.isValid():
            self.tree.setCurrentIndex(index)
        menu = self._build_context_menu(index)
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _build_context_menu(self, index: QModelIndex) -> QMenu:
        """Build the tree-only file menu; exposed for focused UI tests."""
        menu = QMenu(self.tree)
        selected_path: Path | None = None
        selected_is_file = False
        selected_is_directory = False
        if index.isValid():
            file_info = self.model.fileInfo(index)
            selected_path = Path(file_info.absoluteFilePath())
            selected_is_file = file_info.isFile()
            selected_is_directory = file_info.isDir()

        copy_action = menu.addAction("Copy")
        copy_action.setEnabled(selected_is_file)
        if selected_path is not None:
            copy_action.triggered.connect(
                lambda _checked=False, path=selected_path: self.copy_requested.emit(
                    str(path)
                )
            )

        paste_action = menu.addAction("Paste")
        destination = self._paste_destination(
            selected_path,
            selected_is_file=selected_is_file,
            selected_is_directory=selected_is_directory,
        )
        can_paste = (
            self._copied_file is not None
            and self._copied_file.is_file()
            and destination is not None
        )
        paste_action.setEnabled(can_paste)
        if can_paste:
            paste_action.triggered.connect(
                lambda _checked=False,
                source=self._copied_file,
                target=destination: self.paste_requested.emit(
                    str(source),
                    str(target),
                )
            )

        menu.addSeparator()
        rename_action = menu.addAction("Rename")
        rename_action.setEnabled(selected_is_file)
        delete_action = menu.addAction("Delete")
        delete_action.setEnabled(selected_is_file)
        if selected_path is not None:
            rename_action.triggered.connect(
                lambda _checked=False, path=selected_path: self.rename_requested.emit(
                    str(path)
                )
            )
            delete_action.triggered.connect(
                lambda _checked=False, path=selected_path: self.delete_requested.emit(
                    str(path)
                )
            )
        return menu

    def _paste_destination(
        self,
        selected_path: Path | None,
        *,
        selected_is_file: bool,
        selected_is_directory: bool,
    ) -> Path | None:
        if self._project is None:
            return None
        if selected_path is None:
            return self._project.root_path
        if selected_is_directory:
            return selected_path
        if selected_is_file:
            return selected_path.parent
        return None
