import sys
import re
import os
import logging
from pathlib import Path
from threading import Lock
from typing import Optional
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPlainTextEdit, QFileDialog, QMessageBox, QToolBar,
    QMenu, QWidget, QLabel, QDockWidget, QLineEdit, QTextEdit,
    QHBoxLayout, QPushButton, QVBoxLayout, QSizePolicy, QStyle, QDialog,
    QInputDialog
)
from PySide6.QtGui import QAction, QKeySequence, QIcon, QPainter, QColor, QFont, QPalette, QTextCursor, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt, QRect, QSize, QTimer, Signal, Slot
from api_key_manager import APIKeyManager
from ui.llm_setup import LLMSetupDialog

from llm.chat_manager import MessageRole

# Chat UI
from ui.chat_panel import ChatPanel

# Diff-based editing
from editing.diff_viewer import DiffViewerWidget
from editing.diff_manager import DiffManager
from editing.change_set_viewer import ChangeSetReviewDialog

# LLM Settings UI
from ui.llm_settings import LLMSettingsDialog

# RAG management UI
from ui.rag_management import RAGFileManagementDialog
from ui.memory_management import (
    MemoryManagementDialog,
    SummaryReviewDialog,
)
from ui.project_explorer import ProjectExplorer
from sammyai_core.bootstrap import RuntimeServices, build_runtime_services
from sammyai_core.documents import DocumentService
from sammyai_core.logging_config import configure_logging, install_exception_hook
from sammyai_core.paths import AppPaths, get_app_paths, migrate_legacy_runtime_data
from sammyai_core.resources import asset_path, source_root
from sammyai_core.tasks import BackgroundTaskRunner
from sammyai_core.projects import Project, ProjectError
from sammyai_core.agent_workflows import (
    AgentRunResult,
    AgentType,
    AgentWorkflowService,
)
from sammyai_core.file_tools import FileToolError
from sammyai_core.memory import (
    ConversationSummarizer,
    ConversationSummaryDraft,
    MemoryError,
)


logger = logging.getLogger("sammyai")


# --- Module-level helper functions ---

def _extract_color_from_stylesheet(selector: str, css_property: str) -> Optional[str]:
    """Extract a CSS color value from the application stylesheet.
    
    Args:
        selector: CSS selector (e.g., 'QPlainTextEdit')
        css_property: CSS property name (e.g., 'color', 'background-color')
        
    Returns:
        Color string or None if not found
    """
    try:
        ss = QApplication.instance().styleSheet() or ""
        pattern = rf"{selector}\s*\{{[^}}]*(?<!-){css_property}\s*:\s*([^;]+);"
        m = re.search(pattern, ss)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return None


class SearchWidget(QWidget):
    """A search widget with text input, match counter, and navigation buttons."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        # Main vertical layout to hold both rows
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        
        # First row: Search controls
        search_layout = QHBoxLayout()
        
        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Find...")
        self.search_input.setMinimumWidth(200)
        search_layout.addWidget(self.search_input)
        
        # Match counter label
        self.match_label = QLabel("No matches")
        self.match_label.setMinimumWidth(100)
        self.match_label.setStyleSheet("color: #dddddd;")  # Light text for dark theme visibility
        search_layout.addWidget(self.match_label)
        
        # Previous button
        self.prev_button = QPushButton("◀")
        self.prev_button.setMaximumWidth(40)
        self.prev_button.setToolTip("Previous match (Shift+Enter)")
        self.prev_button.setEnabled(False)
        search_layout.addWidget(self.prev_button)
        
        # Next button
        self.next_button = QPushButton("▶")
        self.next_button.setMaximumWidth(40)
        self.next_button.setToolTip("Next match (Enter)")
        self.next_button.setEnabled(False)
        search_layout.addWidget(self.next_button)
        
        # Close button
        self.close_button = QPushButton("✕")
        self.close_button.setMaximumWidth(40)
        self.close_button.setToolTip("Close (Esc)")
        search_layout.addWidget(self.close_button)
        
        search_layout.addStretch()
        main_layout.addLayout(search_layout)
        
        # Second row: Replace controls (initially hidden)
        self.replace_container = QWidget()
        replace_layout = QHBoxLayout()
        replace_layout.setContentsMargins(0, 0, 0, 0)
        
        # Replace input
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Replace with...")
        self.replace_input.setMinimumWidth(200)
        replace_layout.addWidget(self.replace_input)
        
        # Replace button
        self.replace_button = QPushButton("Replace")
        self.replace_button.setToolTip("Replace current match")
        self.replace_button.setEnabled(False)
        replace_layout.addWidget(self.replace_button)
        
        # Replace All button
        self.replace_all_button = QPushButton("Replace All")
        self.replace_all_button.setToolTip("Replace all matches")
        self.replace_all_button.setEnabled(False)
        replace_layout.addWidget(self.replace_all_button)
        
        replace_layout.addStretch()
        self.replace_container.setLayout(replace_layout)
        self.replace_container.hide()  # Initially hidden
        main_layout.addWidget(self.replace_container)
        
        self.setLayout(main_layout)
        
    def show_replace_controls(self, show=True):
        """Show or hide the replace controls."""
        if show:
            self.replace_container.show()
        else:
            self.replace_container.hide()
    
    def update_match_count(self, current, total):
        """Update the match counter display."""
        if total == 0:
            self.match_label.setText("No matches")
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)
            self.replace_button.setEnabled(False)
            self.replace_all_button.setEnabled(False)
        else:
            self.match_label.setText(f"{current} of {total} matches")
            self.prev_button.setEnabled(total > 1)
            self.next_button.setEnabled(total > 1)
            self.replace_button.setEnabled(True)
            self.replace_all_button.setEnabled(True)
    
    def get_search_text(self):
        """Return the current search text."""
        return self.search_input.text()
    
    def get_replace_text(self):
        """Return the current replace text."""
        return self.replace_input.text()
    
    def focus_input(self):
        """Set focus to the search input field."""
        self.search_input.setFocus()
        self.search_input.selectAll()


class TextEditor(QMainWindow):
    # Signals for LLM communication
    llm_response_received = Signal(str)
    llm_error_occurred = Signal(str)
    dbe_diff_ready = Signal(str, str, str)  # original, modified, user_request
    context_sync_finished = Signal(str, object, bool)
    agent_run_completed = Signal(object)
    agent_progress = Signal(str)
    memory_summary_ready = Signal(object)
    memory_summary_failed = Signal(str)
    
    def __init__(
        self,
        *,
        services: RuntimeServices | None = None,
        app_paths: AppPaths | None = None,
    ):
        super().__init__()

        self.app_paths = app_paths or get_app_paths()
        self.document_service = DocumentService()
        self.task_runner = BackgroundTaskRunner()
        self._llm_lock = Lock()

        self.setGeometry(200, 100, 900, 600)

        # Create a container widget to hold search widget and editor
        container = QWidget()
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # Create search widget (initially hidden)
        self.search_widget = SearchWidget()
        self.search_widget.hide()
        container_layout.addWidget(self.search_widget)
        
        # Use a CodeEditor (QPlainTextEdit subclass) that supports line numbers
        self.editor = CodeEditor()
        container_layout.addWidget(self.editor)
        
        container.setLayout(container_layout)
        self.setCentralWidget(container)
        
        # Search tracking variables
        self.current_matches = []  # List of QTextCursor positions for matches
        self.current_match_index = 0  # Current match being viewed
        
        # Connect search widget signals
        self.search_widget.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_widget.next_button.clicked.connect(self._next_match)
        self.search_widget.prev_button.clicked.connect(self._previous_match)
        self.search_widget.close_button.clicked.connect(self._close_search)
        self.search_widget.replace_button.clicked.connect(self._replace_current)
        self.search_widget.replace_all_button.clicked.connect(self._replace_all)
        
        # Install event filter for Enter/Escape keys in search widget
        self.search_widget.search_input.installEventFilter(self)

        # create actions first so toolbar and menubar can reuse them
        self.create_actions()
        self.create_menubar()
        self.create_toolbar()
        # create status bar showing Ln/Col and word count
        self.create_statusbar()
        self.current_file = None
        self.untitled_count = 1
        self.editor.document().modificationChanged.connect(self.update_window_title)
        self.update_window_title()

        # --- Initialize application services outside of the UI layer ---
        self.runtime_services = services or build_runtime_services(self.app_paths)
        self.rag_system = self.runtime_services.rag_system
        self.chat_manager = self.runtime_services.chat_manager
        self.llm_config = self.runtime_services.llm_config
        self.llm_client = self.runtime_services.llm_client
        self.project_service = self.runtime_services.project_service
        self.context_engine = getattr(
            self.runtime_services,
            "context_engine",
            None,
        )
        self.file_tools = getattr(self.runtime_services, "file_tools", None)
        self.memory_service = getattr(
            self.runtime_services,
            "memory_service",
            None,
        )
        self.conversation_summarizer = getattr(
            self.runtime_services,
            "conversation_summarizer",
            None,
        ) or ConversationSummarizer()
        self.agent_workflows = getattr(
            self.runtime_services,
            "agent_workflows",
            None,
        ) or AgentWorkflowService(self.file_tools)
        try:
            self.active_agent_type = AgentType(
                self.chat_manager.get_session_metadata(
                    "agent_type",
                    AgentType.GENERAL.value,
                )
            )
        except ValueError:
            self.active_agent_type = AgentType.GENERAL
        self._update_change_set_history_actions()
        self.rebuild_project_context_action.setEnabled(False)
        self.rag_stats_action.setEnabled(self.rag_system is not None)
        self.clear_rag_action.setEnabled(self.rag_system is not None)
        self.index_action.setEnabled(self.rag_system is not None)
        self.upload_rag_action.setEnabled(self.rag_system is not None)
        self.manage_rag_action.setEnabled(self.rag_system is not None)
        self.manage_memory_action.setEnabled(False)
        self.summarize_chat_action.setEnabled(False)
        if self.runtime_services.project_error:
            self.statusBar().showMessage(
                f"Project system not initialized: "
                f"{self.runtime_services.project_error}"
            )
        elif self.runtime_services.llm_error:
            self.statusBar().showMessage(
                f"LLM client not initialized: {self.runtime_services.llm_error}"
            )
        elif self.runtime_services.rag_error:
            self.statusBar().showMessage(
                f"RAG system not initialized: {self.runtime_services.rag_error}"
            )
        else:
            self.statusBar().showMessage("SammyAI services initialized", 3000)

        # Connect LLM signals
        self.llm_response_received.connect(self._handle_llm_response)
        self.llm_error_occurred.connect(self._handle_llm_error)
        self.dbe_diff_ready.connect(self._show_dbe_diff)
        self.context_sync_finished.connect(self._on_context_sync_finished)
        self.agent_run_completed.connect(self._handle_agent_run_result)
        self.agent_progress.connect(self._handle_agent_progress)
        self.memory_summary_ready.connect(self._review_memory_summary)
        self.memory_summary_failed.connect(self._handle_memory_summary_error)

        # Chat panel (created lazily when the chat button is pressed)
        self.chat_dock: QDockWidget | None = None
        self.chat_panel: ChatPanel | None = None

        # Track if indexing is in progress
        self._indexing_in_progress = False
        self._indexing_lock = Lock()

        # Initialize DBE state
        self.dbe_enabled = False
        self.dbe_context_lines = 20  # Number of lines before/after cursor for context
        self.diff_manager = DiffManager()

        # Status message duration constants (in milliseconds)
        self.STATUS_QUICK = 2000      # Quick feedback (2 seconds)
        self.STATUS_NORMAL = 3000     # Normal message (3 seconds)
        self.STATUS_ERROR = 5000      # Error message (5 seconds)
        self.STATUS_PERSISTENT = 0    # Persist until overwritten

        # Project explorer is a separate, collapsible dock beside the activity rail.
        self.project_dock: QDockWidget | None = None
        self.project_explorer: ProjectExplorer | None = None
        self._create_project_explorer()
        self._restore_active_project()

    def closeEvent(self, event):
        """Persist state and release runtime resources on normal shutdown."""
        try:
            self.task_runner.shutdown()
            self.runtime_services.shutdown()
        except Exception:
            logger.exception("Error while shutting down SammyAI services")
        super().closeEvent(event)


    # --- Helper Methods ---
    
    def _open_file_dialog(self, title: str, file_filter: str) -> Optional[str]:
        """Open a file selection dialog and return the selected path.
        
        Args:
            title: Dialog title
            file_filter: File type filter (Qt format)
            
        Returns:
            Selected file path or None if cancelled
        """
        path, _ = QFileDialog.getOpenFileName(self, title, "", file_filter)
        return path if path else None

    def _show_indexing_status(self, filename: str, status: str, file_size_kb: float = 0, total_chunks: int = 0):
        """Display indexing status message in statusbar.
        
        Args:
            filename: Name of the file being indexed
            status: One of 'start', 'success', 'error'
            file_size_kb: File size in KB (for 'start' status)
            total_chunks: Total chunks indexed (for 'success' status)
        """
        if status == "start":
            self.statusBar().showMessage(
                f"Indexing {filename} ({file_size_kb:.1f}KB)...", 
                self.STATUS_PERSISTENT
            )
        elif status == "success":
            self.statusBar().showMessage(
                f"✓ Indexed {filename} ({total_chunks} total chunks)", 
                self.STATUS_NORMAL
            )
        elif status == "error":
            self.statusBar().showMessage(
                f"✗ Failed to index {filename}", 
                self.STATUS_ERROR
            )

    def _chat_panel_safe(self, method_name: str, *args):
        """Safely call a chat panel method if it exists.
        
        Args:
            method_name: Name of the method to call
            *args: Arguments to pass to the method
            
        Returns:
            Method result or None if chat_panel doesn't exist
        """
        if self.chat_panel:
            try:
                method = getattr(self.chat_panel, method_name, None)
                if method and callable(method):
                    return method(*args)
            except Exception as e:
                logger.exception("Error calling chat panel method %s", method_name)
        return None

    # --- Project system ---

    def _create_project_explorer(self) -> None:
        self.project_explorer = ProjectExplorer(self)
        self.project_explorer.file_activated.connect(self._open_file_path)

        self.project_dock = QDockWidget("Project Explorer", self)
        self.project_dock.setObjectName("projectExplorerDock")
        self.project_dock.setAllowedAreas(
            Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea
        )
        self.project_dock.setFeatures(
            QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable
        )
        self.project_dock.setMinimumWidth(240)
        self.project_dock.setWidget(self.project_explorer)
        self.project_dock.visibilityChanged.connect(
            self.toggle_project_explorer_action.setChecked
        )
        self.addDockWidget(Qt.LeftDockWidgetArea, self.project_dock)
        self.project_dock.hide()

        project_actions = (
            self.new_project_action,
            self.open_project_action,
            self.toggle_project_explorer_action,
        )
        enabled = self.project_service is not None
        for action in project_actions:
            action.setEnabled(enabled)

    def _restore_active_project(self) -> None:
        if self.project_service is None:
            return
        try:
            project = self.project_service.restore_active_project()
        except ProjectError as error:
            logger.exception("Unable to restore active project")
            self.statusBar().showMessage(
                f"Unable to restore project: {error}",
                self.STATUS_ERROR,
            )
            return
        if project is not None:
            self._set_active_project(project)

    def _create_project(self) -> None:
        if self.project_service is None:
            return
        parent = QFileDialog.getExistingDirectory(
            self,
            "Choose Parent Folder for New Project",
        )
        if not parent:
            return

        name, accepted = QInputDialog.getText(
            self,
            "New Project",
            "Project name:",
        )
        name = name.strip()
        if not accepted or not name:
            return
        if name in {".", ".."} or Path(name).name != name:
            QMessageBox.warning(
                self,
                "Invalid Project Name",
                "Use a folder name without path separators.",
            )
            return

        try:
            project = self.project_service.create_project(
                Path(parent) / name,
                name=name,
            )
        except ProjectError as error:
            QMessageBox.critical(self, "Unable to Create Project", str(error))
            return
        self._set_active_project(project)

    def _open_project(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Open Project Folder",
        )
        if path:
            self._open_project_path(path)

    def _open_project_path(self, path: str | Path) -> None:
        if self.project_service is None:
            return
        try:
            project = self.project_service.open_project(path)
        except ProjectError as error:
            QMessageBox.critical(self, "Unable to Open Project", str(error))
            return
        self._set_active_project(project)

    def _open_registered_project(self, project_id: str) -> None:
        if self.project_service is None:
            return
        try:
            project = self.project_service.open_registered_project(project_id)
        except ProjectError as error:
            QMessageBox.critical(self, "Unable to Open Project", str(error))
            self._populate_recent_projects_menu()
            return
        self._set_active_project(project)

    def _set_active_project(self, project: Project) -> None:
        if self.project_explorer is not None:
            self.project_explorer.set_project(project)
        if self.project_dock is not None:
            self.project_dock.show()
            self.project_dock.raise_()
        self.close_project_action.setEnabled(True)
        self.rebuild_project_context_action.setEnabled(
            self.context_engine is not None and self.rag_system is not None
        )
        self.manage_memory_action.setEnabled(self.memory_service is not None)
        self.summarize_chat_action.setEnabled(
            self.memory_service is not None and self.llm_client is not None
        )
        self.update_window_title()
        self.statusBar().showMessage(
            f"Opened project: {project.name}",
            self.STATUS_NORMAL,
        )
        self._schedule_project_context_sync(project)

    def _schedule_project_context_sync(
        self,
        project: Project,
        *,
        force_reindex: bool = False,
    ) -> None:
        if self.context_engine is None:
            return

        def sync_worker() -> None:
            report = self.context_engine.sync_project(
                project,
                force_reindex=force_reindex,
            )
            logger.info(
                "Project context synchronized for %s: "
                "%s added, %s updated, %s removed, %s unchanged, %s failed",
                project.id,
                report.added,
                report.updated,
                report.removed,
                report.unchanged,
                report.failed,
            )
            self.context_sync_finished.emit(
                project.id,
                report,
                force_reindex,
            )

        self.task_runner.submit(
            sync_worker,
            name=f"context-sync-{project.id}",
        )

    @Slot(str, object, bool)
    def _on_context_sync_finished(
        self,
        project_id: str,
        report,
        forced: bool,
    ) -> None:
        project = (
            self.project_service.active_project
            if self.project_service is not None
            else None
        )
        if project is None or project.id != project_id:
            return
        if forced:
            self.rebuild_project_context_action.setEnabled(True)
            self.statusBar().showMessage(
                "Project context rebuilt: "
                f"{report.added + report.updated} indexed, "
                f"{report.failed} failed",
                self.STATUS_ERROR if report.failed else self.STATUS_NORMAL,
            )
        elif report.failed:
            self.statusBar().showMessage(
                f"Project context synchronization failed for "
                f"{report.failed} file(s)",
                self.STATUS_ERROR,
            )

    def _close_project(self) -> None:
        if self.project_service is None:
            return
        self.project_service.close_project()
        if self.project_explorer is not None:
            self.project_explorer.clear_project()
        if self.project_dock is not None:
            self.project_dock.hide()
        self.close_project_action.setEnabled(False)
        self.rebuild_project_context_action.setEnabled(False)
        self.manage_memory_action.setEnabled(False)
        self.summarize_chat_action.setEnabled(False)
        self.update_window_title()
        self.statusBar().showMessage("Project closed", self.STATUS_NORMAL)

    def _toggle_project_explorer(self, visible: bool) -> None:
        if self.project_dock is None:
            return
        self.project_dock.setVisible(visible)

    def _populate_recent_projects_menu(self) -> None:
        menu = getattr(self, "recent_projects_menu", None)
        if menu is None:
            return
        menu.clear()
        if self.project_service is None:
            unavailable = menu.addAction("Project system unavailable")
            unavailable.setEnabled(False)
            return

        projects = self.project_service.recent_projects(limit=10)
        if not projects:
            empty = menu.addAction("No recent projects")
            empty.setEnabled(False)
            return

        for project in projects:
            exists = project.root_path.is_dir()
            label = project.name if exists else f"{project.name} (missing)"
            action = menu.addAction(label)
            action.setToolTip(str(project.root_path))
            action.setEnabled(exists)
            if exists:
                action.triggered.connect(
                    lambda _checked=False, project_id=project.id: (
                        self._open_registered_project(project_id)
                    )
                )

    def create_actions(self):
        # Project actions
        self.new_project_action = QAction("New Project...", self)
        self.new_project_action.setShortcut(QKeySequence("Ctrl+Shift+N"))
        self.new_project_action.setStatusTip(
            "Create and open a new SammyAI writing project"
        )
        self.new_project_action.triggered.connect(self._create_project)

        self.open_project_action = QAction("Open Project...", self)
        self.open_project_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self.open_project_action.setStatusTip(
            "Open a folder as a SammyAI writing project"
        )
        self.open_project_action.triggered.connect(self._open_project)

        self.close_project_action = QAction("Close Project", self)
        self.close_project_action.setStatusTip(
            "Close the active project without closing the current document"
        )
        self.close_project_action.triggered.connect(self._close_project)
        self.close_project_action.setEnabled(False)

        self.toggle_project_explorer_action = QAction("Project Explorer", self)
        self.toggle_project_explorer_action.setShortcut(
            QKeySequence("Ctrl+Shift+E")
        )
        self.toggle_project_explorer_action.setCheckable(True)
        self.toggle_project_explorer_action.setStatusTip(
            "Show or hide the project explorer"
        )
        self.toggle_project_explorer_action.triggered.connect(
            self._toggle_project_explorer
        )

        # New File
        self.new_action = QAction("New", self)
        self.new_action.setShortcut(QKeySequence.New)  # Ctrl+N
        self.new_action.triggered.connect(self.new_file)
        self.new_action.setStatusTip("Create a new document")
        self.new_action.setToolTip("New (Ctrl+N)")

        # Open File
        self.open_action = QAction("Open...", self)
        self.open_action.setShortcut(QKeySequence.Open)  # Ctrl+O
        self.open_action.triggered.connect(self.open_file)
        self.open_action.setStatusTip("Open an existing file")
        self.open_action.setToolTip("Open (Ctrl+O)")

        # Save File
        self.save_action = QAction("Save", self)
        self.save_action.setShortcut(QKeySequence.Save)  # Ctrl+S
        self.save_action.triggered.connect(self.save_file)
        self.save_action.setStatusTip("Save the current document")
        self.save_action.setToolTip("Save (Ctrl+S)")

        # Save As
        self.save_as_action = QAction("Save As...", self)
        self.save_as_action.setShortcut(QKeySequence.SaveAs)  # Ctrl+Shift+S
        self.save_as_action.triggered.connect(self.save_file_as)
        self.save_as_action.setStatusTip("Save the current document under a new name")
        self.save_as_action.setToolTip("Save As (Ctrl+Shift+S)")

        # Close File
        self.close_action = QAction("Close", self)
        self.close_action.setShortcut(QKeySequence.Close)  # Ctrl+W
        self.close_action.triggered.connect(self.close_file)
        self.close_action.setStatusTip("Close the current document")
        self.close_action.setToolTip("Close (Ctrl+W)")

        # Search
        self.search_action = QAction("Search", self)
        self.search_action.setShortcut(QKeySequence("Ctrl+F"))
        self.search_action.triggered.connect(self._on_search)
        self.search_action.setStatusTip("Find text in the document")
        self.search_action.setToolTip("Search (Ctrl+F)")
        
        # Replace
        self.replace_action = QAction("Replace", self)
        self.replace_action.setShortcut(QKeySequence("Ctrl+H"))
        self.replace_action.triggered.connect(self._on_replace)
        self.replace_action.setStatusTip("Find and replace text in the document")
        self.replace_action.setToolTip("Replace (Ctrl+H)")


        # --- Edit actions ---
        self.copy_action = QAction("Copy", self)
        self.copy_action.setShortcut(QKeySequence.Copy)  # Ctrl+C
        self.copy_action.triggered.connect(self._on_copy)

        self.paste_action = QAction("Paste", self)
        self.paste_action.setShortcut(QKeySequence.Paste)  # Ctrl+V
        self.paste_action.triggered.connect(self._on_paste)

        self.cut_action = QAction("Cut", self)
        self.cut_action.setShortcut(QKeySequence.Cut)  # Ctrl+X
        self.cut_action.triggered.connect(self._on_cut)

        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence.Undo)  # Ctrl+Z
        self.undo_action.triggered.connect(self._on_undo)

        # Redo
        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcut(QKeySequence("Ctrl+Y"))
        self.redo_action.triggered.connect(self._on_redo)

        # Repeat: Shift+Ctrl+Y
        self.repeat_action = QAction("Repeat", self)
        self.repeat_action.setShortcut(QKeySequence("Ctrl+Shift+Y"))  # Shift+Ctrl+Y
        self.repeat_action.triggered.connect(self._on_repeat)

        # Chat and settings actions
        self.agent_action = QAction("Chat", self)
        self.agent_action.setEnabled(True)
        self.agent_action.setToolTip("Open Sammy AI chat panel")
        self.agent_action.triggered.connect(self._toggle_chat_panel)

        self.llm_setup_action = QAction("LLM Setup", self)
        self.llm_setup_action.setToolTip("Configure LLM Models & Keys")
        self.llm_setup_action.triggered.connect(self._on_configure_llm_setup)


        self.settings_action = QAction("Settings", self)
        self.settings_action.setEnabled(True)
        self.settings_action.triggered.connect(self._on_show_llm_settings)

        # Initial enable/disable states
        self.copy_action.setEnabled(False)
        self.cut_action.setEnabled(False)
        # Undo/redo availability will be driven by document signals
        self.undo_action.setEnabled(False)
        self.redo_action.setEnabled(False)

        # Legacy manual indexing remains available under Advanced.
        self.index_action = QAction("Index Current File Manually...", self)
        self.index_action.triggered.connect(self._index_current_file_manually)
        self.index_action.setStatusTip(
            "Legacy fallback: manually index the current file"
        )

        self.upload_rag_action = QAction("Add External File to Index...", self)
        self.upload_rag_action.triggered.connect(self._upload_file_for_rag)
        self.upload_rag_action.setStatusTip(
            "Legacy fallback: persistently index a file outside the project"
        )

        self.rebuild_project_context_action = QAction(
            "Rebuild Active Project Index...",
            self,
        )
        self.rebuild_project_context_action.triggered.connect(
            self._rebuild_active_project_context
        )
        self.rebuild_project_context_action.setStatusTip(
            "Regenerate context embeddings for every supported project file"
        )

        # Advanced index management actions
        self.manage_rag_action = QAction("Legacy Index Manager...", self)
        self.manage_rag_action.triggered.connect(self._manage_rag_index)
        
        self.clear_rag_action = QAction("Reset Entire Context Index...", self)
        self.clear_rag_action.triggered.connect(self._clear_rag_index)
        
        self.rag_stats_action = QAction("Context Index Statistics...", self)
        self.rag_stats_action.triggered.connect(self._show_rag_stats)

        self.manage_memory_action = QAction("Manage Project Memory...", self)
        self.manage_memory_action.triggered.connect(
            self._manage_project_memory
        )
        self.manage_memory_action.setStatusTip(
            "Review structured memories, provenance, and summaries"
        )

        self.summarize_chat_action = QAction(
            "Summarize Current Chat...",
            self,
        )
        self.summarize_chat_action.triggered.connect(
            self._summarize_current_chat
        )
        self.summarize_chat_action.setStatusTip(
            "Create a reviewable persistent-memory draft from this chat"
        )

        # Temporary references remain explicit but use user-facing terminology.
        self.upload_cin_action = QAction("Attach Reference...", self)
        self.upload_cin_action.triggered.connect(self._upload_cin_file)
        self.upload_cin_action.setStatusTip(
            "Attach a small external reference to the current conversation"
        )

        self.clear_cin_action = QAction("Remove Attached Reference", self)
        self.clear_cin_action.triggered.connect(self._clear_cin_context)
        self.clear_cin_action.setStatusTip(
            "Remove the temporary reference from this conversation"
        )
        self.clear_cin_action.setEnabled(False)

        # DBE (Diff-Based Editing) actions
        self.compare_file_action = QAction("Compare with File...", self)
        self.compare_file_action.setShortcut(QKeySequence("Ctrl+D"))
        self.compare_file_action.triggered.connect(self._compare_with_file)
        self.compare_file_action.setStatusTip("Compare current text with another file using diff")

        self.compare_clipboard_action = QAction("Compare with Clipboard", self)
        self.compare_clipboard_action.setShortcut(QKeySequence("Ctrl+Shift+D"))
        self.compare_clipboard_action.triggered.connect(self._compare_with_clipboard)
        self.compare_clipboard_action.setStatusTip("Compare current text with clipboard content using diff")

        self.apply_diff_action = QAction("Apply Diff from File...", self)
        self.apply_diff_action.triggered.connect(self._apply_diff_from_file)
        self.apply_diff_action.setStatusTip("Apply a diff file to current text")

        self.undo_change_set_action = QAction(
            "Undo Last Applied Change Set",
            self,
        )
        self.undo_change_set_action.triggered.connect(
            self._undo_last_change_set
        )
        self.undo_change_set_action.setEnabled(False)

        self.redo_change_set_action = QAction(
            "Redo Last Applied Change Set",
            self,
        )
        self.redo_change_set_action.triggered.connect(
            self._redo_last_change_set
        )
        self.redo_change_set_action.setEnabled(False)

        # Legacy DBE activation is retained only as an advanced fallback.
        self.toggle_dbe_action = QAction("Enable Legacy DBE Mode", self)
        self.toggle_dbe_action.setCheckable(True)
        self.toggle_dbe_action.triggered.connect(self._toggle_dbe_mode)
        self.toggle_dbe_action.setStatusTip(
            "Legacy fallback: send chat replies through the original DBE workflow"
        )

    def _load_icon(self, theme_name, fallback):
        icon = QIcon.fromTheme(theme_name)
        if not icon or icon.isNull():
            return QApplication.style().standardIcon(fallback)
        return icon

    def _load_colored_svg_icon(self, base_name, color=None, size=32):
        """Load an SVG from the local `icons/` folder and tint it to `color`.

        Falls back to themed/fallback icon if the SVG file is not available or fails to render.
        """
        if color is None:
            # Try to derive the icon color from the QToolButton style in the stylesheet
            color = _extract_color_from_stylesheet("QToolButton", "color")
            
            # Fallback to editor text color if not found in QToolButton
            if color is None:
                try:
                    color = self.editor._get_editor_text_color().name()
                except Exception:
                    color = "#ffffff"

        try:
            svg_path = str(asset_path("icons", f"{base_name}.svg"))

            if os.path.exists(svg_path):
                renderer = QSvgRenderer(svg_path)
                pix = QPixmap(size, size)
                pix.fill(Qt.transparent)

                painter = QPainter(pix)
                # Render the SVG scaled to the pixmap
                renderer.render(painter, QRect(0, 0, size, size))

                # Tint the rendered pixmap by using SourceIn composition
                painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
                painter.fillRect(pix.rect(), QColor(color))
                painter.end()

                return QIcon(pix)
        except Exception:
            # Fall through to fallback
            pass

        # Fallback to theme/fallback icon if something goes wrong
        return self._load_icon(base_name, QStyle.SP_FileIcon)

    def create_toolbar(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        # Make toolbar vertical and dock it to the left area
        toolbar.setOrientation(Qt.Vertical)
        toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(Qt.LeftToolBarArea, toolbar)
        # Add quick toolbar actions: New, Open, Save, Close in this order
        # Set icons if available
        # Prefer local SVG icons (tinted to match the editor text color) if available
        self.new_action.setIcon(self._load_colored_svg_icon("new"))
        self.open_action.setIcon(self._load_colored_svg_icon("open"))
        self.save_action.setIcon(self._load_colored_svg_icon("save"))
        self.close_action.setIcon(self._load_colored_svg_icon("close"))

        toolbar.addAction(self.new_action)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_action)
        toolbar.addAction(self.close_action)
        # Add Search icon below Close (use local svg if present)
        self.search_action.setIcon(self._load_colored_svg_icon("search"))
        toolbar.addAction(self.search_action)

        # Add a stretch spacer to push the next items to the bottom of the vertical toolbar
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        toolbar.addWidget(spacer)

        # Bottom-only icons
        self.agent_action.setIcon(self._load_colored_svg_icon("chat"))
        self.llm_setup_action.setIcon(self._load_colored_svg_icon("llm_setup"))
        self.settings_action.setIcon(self._load_colored_svg_icon("settings"))

        toolbar.addAction(self.agent_action)
        toolbar.addAction(self.llm_setup_action)
        toolbar.addAction(self.settings_action)


        # Connect editor signals to enable/disable actions based on context
        # copyAvailable(bool) is emitted when a selection is present
        self.editor.copyAvailable.connect(self.copy_action.setEnabled)
        self.editor.copyAvailable.connect(self.cut_action.setEnabled)

        # Document signals for undo/redo availability
        doc = self.editor.document()
        try:
            doc.undoAvailable.connect(self.undo_action.setEnabled)
            doc.redoAvailable.connect(self.redo_action.setEnabled)
        except Exception:
            # In case the API differs, fallback to checking availability manually
            pass

        # Keep the UI in sync at startup
        self.copy_action.setEnabled(bool(self.editor.textCursor().hasSelection()))
        self.cut_action.setEnabled(bool(self.editor.textCursor().hasSelection()))
        self.undo_action.setEnabled(doc.isUndoAvailable())
        self.redo_action.setEnabled(doc.isRedoAvailable())

    def create_menubar(self):
        """Create a proper menubar with File and Edit menus."""
        menubar = self.menuBar()
        # File menu
        file_menu = menubar.addMenu("File")
        file_menu.addAction(self.new_project_action)
        file_menu.addAction(self.open_project_action)
        self.recent_projects_menu = file_menu.addMenu("Open Recent Project")
        self.recent_projects_menu.aboutToShow.connect(
            self._populate_recent_projects_menu
        )
        file_menu.addAction(self.close_project_action)
        file_menu.addSeparator()
        file_menu.addAction(self.new_action)
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.save_action)
        # add Save As with an icon if available
        self.save_as_action.setIcon(self._load_icon("document-save-as", QStyle.SP_DialogSaveButton))
        file_menu.addAction(self.save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(self.close_action)

        # Edit menu
        edit_menu = menubar.addMenu("Edit")
        # add icons to edit menu actions
        self.copy_action.setIcon(self._load_icon("edit-copy", QStyle.SP_DialogOpenButton))
        self.cut_action.setIcon(self._load_icon("edit-cut", QStyle.SP_DialogOpenButton))
        self.paste_action.setIcon(self._load_icon("edit-paste", QStyle.SP_DialogOpenButton))
        self.undo_action.setIcon(self._load_icon("edit-undo", QStyle.SP_ArrowBack))
        self.redo_action.setIcon(self._load_icon("edit-redo", QStyle.SP_ArrowForward))
        self.repeat_action.setIcon(self._load_icon("view-refresh", QStyle.SP_BrowserReload))
        edit_menu.addAction(self.copy_action)
        edit_menu.addAction(self.paste_action)
        edit_menu.addAction(self.cut_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.repeat_action)
        edit_menu.addSeparator()
        # Add search and replace actions
        self.search_action.setIcon(self._load_icon("edit-find", QStyle.SP_FileDialogContentsView))
        self.replace_action.setIcon(self._load_icon("edit-find-replace", QStyle.SP_FileDialogContentsView))
        edit_menu.addAction(self.search_action)
        edit_menu.addAction(self.replace_action)
        edit_menu.addSeparator()
        self.compare_menu = edit_menu.addMenu("Compare and Review")
        self.compare_menu.addAction(self.compare_file_action)
        self.compare_menu.addAction(self.compare_clipboard_action)
        self.compare_menu.addSeparator()
        self.compare_menu.addAction(self.apply_diff_action)
        self.compare_menu.addSeparator()
        self.compare_menu.addAction(self.undo_change_set_action)
        self.compare_menu.addAction(self.redo_change_set_action)

        view_menu = menubar.addMenu("View")
        view_menu.addAction(self.toggle_project_explorer_action)

        self.advanced_menu = menubar.addMenu("Advanced")
        self.persistent_memory_menu = self.advanced_menu.addMenu(
            "Persistent Memory"
        )
        self.persistent_memory_menu.addAction(self.manage_memory_action)
        self.persistent_memory_menu.addAction(self.summarize_chat_action)

        self.project_context_menu = self.advanced_menu.addMenu(
            "Project Context"
        )
        self.project_context_menu.addAction(
            self.rebuild_project_context_action
        )
        self.project_context_menu.addAction(self.rag_stats_action)
        self.project_context_menu.addAction(self.clear_rag_action)

        self.legacy_rag_menu = self.advanced_menu.addMenu(
            "Legacy Manual Indexing"
        )
        self.legacy_rag_menu.addAction(self.index_action)
        self.legacy_rag_menu.addAction(self.upload_rag_action)
        self.legacy_rag_menu.addAction(self.manage_rag_action)

        self.advanced_menu.addSeparator()
        self.advanced_menu.addAction(self.toggle_dbe_action)

    def create_statusbar(self):
        """Create status bar with line/column and word count indicators."""
        sb = self.statusBar()
        # Left part can show messages; we add two permanent widgets to the right
        self._status_word = QLabel("Words: 0")
        self._status_pos = QLabel("Ln 1, Col 1")
        # Slight padding
        self._status_word.setMargin(4)
        self._status_pos.setMargin(8)
        # Use editor text color for status labels so they are visible in dark theme
        try:
            status_color = self.editor._get_editor_text_color().name()
        except Exception:
            status_color = "#ffffff"
        self._status_word.setStyleSheet(f"color: {status_color};")
        self._status_pos.setStyleSheet(f"color: {status_color};")
        sb.addPermanentWidget(self._status_word)
        sb.addPermanentWidget(self._status_pos)

        # Connect editor signals to update status
        self.editor.cursorPositionChanged.connect(self._update_cursor_position)
        self.editor.textChanged.connect(self._update_word_count)

        # Initialize values
        self._update_cursor_position()
        self._update_word_count()

    def _update_cursor_position(self):
        cursor = self.editor.textCursor()
        # blockNumber() is zero-based
        ln = cursor.blockNumber() + 1
        col = cursor.positionInBlock() + 1
        self._status_pos.setText(f"Ln {ln}, Col {col}")

    def _update_word_count(self):
        text = self.editor.toPlainText()
        # count words using word boundaries
        words = re.findall(r"\b\w+\b", text)
        self._status_word.setText(f"Words: {len(words)}")

    def _on_search(self):
        """Show the search widget in find-only mode and focus the input field."""
        self.search_widget.show_replace_controls(False)
        self.search_widget.show()
        self.search_widget.focus_input()
    
    def _on_replace(self):
        """Show the search widget in find-and-replace mode and focus the input field."""
        self.search_widget.show_replace_controls(True)
        self.search_widget.show()
        self.search_widget.focus_input()
    
    def _on_search_text_changed(self, text):
        """Called when search text changes - find and highlight all matches."""
        if not text:
            self._clear_search_highlights()
            self.search_widget.update_match_count(0, 0)
            return
        
        # Find all matches
        self.current_matches = self._find_all_matches(text)
        
        if self.current_matches:
            self.current_match_index = 0
            self._highlight_all_matches()
            self._navigate_to_match(0)
            self.search_widget.update_match_count(1, len(self.current_matches))
        else:
            self._clear_search_highlights()
            self.search_widget.update_match_count(0, 0)
    
    def _find_all_matches(self, text):
        """Find all occurrences of text in the document and return their cursor positions."""
        matches = []
        document = self.editor.document()
        cursor = QTextCursor(document)
        
        # Find all matches
        while True:
            cursor = document.find(text, cursor)
            if cursor.isNull():
                break
            matches.append(cursor)
        
        return matches
    
    def _highlight_all_matches(self):
        """Highlight all matches with different colors for current vs other matches."""
        if not self.current_matches:
            return
        
        extra_selections = []
        
        # Highlight all matches
        for i, cursor in enumerate(self.current_matches):
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            
            # Current match gets a different color (orange) than other matches (yellow)
            if i == self.current_match_index:
                selection.format.setBackground(QColor("#FF8C00"))  # Dark orange for current match
            else:
                selection.format.setBackground(QColor("#FFD700"))  # Gold for other matches
            
            extra_selections.append(selection)
        
        self.editor.setExtraSelections(extra_selections)
    
    def _navigate_to_match(self, index):
        """Navigate to and select a specific match."""
        if not self.current_matches or index < 0 or index >= len(self.current_matches):
            return
        
        self.current_match_index = index
        cursor = self.current_matches[index]
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()
        
        # Update highlighting to show new current match
        self._highlight_all_matches()
        
        # Update match counter
        self.search_widget.update_match_count(index + 1, len(self.current_matches))
    
    def _next_match(self):
        """Navigate to the next match."""
        if not self.current_matches:
            return
        
        next_index = (self.current_match_index + 1) % len(self.current_matches)
        self._navigate_to_match(next_index)
    
    def _previous_match(self):
        """Navigate to the previous match."""
        if not self.current_matches:
            return
        
        prev_index = (self.current_match_index - 1) % len(self.current_matches)
        self._navigate_to_match(prev_index)
    
    def _replace_current(self):
        """Replace the current match and move to the next one."""
        if not self.current_matches or self.current_match_index >= len(self.current_matches):
            return
        
        search_text = self.search_widget.get_search_text()
        replace_text = self.search_widget.get_replace_text()
        
        if not search_text:
            return
        
        # Get the current match cursor
        cursor = self.current_matches[self.current_match_index]
        
        # Replace the text
        cursor.insertText(replace_text)
        
        # Refresh the matches list after replacement
        self.current_matches = self._find_all_matches(search_text)
        
        if self.current_matches:
            # Stay at the same index (which is now the next match)
            if self.current_match_index >= len(self.current_matches):
                self.current_match_index = 0
            self._navigate_to_match(self.current_match_index)
        else:
            # No more matches
            self._clear_search_highlights()
            self.search_widget.update_match_count(0, 0)
    
    def _replace_all(self):
        """Replace all matches at once."""
        if not self.current_matches:
            return
        
        search_text = self.search_widget.get_search_text()
        replace_text = self.search_widget.get_replace_text()
        
        if not search_text:
            return
        
        # Count matches before replacing
        count = len(self.current_matches)
        
        # Replace all matches from last to first to maintain cursor positions
        for cursor in reversed(self.current_matches):
            cursor.insertText(replace_text)
        
        # Clear matches and highlights
        self.current_matches = []
        self.current_match_index = 0
        self._clear_search_highlights()
        self.search_widget.update_match_count(0, 0)
        
        # Show status message
        self.statusBar().showMessage(f"Replaced {count} occurrence(s)", 3000)
    
    def _close_search(self):
        """Close the search widget and clear highlights."""
        self.search_widget.hide()
        self._clear_search_highlights()
        self.current_matches = []
        self.current_match_index = 0
        self.editor.setFocus()
    
    def _clear_search_highlights(self):
        """Clear all search highlights from the editor."""
        self.editor.setExtraSelections([])
    
    def eventFilter(self, obj, event):
        """Handle keyboard events in the search widget."""
        if obj == self.search_widget.search_input and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key_Escape:
                self._close_search()
                return True
            elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                if event.modifiers() & Qt.ShiftModifier:
                    self._previous_match()
                else:
                    self._next_match()
                return True
        
        return super().eventFilter(obj, event)


    # --- Chat panel integration ---
    def _toggle_chat_panel(self):
        """Show or hide the chat panel dock."""
        if self.chat_dock and not self.chat_dock.isHidden():
            self.chat_dock.hide()
            return

        if not self.chat_dock:
            self._create_chat_panel()

        if self.chat_dock:
            self.chat_dock.show()
            self.chat_panel.setFocus()

    def _create_chat_panel(self):
        """Create the chat panel and dock widget and wire up messaging."""
        try:
            self.chat_panel = ChatPanel(self)
            self.chat_panel.close_button.clicked.connect(lambda: self.chat_dock.hide() if self.chat_dock else None)
            # When a message is sent from the UI, handle it
            self.chat_panel.message_sent.connect(self._on_chat_message_sent)
            # When the model selection changes in the UI, attempt to switch clients
            self.chat_panel.model_selected.connect(self._on_model_selected)
            self.chat_panel.agent_selected.connect(self._on_agent_selected)
            # When clear chat is requested, clear the session
            self.chat_panel.clear_chat_requested.connect(self._on_clear_chat_requested)

            # The primary chat only exposes temporary reference attachment.
            self._setup_chat_panel_menus()

            self.chat_dock = QDockWidget(self)
            self.chat_dock.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
            self.chat_dock.setWidget(self.chat_panel)
            self.addDockWidget(Qt.RightDockWidgetArea, self.chat_dock)
            # Set the combo to the currently configured model
            try:
                current_model = self.llm_config.model_key if hasattr(self, "llm_config") else None
                if current_model and hasattr(self.chat_panel, "model_combo"):
                    idx = self.chat_panel.model_combo.findText(current_model)
                    if idx >= 0:
                        self.chat_panel.model_combo.setCurrentIndex(idx)
                agent_idx = self.chat_panel.agent_combo.findData(
                    self.active_agent_type.value
                )
                if agent_idx >= 0:
                    self.chat_panel.agent_combo.setCurrentIndex(agent_idx)
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self, "Chat Panel Error", str(e))

    def _setup_chat_panel_menus(self):
        """Configure the primary chat's temporary-reference menu."""
        if not self.chat_panel:
            return

        reference_menu = QMenu(self.chat_panel.attach_button)
        reference_menu.addAction(self.upload_cin_action)
        reference_menu.addAction(self.clear_cin_action)
        self.chat_panel.attach_button.setMenu(reference_menu)

    def _on_chat_message_sent(self, message: str):
        """Handle message sent from chat panel UI: store in session and query LLM in background."""
        if not message:
            return

        # Immediately show user message in UI FIRST
        if self.chat_panel:
            self.chat_panel.add_user_message(message)
            self.chat_panel.set_thinking(True)

        # Then add user message to session
        try:
            self.chat_manager.add_message(
                MessageRole.USER,
                message,
                metadata={"agent_type": self.active_agent_type.value},
            )
        except Exception as e:
            logger.exception("Failed to add user message to session")

        # If LLM not available, inform the user
        if not self.llm_client:
            self._chat_panel_safe("set_thinking", False)
            self._chat_panel_safe("add_system_message", "LLM client not initialized. Configure API key or check environment.")
            return

        # Check if DBE mode is enabled
        if self.dbe_enabled:
            # DBE mode: inject editor context and show diff
            self._handle_dbe_request(message)
        else:
            # Agent workflows own normal chat behavior.
            self._handle_normal_chat(message)

    def _on_clear_chat_requested(self):
        """Handle clear chat request: clear session history."""
        try:
            if self.chat_manager:
                self.chat_manager.clear_session()
                # Optionally verify/log
                if self.chat_panel:
                    self.chat_panel.set_status("Chat session reset (context cleared)")
        except Exception as e:
            logger.exception("Error clearing chat session")
    
    def _handle_normal_chat(self, message: str):
        """Run the selected agent workflow outside the UI thread."""
        selected_agent = self.active_agent_type
        client = self.llm_client

        def worker():
            try:
                if self.chat_manager:
                    msgs = self.chat_manager.get_messages_for_llm_with_context(
                        query=message,
                        top_k=3,
                    )
                else:
                    msgs = [{"role": "user", "content": message}]

                def complete(
                    completion_messages: list[dict[str, str]],
                    system_prompt: str,
                ) -> str:
                    with self._llm_lock:
                        original_prompt = client.system_prompt
                        try:
                            client.system_prompt = system_prompt
                            return client.chat(completion_messages)
                        finally:
                            client.system_prompt = original_prompt

                result = self.agent_workflows.run(
                    selected_agent,
                    user_request=message,
                    messages=msgs,
                    complete=complete,
                    authorized_files=(
                        getattr(
                            self.chat_manager.last_context_result,
                            "complete_referenced_files",
                            (),
                        )
                        if self.chat_manager.last_context_result is not None
                        else ()
                    ),
                    on_event=lambda event: self.agent_progress.emit(
                        event.message
                    ),
                )

                self.chat_manager.add_message(
                    MessageRole.ASSISTANT,
                    result.response,
                    metadata={
                        "agent_type": result.agent_type.value,
                        "agent_run_id": result.run_id,
                        "model_calls": result.model_calls,
                    },
                )
                self.agent_run_completed.emit(result)
            except Exception as e:
                self.llm_error_occurred.emit(str(e))

        self.task_runner.submit(
            worker,
            name=f"agent-{selected_agent.value}",
        )
    
    def _handle_dbe_request(self, message: str):
        """Handle DBE mode request with editor context."""
        # Get editor context
        text, cursor_line, selection_start, selection_end = self._get_editor_context_for_dbe()
        
        if not text:
            self._chat_panel_safe("set_thinking", False)
            self._chat_panel_safe("add_system_message", "⚠️ Editor is empty. Please add some text before using DBE mode.")
            return
        
        # Store original text for diff
        original_text = text
        original_lines = text.splitlines()
        
        # Prepare editor context - now returns tuple with line range info
        context_result = self.chat_manager.prepare_dbe_context(
            file_path=self.current_file,
            text=text,
            cursor_line=cursor_line,
            selection_start=selection_start,
            selection_end=selection_end,
            context_lines=self.dbe_context_lines
        )
        
        # Unpack the tuple with focus lines: (context_string, start_line, end_line, original_section_text, focus_start, focus_end)
        editor_context, dbe_start_line, dbe_end_line, original_section, focus_start, focus_end = context_result
        
        # Run LLM query in background thread
        def worker():
            try:
                # Get messages with DBE context
                from llm.dbe_system_prompt import get_dbe_system_prompt
                
                # Get messages with editor context
                msgs = self.chat_manager.get_messages_for_llm_with_dbe_context(
                    query=message,
                    editor_context=editor_context
                )

                # Serialize access while the legacy client prompt is overridden.
                with self._llm_lock:
                    original_prompt = self.llm_client.system_prompt
                    try:
                        self.llm_client.system_prompt = get_dbe_system_prompt()
                        reply = self.llm_client.chat(msgs)
                    finally:
                        self.llm_client.system_prompt = original_prompt
                
                # Extract revised section from LLM response
                revised_section = self._extract_text_from_llm_response(reply)
                
                # Reconstruct the full document by splicing revised section
                # into the original at the correct position
                revised_section_lines = revised_section.splitlines()
                
                # Build the reconstructed full document:
                # - Lines before the DBE section (1 to start_line-1)
                # - The revised section from LLM
                # - Lines after the DBE section (end_line+1 to end)
                reconstructed_lines = []
                
                # Add lines before DBE section
                # Add lines before FOCUS section
                if focus_start > 1:
                    reconstructed_lines.extend(original_lines[:focus_start - 1])
                
                # Add revised section
                reconstructed_lines.extend(revised_section_lines)
                
                # Add lines after FOCUS section
                if focus_end < len(original_lines):
                    reconstructed_lines.extend(original_lines[focus_end:])
                
                reconstructed_text = "\n".join(reconstructed_lines)
                
                # Add assistant message to session
                try:
                    self.chat_manager.add_message(MessageRole.ASSISTANT, reply)
                except Exception:
                    pass
                
                # Emit signal to show diff on main thread
                # Now comparing full original vs full reconstructed document
                self.dbe_diff_ready.emit(original_text, reconstructed_text, message)
                
            except Exception as e:
                self.llm_error_occurred.emit(str(e))
        
        self.task_runner.submit(worker, name="dbe")
    
    @Slot(str, str, str)
    def _show_dbe_diff(self, original: str, modified: str, user_request: str):
        """Show DBE diff in viewer (called on main thread)."""
        self._chat_panel_safe("set_thinking", False)
        
        # Create diff dialog
        dialog = self._create_diff_dialog()
        dialog.setWindowTitle(
            f"Legacy DBE Suggestion - {user_request[:50]}..."
        )
        
        # Load diff
        dialog.diff_viewer.load_diff(
            original, modified,
            "current", "llm_suggestion"
        )
        
        # Show dialog
        if dialog.exec() == QDialog.Accepted:
            # User approved - apply changes
            modified_text = dialog.diff_viewer.get_modified_text()
            if self._apply_reviewed_editor_change(original, modified_text):
                self._chat_panel_safe("add_system_message", "✓ Changes applied successfully!")
                self.statusBar().showMessage("✓ DBE changes applied", self.STATUS_NORMAL)
        else:
            # User rejected
            self._chat_panel_safe("add_system_message", "✗ Changes rejected")
            self.statusBar().showMessage("✗ DBE changes rejected", self.STATUS_NORMAL)

    
    @Slot(str)
    def _handle_llm_response(self, reply: str):
        """Handle successful LLM response on main thread."""
        self._chat_panel_safe("set_thinking", False)
        self._chat_panel_safe("add_assistant_message", reply)

    @Slot(object)
    def _handle_agent_run_result(self, result: AgentRunResult) -> None:
        """Render one agent result and review any proposed file changes."""
        self._chat_panel_safe("set_thinking", False)
        self._chat_panel_safe("add_assistant_message", result.response)
        self._chat_panel_safe(
            "set_status",
            f"{result.agent_type.display_name} completed "
            f"({result.model_calls} model call"
            f"{'s' if result.model_calls != 1 else ''})",
        )
        for notice in result.notices:
            self._chat_panel_safe("add_system_message", notice)

        if (
            result.change_set is None
            or result.change_preview is None
            or self.file_tools is None
        ):
            return

        dialog = ChangeSetReviewDialog(result.change_preview, self)
        if dialog.exec() != QDialog.Accepted:
            self._chat_panel_safe(
                "add_system_message",
                "Proposed file changes rejected; no files were modified.",
            )
            return

        if self._current_document_conflicts_with(result.change_set):
            QMessageBox.warning(
                self,
                "Unsaved Document Conflict",
                "The proposed change includes the current document, which has "
                "unsaved edits. Save or discard those edits before applying "
                "the change set.",
            )
            self._chat_panel_safe(
                "add_system_message",
                "File changes were not applied because the current document "
                "has unsaved edits.",
            )
            return

        try:
            applied = self.file_tools.apply(result.change_set)
        except FileToolError as error:
            QMessageBox.critical(self, "Change Set Conflict", str(error))
            self._chat_panel_safe(
                "add_system_message",
                f"File changes were not applied: {error}",
            )
            return

        self._update_change_set_history_actions()
        self._reload_current_file_if_changed(applied.changed_paths)
        self._sync_after_file_tool_change()
        self._chat_panel_safe(
            "add_system_message",
            f"Applied {len(applied.changed_paths)} reviewed file change(s). "
            "The change set can be undone through the file-tool history.",
        )

    @Slot(str)
    def _handle_agent_progress(self, message: str) -> None:
        self._chat_panel_safe("set_status", message)

    def _update_change_set_history_actions(self) -> None:
        tools = getattr(self, "file_tools", None)
        self.undo_change_set_action.setEnabled(
            bool(tools and tools.can_undo)
        )
        self.redo_change_set_action.setEnabled(
            bool(tools and tools.can_redo)
        )

    def _undo_last_change_set(self) -> None:
        if self.file_tools is None:
            return
        change_set = self.file_tools.next_undo_change_set
        if change_set is None:
            self._update_change_set_history_actions()
            return
        if self._current_document_conflicts_with(change_set):
            QMessageBox.warning(
                self,
                "Unsaved Document Conflict",
                "Save or discard the current document's edits before undoing "
                "this change set.",
            )
            return
        try:
            applied = self.file_tools.undo_last()
        except FileToolError as error:
            QMessageBox.critical(self, "Undo Change Set", str(error))
            return
        self._update_change_set_history_actions()
        self._reload_current_file_if_changed(applied.changed_paths)
        self._sync_after_file_tool_change()
        self.statusBar().showMessage(
            "Last applied change set undone",
            self.STATUS_NORMAL,
        )

    def _redo_last_change_set(self) -> None:
        if self.file_tools is None:
            return
        change_set = self.file_tools.next_redo_change_set
        if change_set is None:
            self._update_change_set_history_actions()
            return
        if self._current_document_conflicts_with(change_set):
            QMessageBox.warning(
                self,
                "Unsaved Document Conflict",
                "Save or discard the current document's edits before redoing "
                "this change set.",
            )
            return
        try:
            applied = self.file_tools.redo_last()
        except FileToolError as error:
            QMessageBox.critical(self, "Redo Change Set", str(error))
            return
        self._update_change_set_history_actions()
        self._reload_current_file_if_changed(applied.changed_paths)
        self._sync_after_file_tool_change()
        self.statusBar().showMessage(
            "Change set reapplied",
            self.STATUS_NORMAL,
        )

    def _sync_after_file_tool_change(self) -> None:
        project = (
            self.project_service.active_project
            if self.project_service is not None
            else None
        )
        if project is not None:
            self._schedule_project_context_sync(project)
            
    @Slot(str)
    def _handle_llm_error(self, error_msg: str):
        """Handle LLM error on main thread."""
        self._chat_panel_safe("set_thinking", False)
        self._chat_panel_safe("add_system_message", f"LLM error: {error_msg}")

    def _on_agent_selected(self, agent_value: str) -> None:
        try:
            self.active_agent_type = AgentType(agent_value)
        except ValueError:
            self.active_agent_type = AgentType.GENERAL
        self.chat_manager.set_session_metadata(
            "agent_type",
            self.active_agent_type.value,
        )
        self._chat_panel_safe(
            "set_status",
            f"Using agent: {self.active_agent_type.display_name}",
        )

    def _current_document_conflicts_with(self, change_set) -> bool:
        if not self.current_file or not self.editor.document().isModified():
            return False
        project = (
            self.project_service.active_project
            if self.project_service is not None
            else None
        )
        if project is None:
            return False
        try:
            relative_path = (
                Path(self.current_file)
                .resolve()
                .relative_to(project.root_path)
                .as_posix()
            )
        except ValueError:
            return False
        return any(
            os.path.normcase(change.relative_path)
            == os.path.normcase(relative_path)
            for change in change_set.changes
        )

    def _reload_current_file_if_changed(
        self,
        changed_paths: tuple[str, ...],
    ) -> None:
        if not self.current_file:
            return
        project = (
            self.project_service.active_project
            if self.project_service is not None
            else None
        )
        if project is None:
            return
        try:
            relative_path = (
                Path(self.current_file)
                .resolve()
                .relative_to(project.root_path)
                .as_posix()
            )
        except ValueError:
            return
        normalized_paths = {
            os.path.normcase(path)
            for path in changed_paths
        }
        if os.path.normcase(relative_path) not in normalized_paths:
            return
        current_path = Path(self.current_file)
        if current_path.exists():
            self.editor.setPlainText(
                self.document_service.read_text(current_path)
            )
            self.editor.document().setModified(False)
        else:
            self.close_file()

    def _on_model_selected(self, model_key: str):
        """Handle a model selection change from the UI.

        Attempt to update the LLM config and recreate the client. If creation
        fails (e.g., missing API key for cloud models), report back to the UI
        and keep the previous configuration.
        """
        # Store old setting in case we need to roll back
        old_model = None
        try:
            old_model = self.llm_config.model_key
        except Exception:
            old_model = None

        try:
            # Update config and create client
            self.llm_config.model_key = model_key
            new_client = self.llm_config.create_client()
            self.llm_client = new_client
            self.summarize_chat_action.setEnabled(
                self.memory_service is not None
                and self.project_service is not None
                and self.project_service.active_project is not None
            )
            self._chat_panel_safe("set_status", f"Using model: {model_key}")
            # Also show a short statusbar message
            self.statusBar().showMessage(f"Using model: {model_key}", self.STATUS_NORMAL)
        except Exception as e:
            # Rollback model_key if possible
            try:
                if old_model is not None:
                    self.llm_config.model_key = old_model
            except Exception:
                pass
            # Inform the user in the chat panel
            self._chat_panel_safe("add_system_message", f"Failed to switch model to {model_key}: {e}")
            self.statusBar().showMessage(f"Failed to switch model: {e}", self.STATUS_ERROR)



    # --- Edit action handlers (TextEditor forwards to the editor widget) ---
    def _on_copy(self):
        self.editor.copy()

    def _on_paste(self):
        self.editor.paste()

    def _on_cut(self):
        self.editor.cut()

    def _on_undo(self):
        self.editor.undo()

    def _on_redo(self):
        self.editor.redo()

    def _on_repeat(self):
        # Repeat last redo action
        self.editor.redo()

    def _apply_reviewed_editor_change(
        self,
        expected_original: str,
        modified_text: str,
    ) -> bool:
        """Apply one reviewed replacement without discarding Qt undo history."""
        if self.editor.toPlainText() != expected_original:
            QMessageBox.warning(
                self,
                "Edit Conflict",
                "The document changed while the diff was being reviewed. "
                "The proposed change was not applied.",
            )
            return False

        cursor = QTextCursor(self.editor.document())
        cursor.beginEditBlock()
        cursor.select(QTextCursor.Document)
        cursor.insertText(modified_text)
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
        return True

    def _on_show_llm_settings(self):
        """Show the LLM parameter settings dialog and update configuration."""
        if not hasattr(self, 'llm_config'):
            return
            
        dialog = LLMSettingsDialog(
            temperature=self.llm_config.temperature,
            top_p=self.llm_config.top_p,
            seed=self.llm_config.seed,
            model_name=self.llm_config.model_key,
            parent=self
        )
        
        if dialog.exec():
            temp, top_p, seed = dialog.get_values()
            
            # Update configuration
            self.llm_config.temperature = temp
            self.llm_config.top_p = top_p
            self.llm_config.seed = seed
            
            # Apply to active client if it exists
            if self.llm_client:
                self.llm_config.apply_to_client(self.llm_client)
            
            seed_msg = f", Seed={seed}" if seed is not None else ""
            self.statusBar().showMessage(f"LLM Parameters updated: Temperature={temp}, Top-P={top_p}{seed_msg}", self.STATUS_NORMAL)

    def _on_configure_llm_setup(self):
        """Open the LLM setup configuration dialog."""
        dialog = LLMSetupDialog(self)
        
        # Connect the signal so the chat panel updates automatically
        if self.chat_panel:
            dialog.settingsChanged.connect(self.chat_panel.refresh_model_dropdown)
        
        if dialog.exec():
            # Refresh client if needed
            try:
                if hasattr(self, "llm_config") and self.llm_config is not None:
                    from llm.client import get_model_mapping
                    mapping = get_model_mapping()
                    
                    # If the current model is no longer available, pick the default or first one
                    if self.llm_config.model_key not in mapping:
                        default_model = APIKeyManager.load_default_model()
                        if default_model in mapping:
                            self.llm_config.model_key = default_model
                        elif mapping:
                            self.llm_config.model_key = list(mapping.keys())[0]
                    
                    # Force a client refresh
                    self._on_model_selected(self.llm_config.model_key)
            except Exception as e:
                self.statusBar().showMessage(f"Error updating LLM setup: {e}", self.STATUS_ERROR)



    # --- File operations ---
    def _should_index_file(self, file_path: str, max_size_kb: int = 100) -> bool:
        """
        Check if a file should be indexed based on its size.
        
        Args:
            file_path: Path to the file
            max_size_kb: Maximum file size in KB to index (default 100KB)
            
        Returns:
            True if file should be indexed, False otherwise
        """
        try:
            file_size = os.path.getsize(file_path)
            file_size_kb = file_size / 1024
            
            if file_size_kb > max_size_kb:
                # Ask user if they want to index large files
                reply = QMessageBox.question(
                    self,
                    "Large File Indexing",
                    f"The file is {file_size_kb:.1f}KB. Indexing large files may temporarily freeze the UI.\n\n"
                    f"Do you want to index this file for RAG context?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                return reply == QMessageBox.Yes
            
            return True
        except Exception as e:
            logger.exception("Error checking file size for %s", file_path)
            return False
    
    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open File", "", "Text Files (*.txt *.md);;Markdown Files (*.md);;Plain Text (*.txt);;All Files (*)")
        if path:
            self._open_file_path(path)

    def _open_file_path(self, path: str | Path) -> None:
        document_path = str(Path(path).resolve())
        try:
            content = self.document_service.read_text(document_path)
            previous_file = self.current_file
            self.editor.setPlainText(content)
            self.current_file = document_path
            self.editor.document().setModified(False)
            self.update_window_title()

            # Opening remains separate from indexing, but only the current file
            # receives the active-file retrieval boost.
            if self.rag_system:
                try:
                    if previous_file and previous_file != document_path:
                        self.rag_system.unmark_active_file(previous_file)
                    self.rag_system.mark_active_file(document_path)
                except Exception:
                    logger.exception(
                        "Failed to update active RAG file to %s",
                        document_path,
                    )
            self.statusBar().showMessage(
                f"Opened {os.path.basename(document_path)}",
                self.STATUS_QUICK,
            )
        except Exception as error:
            logger.exception("Unable to open document %s", document_path)
            QMessageBox.critical(self, "Error", str(error))


    def save_file(self):
        if not self.current_file:
            path, _ = QFileDialog.getSaveFileName(self, "Save File", "", "Text Files (*.txt *.md);;Markdown Files (*.md);;Plain Text (*.txt);;All Files (*)")
            if not path:
                return
            self.current_file = path

        try:
            self.document_service.write_text(
                self.current_file,
                self.editor.toPlainText(),
            )
            self.editor.document().setModified(False)
            self.update_window_title()

            project = (
                self.project_service.active_project
                if self.project_service is not None
                else None
            )
            if project is not None:
                try:
                    Path(self.current_file).resolve().relative_to(project.root_path)
                except ValueError:
                    pass
                else:
                    self._schedule_project_context_sync(project)
            
            if self.rag_system:
                self.statusBar().showMessage(
                    f"Saved {os.path.basename(self.current_file)}", self.STATUS_QUICK
                )
                
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            


    def save_file_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save File As", "", "Text Files (*.txt *.md);;Markdown Files (*.md);;Plain Text (*.txt);;All Files (*)")
        if not path:
            return
        self.current_file = path
        self.save_file()
        self.update_window_title()

    def close_file(self):
        # Unmark file as active in RAG system
        if self.rag_system and self.current_file:
            try:
                self.rag_system.unmark_active_file(self.current_file)
            except Exception as e:
                logger.exception("Failed to unmark active file %s", self.current_file)
        
        self.editor.clear()
        self.current_file = None
        self.untitled_count += 1
        self.editor.document().setModified(False)
        self.update_window_title()

    def new_file(self):
        self.close_file()

    def update_window_title(self, *args):
        """Update the window title to show document name and editor name."""
        if self.current_file:
            import os
            doc_name = os.path.basename(self.current_file)
        else:
            doc_name = f"Untitled {self.untitled_count}"
        
        is_modified = getattr(self.editor.document(), "isModified", lambda: False)()
        star = "*" if is_modified else ""
        project_service = getattr(self, "project_service", None)
        project = project_service.active_project if project_service else None
        project_label = f" — {project.name}" if project else ""

        self.setWindowTitle(f"{star}{doc_name}{project_label} - SammyAI")

    def _rebuild_active_project_context(self) -> None:
        """Force regeneration of the active project's context index."""
        project = (
            self.project_service.active_project
            if self.project_service is not None
            else None
        )
        if (
            project is None
            or self.context_engine is None
            or self.rag_system is None
        ):
            QMessageBox.information(
                self,
                "No Active Project",
                "Open a project before rebuilding its context index.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Rebuild Project Context",
            f"Rebuild the context index for '{project.name}'?\n\n"
            "This regenerates embeddings and may take some time.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.rebuild_project_context_action.setEnabled(False)
        self.statusBar().showMessage(
            f"Rebuilding context for {project.name}...",
            self.STATUS_PERSISTENT,
        )
        self._schedule_project_context_sync(project, force_reindex=True)

    # Legacy manual indexing methods
    def _index_current_file_manually(self):
        """User explicitly requests indexing of current file."""
        if not self.current_file:
            QMessageBox.warning(self, "No File", "No file is currently open.")
            return
        
        if not self.rag_system:
            QMessageBox.warning(self, "RAG Unavailable", "RAG system not initialized.")
            return
        
        # Check if already indexing
        with self._indexing_lock:
            if self._indexing_in_progress:
                QMessageBox.information(
                    self, 
                    "Indexing in Progress", 
                    "Already indexing a file. Please wait."
                )
                return
            self._indexing_in_progress = True
        
        # Check file size
        if not self._should_index_file(self.current_file, max_size_kb=500):
            with self._indexing_lock:
                self._indexing_in_progress = False
            return
        
        file_to_index = self.current_file
        file_size_kb = os.path.getsize(file_to_index) / 1024
        
        self._show_indexing_status(
            os.path.basename(file_to_index), 
            "start", 
            file_size_kb
        )
        
        def index_worker():
            try:
                # Index the file
                success = self.rag_system.index_file(file_to_index, force_reindex=True)
                
                if success:
                    # Mark as active
                    self.rag_system.mark_active_file(file_to_index)
                    
                    # Get stats
                    stats = self.rag_system.get_stats()
                    
                    # Update UI on main thread
                    QTimer.singleShot(0, lambda: self._show_indexing_status(
                        os.path.basename(file_to_index),
                        "success",
                        total_chunks=stats['total_documents']
                    ))
                else:
                    QTimer.singleShot(0, lambda: self._show_indexing_status(
                        os.path.basename(file_to_index),
                        "error"
                    ))
            except Exception as e:
                logger.exception("Error indexing current file %s", file_to_index)
                QTimer.singleShot(0, lambda: self.statusBar().showMessage(
                    f"✗ Error indexing: {str(e)}", 
                    self.STATUS_ERROR
                ))
            finally:
                # Release the lock
                with self._indexing_lock:
                    self._indexing_in_progress = False
        
        # Start indexing in background (thread started within lock released)
        self.task_runner.submit(index_worker, name="index-current-file")

    def _upload_file_for_rag(self):
        """Upload a file (.txt, .md, .pdf) for RAG indexing."""
        if not self.rag_system:
            QMessageBox.warning(self, "RAG Unavailable", "RAG system not initialized.")
            return

        path = self._open_file_dialog(
            "Upload File for RAG indexing", 
            "Allowed Files (*.txt *.pdf *.md);;Text Files (*.txt);;Markdown Files (*.md);;PDF Files (*.pdf);;All Files (*)"
        )
        if not path:
            return

        # Check if already indexing
        with self._indexing_lock:
            if self._indexing_in_progress:
                QMessageBox.information(
                    self, 
                    "Indexing in Progress", 
                    "Already indexing a file. Please wait."
                )
                return
            self._indexing_in_progress = True

        # Check file size (larger limit than CIN, maybe 1MB)
        if not self._should_index_file(path, max_size_kb=1000):
            with self._indexing_lock:
                self._indexing_in_progress = False
            return

        file_to_index = path
        file_size_kb = os.path.getsize(file_to_index) / 1024

        self._show_indexing_status(
            os.path.basename(file_to_index),
            "start",
            file_size_kb
        )

        def index_worker():
            try:
                # Index the file
                success = self.rag_system.index_file(file_to_index, force_reindex=False)
                
                if success:
                    # Get stats
                    stats = self.rag_system.get_stats()
                    
                    # Update UI on main thread
                    QTimer.singleShot(0, lambda: self._show_indexing_status(
                        os.path.basename(file_to_index),
                        "success",
                        total_chunks=stats['total_documents']
                    ))
                    # Also show success dialog as it's a manual upload
                    QTimer.singleShot(0, lambda: QMessageBox.information(
                        self, "RAG Indexing Success",
                        f"File '{os.path.basename(file_to_index)}' has been indexed for RAG.\n"
                        f"Total chunks in system: {stats['total_documents']}"
                    ))
                else:
                    QTimer.singleShot(0, lambda: self._show_indexing_status(
                        os.path.basename(file_to_index),
                        "error"
                    ))
            except Exception as e:
                logger.exception("Error indexing uploaded file %s", file_to_index)
                QTimer.singleShot(0, lambda: self.statusBar().showMessage(
                    f"✗ Error indexing: {str(e)}", 
                    self.STATUS_ERROR
                ))
            finally:
                # Release the lock
                with self._indexing_lock:
                    self._indexing_in_progress = False
        
        # Start indexing in background
        self.task_runner.submit(index_worker, name="index-uploaded-file")

    # Manage RAG index method
    def _manage_rag_index(self):
        """Open the legacy low-level index management dialog."""
        if not self.rag_system:
            QMessageBox.warning(self, "RAG Unavailable", "RAG system not initialized.")
            return
            
        dialog = RAGFileManagementDialog(self.rag_system, self)
        dialog.exec()
        if self.context_engine is not None:
            self.context_engine.invalidate_index_state()

    def _clear_rag_index(self):
        """Reset the low-level index and rebuild the active project."""
        if not self.rag_system:
            QMessageBox.warning(
                self,
                "Context Index Unavailable",
                "The context index is not initialized.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Reset Context Index",
            "This removes the complete local context index. The active "
            "project will then be rebuilt automatically.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            self.rag_system.clear_index()
            if self.context_engine is not None:
                self.context_engine.invalidate_index_state()
            project = (
                self.project_service.active_project
                if self.project_service is not None
                else None
            )
            if project is not None and self.context_engine is not None:
                self.rebuild_project_context_action.setEnabled(False)
                self.statusBar().showMessage(
                    f"Reset complete; rebuilding context for {project.name}...",
                    self.STATUS_PERSISTENT,
                )
                self._schedule_project_context_sync(
                    project,
                    force_reindex=True,
                )
            else:
                self.statusBar().showMessage(
                    "Context index reset",
                    self.STATUS_NORMAL,
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Context Index Error",
                f"Failed to reset the context index: {e}",
            )
    
    # Show RAG statistics method
    def _show_rag_stats(self):
        """Display RAG system statistics."""
        if not self.rag_system:
            QMessageBox.warning(self, "RAG Unavailable", "RAG system not initialized.")
            return
        
        try:
            stats = self.rag_system.get_stats()
            
            message = f"""Context Index Statistics

    Total chunks indexed: {stats['total_documents']}
    Indexed files: {stats['indexed_files']}
    Active files: {stats['active_files']}
    Embedding dimension: {stats['embedding_dimension']}

    Files in index:
    """
            for file_path in stats['files']:
                message += f"• {os.path.basename(file_path)}\n"
            
            if not stats['files']:
                message += "(No files indexed yet)\n"
            
            QMessageBox.information(self, "Context Index Statistics", message)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to get RAG stats: {e}")

    def _manage_project_memory(self) -> None:
        if self.memory_service is None:
            QMessageBox.warning(
                self,
                "Project Memory Unavailable",
                "Persistent memory is not initialized.",
            )
            return
        try:
            dialog = MemoryManagementDialog(self.memory_service, self)
        except MemoryError as error:
            QMessageBox.warning(self, "Project Memory", str(error))
            return
        dialog.exec()

    def _summarize_current_chat(self) -> None:
        project = (
            self.project_service.active_project
            if self.project_service is not None
            else None
        )
        session = self.chat_manager.get_active_session()
        if (
            project is None
            or self.memory_service is None
            or session is None
        ):
            QMessageBox.information(
                self,
                "Cannot Summarize Chat",
                "Open a project and start a chat before creating persistent "
                "memory.",
            )
            return
        if self.llm_client is None:
            QMessageBox.warning(
                self,
                "LLM Unavailable",
                "Configure an LLM before summarizing the conversation.",
            )
            return
        conversation = [
            message.to_llm_format()
            for message in session.messages
            if message.role in {MessageRole.USER, MessageRole.ASSISTANT}
        ]
        if not conversation:
            QMessageBox.information(
                self,
                "Empty Chat",
                "The current chat has no messages to summarize.",
            )
            return

        client = self.llm_client
        self.summarize_chat_action.setEnabled(False)
        self._chat_panel_safe(
            "set_status",
            "Preparing a conversation-memory draft...",
        )

        def worker() -> None:
            try:
                def complete(messages, system_prompt):
                    with self._llm_lock:
                        original_prompt = client.system_prompt
                        try:
                            client.system_prompt = system_prompt
                            return client.chat(messages)
                        finally:
                            client.system_prompt = original_prompt

                draft = self.conversation_summarizer.generate(
                    project_id=project.id,
                    session_id=session.session_id,
                    messages=conversation,
                    complete=complete,
                )
                self.memory_summary_ready.emit(draft)
            except Exception as error:
                self.memory_summary_failed.emit(str(error))

        self.task_runner.submit(worker, name="summarize-memory")

    @Slot(object)
    def _review_memory_summary(
        self,
        draft: ConversationSummaryDraft,
    ) -> None:
        self.summarize_chat_action.setEnabled(True)
        if self.memory_service is None:
            return
        project = self.memory_service.active_project
        if project is None or project.id != draft.project_id:
            QMessageBox.warning(
                self,
                "Project Changed",
                "The active project changed while the summary was generated. "
                "Nothing was saved.",
            )
            return
        dialog = SummaryReviewDialog(draft, self)
        if dialog.exec() != QDialog.Accepted:
            self._chat_panel_safe(
                "set_status",
                "Conversation-memory draft discarded",
            )
            return
        try:
            summary, memories = self.memory_service.save_summary_draft(
                dialog.reviewed_draft(),
                dialog.selected_memory_indices(),
            )
        except MemoryError as error:
            QMessageBox.warning(
                self,
                "Unable to Save Memory",
                str(error),
            )
            return
        self._chat_panel_safe(
            "add_system_message",
            f"Saved conversation summary '{summary.title}' and "
            f"{len(memories)} structured memory item(s).",
        )
        self.statusBar().showMessage(
            "Persistent project memory updated",
            self.STATUS_NORMAL,
        )

    @Slot(str)
    def _handle_memory_summary_error(self, error: str) -> None:
        project = (
            self.project_service.active_project
            if self.project_service is not None
            else None
        )
        self.summarize_chat_action.setEnabled(
            project is not None
            and self.memory_service is not None
            and self.llm_client is not None
        )
        self._chat_panel_safe(
            "add_system_message",
            f"Unable to summarize this conversation: {error}",
        )
        self.statusBar().showMessage(
            "Conversation summary failed",
            self.STATUS_ERROR,
        )

    # --- Temporary external references (legacy CIN implementation) ---
    def _upload_cin_file(self):
        """Attach a small external reference to the active conversation."""
        path = self._open_file_dialog(
            "Attach Reference",
            "Allowed Files (*.txt *.pdf *.md);;Text Files (*.txt);;Markdown Files (*.md);;PDF Files (*.pdf);;All Files (*)"
        )
        if not path:
            return

        # Check file size (50kB limit)
        file_size_kb = os.path.getsize(path) / 1024
        if file_size_kb > 50:
            QMessageBox.warning(
                self,
                "Reference Too Large",
                "Temporary references are limited to files smaller than "
                f"50kB. The selected file is {file_size_kb:.1f}kB.\n"
                "Add larger references to the active project instead.",
            )
            return

        self.statusBar().showMessage(
            f"Attaching {os.path.basename(path)}...",
            0,
        )

        try:
            content = self.document_service.extract_context_text(path)

            if content:
                self.chat_manager.cin_context = content
                self.clear_cin_action.setEnabled(True)
                self.statusBar().showMessage(
                    f"✓ Attached {os.path.basename(path)}",
                    self.STATUS_NORMAL,
                )
                QMessageBox.information(
                    self,
                    "Reference Attached",
                    f"'{os.path.basename(path)}' is attached to this "
                    "conversation.\nSammyAI will use it when relevant.",
                )
            else:
                self.statusBar().showMessage(
                    "✗ Could not read the reference",
                    self.STATUS_ERROR,
                )
                QMessageBox.warning(
                    self,
                    "Reference Error",
                    "No text could be extracted from the selected file.",
                )

        except Exception as e:
            self.statusBar().showMessage(
                f"✗ Reference error: {str(e)}",
                self.STATUS_ERROR,
            )
            QMessageBox.critical(
                self,
                "Reference Error",
                f"Unable to attach the selected reference: {str(e)}",
            )

    def _clear_cin_context(self):
        """Remove the temporary reference from the active conversation."""
        self.chat_manager.cin_context = None
        self.clear_cin_action.setEnabled(False)
        self.statusBar().showMessage(
            "Attached reference removed",
            self.STATUS_NORMAL,
        )
        QMessageBox.information(
            self,
            "Reference Removed",
            "The temporary reference has been removed from this conversation.",
        )

    # --- DBE (Diff-Based Editing) methods ---
    def _compare_with_file(self):
        """Compare current text with another file using diff viewer."""
        # Get current text
        current_text = self.editor.toPlainText()
        
        if not current_text:
            QMessageBox.warning(self, "No Content", "Current editor is empty.")
            return
        
        # Select file to compare
        path = self._open_file_dialog(
            "Select File to Compare", 
            "Text Files (*.txt);;All Files (*)"
        )
        
        if not path:
            return
        
        try:
            other_text = self.document_service.read_text(path)
            
            # Create diff dialog
            dialog = self._create_diff_dialog()
            
            current_name = self.current_file if self.current_file else "current"
            dialog.diff_viewer.load_diff(current_text, other_text, current_name, path)
            
            # If user applies the diff, update the editor
            if dialog.exec() == QDialog.Accepted:
                modified_text = dialog.diff_viewer.get_modified_text()
                if self._apply_reviewed_editor_change(
                    current_text,
                    modified_text,
                ):
                    self.statusBar().showMessage("Diff applied successfully", self.STATUS_NORMAL)
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to compare files: {e}")

    def _compare_with_clipboard(self):
        """Compare current text with clipboard content using diff viewer."""
        # Get current text
        current_text = self.editor.toPlainText()
        
        if not current_text:
            QMessageBox.warning(self, "No Content", "Current editor is empty.")
            return
        
        # Get clipboard text
        clipboard = QApplication.clipboard()
        clipboard_text = clipboard.text()
        
        if not clipboard_text:
            QMessageBox.warning(self, "Empty Clipboard", "Clipboard is empty.")
            return
        
        # Create diff dialog
        dialog = self._create_diff_dialog()
        
        current_name = self.current_file if self.current_file else "current"
        dialog.diff_viewer.load_diff(current_text, clipboard_text, current_name, "clipboard")
        
        # If user applies the diff, update the editor
        if dialog.exec() == QDialog.Accepted:
            modified_text = dialog.diff_viewer.get_modified_text()
            if self._apply_reviewed_editor_change(
                current_text,
                modified_text,
            ):
                self.statusBar().showMessage("Diff applied successfully", self.STATUS_NORMAL)

    def _apply_diff_from_file(self):
        """Apply a diff file to current text."""
        # Get current text
        current_text = self.editor.toPlainText()
        
        if not current_text:
            QMessageBox.warning(self, "No Content", "Current editor is empty.")
            return
        
        # Select diff file
        path = self._open_file_dialog(
            "Select Diff File", 
            "Diff Files (*.diff *.patch);;All Files (*)"
        )
        
        if not path:
            return
        
        try:
            diff_string = self.document_service.read_text(path)
            
            # Create diff dialog
            dialog = self._create_diff_dialog()
            dialog.diff_viewer.load_diff_from_string(diff_string, current_text)
            
            # If user applies the diff, update the editor
            if dialog.exec() == QDialog.Accepted:
                modified_text = dialog.diff_viewer.get_modified_text()
                if self._apply_reviewed_editor_change(
                    current_text,
                    modified_text,
                ):
                    self.statusBar().showMessage("Diff applied successfully", self.STATUS_NORMAL)
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to apply diff: {e}")

    def _create_diff_dialog(self):
        """Create a diff viewer dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Diff Viewer - DBE")
        dialog.setGeometry(100, 100, 900, 600)
        
        layout = QVBoxLayout(dialog)
        
        diff_viewer = DiffViewerWidget(dialog, diff_manager=self.diff_manager)
        layout.addWidget(diff_viewer)
        
        # Store reference for access
        dialog.diff_viewer = diff_viewer
        
        # Connect signals
        diff_viewer.diff_applied.connect(dialog.accept)
        diff_viewer.diff_rejected.connect(dialog.reject)
        
        return dialog

    def _toggle_dbe_mode(self):
        """Toggle the legacy DBE chat workflow on or off."""
        self.dbe_enabled = self.toggle_dbe_action.isChecked()
        
        if self.dbe_enabled:
            self.statusBar().showMessage(
                "Legacy DBE mode enabled",
                self.STATUS_NORMAL,
            )
            self._chat_panel_safe(
                "add_system_message",
                "Legacy DBE mode enabled. Chat suggestions will be routed "
                "through the original single-document diff workflow.",
            )
        else:
            self.statusBar().showMessage(
                "Legacy DBE mode disabled",
                self.STATUS_NORMAL,
            )
            self._chat_panel_safe(
                "add_system_message",
                "Legacy DBE mode disabled. Returning to normal chat.",
            )
    
    def _get_editor_context_for_dbe(self) -> tuple[str, int, Optional[int], Optional[int]]:
        """
        Get editor context for DBE mode.
        
        Returns:
            Tuple of (text, cursor_line, selection_start, selection_end)
        """
        text = self.editor.toPlainText()
        cursor = self.editor.textCursor()
        
        # Get cursor line (1-indexed)
        cursor_line = cursor.blockNumber() + 1
        
        # Check if there's a selection
        if cursor.hasSelection():
            # Get selection start and end blocks
            start_block = self.editor.document().findBlock(cursor.selectionStart())
            end_block = self.editor.document().findBlock(cursor.selectionEnd())
            
            selection_start = start_block.blockNumber() + 1
            selection_end = end_block.blockNumber() + 1
        else:
            selection_start = None
            selection_end = None
        
        return text, cursor_line, selection_start, selection_end
    
    def _extract_text_from_llm_response(self, response: str) -> str:
        """
        Extract revised text from LLM response.
        
        For now, we assume the LLM returns clean text.
        In the future, we could add parsing for markdown code blocks.
        
        Args:
            response: LLM response
            
        Returns:
            Extracted text
        """
        # Remove common markdown code block wrappers if present
        text = response.strip()
        
        # Check for markdown code blocks
        if text.startswith("```") and text.endswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (the ``` markers)
            if len(lines) > 2:
                text = "\n".join(lines[1:-1])
        
        return text.strip()


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):
        return QSize(self._editor.lineNumberAreaWidth(), 0)

    def paintEvent(self, event):
        self._editor.lineNumberAreaPaintEvent(event)


class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.lineNumberArea = LineNumberArea(self)

        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)

        self.updateLineNumberAreaWidth(0)
        self.highlightCurrentLine()

    def lineNumberAreaWidth(self):
        # Calculate space needed for line numbers
        digits = len(str(max(1, self.blockCount())))
        space = self.fontMetrics().horizontalAdvance('9') * digits + 12
        return space

    def updateLineNumberAreaWidth(self, _):
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def _get_editor_background_color(self):
        ss = QApplication.instance().styleSheet() or ""
        m = re.search(r"QPlainTextEdit\s*\{[^}]*background-color\s*:\s*([^;]+);", ss)
        if m:
            try:
                return QColor(m.group(1).strip())
            except Exception:
                pass
        return self.palette().color(QPalette.Base)

    def _get_editor_text_color(self):
        color_str = _extract_color_from_stylesheet("QPlainTextEdit", "color")
        if color_str:
            try:
                return QColor(color_str)
            except Exception:
                pass
        return self.palette().color(QPalette.Text)

    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(QRect(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height()))

    def highlightCurrentLine(self):
        # Removing the yellow highlight to avoid low-contrast issues with dark themes.
        # We intentionally do not set any extra selections here so the current line
        # remains unhighlighted and text visibility is preserved.
        self.setExtraSelections([])

    def lineNumberAreaPaintEvent(self, event):
        # Determine editor background and text color before creating the painter
        bg_color = self._get_editor_background_color()
        text_color = self._get_editor_text_color()
        painter = QPainter(self.lineNumberArea)
        painter.fillRect(event.rect(), bg_color)
        
        # Set the painter font to match the editor's font
        painter.setFont(self.font())

        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        height = self.fontMetrics().height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1)
                # Use the editor's text color so numbers contrast correctly
                painter.setPen(text_color)
                painter.drawText(0, top, self.lineNumberArea.width() - 4, height, Qt.AlignRight, number)

            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            blockNumber += 1


    # Note: file operation methods (open/save/close/new) and edit action handlers
    # are implemented on the TextEditor container and forward to this widget.

def load_stylesheet(app: QApplication, path: str | Path) -> None:
    stylesheet_path = Path(path)
    app.setStyleSheet(stylesheet_path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    """Start the SammyAI desktop application."""

    paths = get_app_paths()
    log_file = configure_logging(paths.log_dir)
    install_exception_hook()
    logger.info("Starting SammyAI; log file: %s", log_file)

    migrated = migrate_legacy_runtime_data(source_root(), paths)
    if migrated:
        logger.info("Copied legacy runtime data: %s", ", ".join(migrated))

    app = QApplication(list(sys.argv if argv is None else argv))
    app.setApplicationName("SammyAI")
    app.setOrganizationName("SammyAI")

    stylesheet = asset_path("ui", "styles", "dark_theme.qss")
    try:
        load_stylesheet(app, stylesheet)
    except OSError:
        logger.exception("Unable to load stylesheet from %s", stylesheet)

    editor = TextEditor(app_paths=paths)
    editor.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
