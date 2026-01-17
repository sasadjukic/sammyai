import sys
import re
import os
from typing import Optional
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPlainTextEdit, QFileDialog, QMessageBox, QToolBar,
    QToolButton, QMenu, QWidget, QLabel, QStatusBar, QInputDialog, QLineEdit,
    QHBoxLayout, QPushButton, QVBoxLayout, QDockWidget
)
from PySide6.QtGui import QAction, QKeySequence, QIcon, QPainter, QColor, QFont, QTextFormat, QPalette, QTextCursor, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt, QRect, QSize, QTimer, Signal, Slot
import threading
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtWidgets import QApplication, QStyle, QTextEdit
from api_key_manager import APIKeyDialog, APIKeyManager

# LLM integration
from llm.client import LLMConfig
from llm.chat_manager import ChatManager, MessageRole

# Chat UI
from ui.chat_panel import ChatPanel

# RAG system
from rag.rag_system import RAGSystem

# Diff-based editing
from PySide6.QtWidgets import QDialog
from editing.diff_viewer import DiffViewerWidget
from editing.diff_manager import DiffManager


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
    
    def __init__(self):
        super().__init__()

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
        self.update_window_title()

        # --- Initialize RAG system ---
        try:
            rag_persist_dir = os.path.join(os.path.dirname(__file__), "cache", "index")
            rag_cache_dir = os.path.join(os.path.dirname(__file__), "cache", "embeddings")
            self.rag_system = RAGSystem(
                chunk_size=500,
                overlap=50,
                persist_dir=rag_persist_dir,
                cache_dir=rag_cache_dir,
                max_documents=1000000,
                max_chunks_per_file=150000
            )
            self.statusBar().showMessage("RAG system initialized", 2000)
        except Exception as e:
            self.rag_system = None
            print(f"RAG system initialization failed: {e}")

        # --- Initialize LLM and chat manager ---
        # Chat sessions will be stored under the package's llm/chat_sessions folder (if present)
        try:
            sessions_dir = os.path.join(os.path.dirname(__file__), "llm", "chat_sessions")
            self.chat_manager = ChatManager(storage_dir=sessions_dir, rag_system=self.rag_system)
        except Exception:
            # Fall back to in-memory manager
            self.chat_manager = ChatManager(rag_system=self.rag_system)

        # Load existing sessions and ensure an active one exists
        self.chat_manager.load_all_sessions()
        if not self.chat_manager.get_active_session():
            self.chat_manager.create_session()

        # Create default LLM client via LLMConfig; handle initialization errors gracefully
        try:
            self.llm_config = LLMConfig()
            self.llm_client = self.llm_config.create_client()
            self.statusBar().showMessage("LLM client initialized", 3000)
        except Exception as e:
            self.llm_client = None
            # Non-fatal; show status so user knows LLM features aren't ready
            self.statusBar().showMessage(f"LLM client not initialized: {e}")

        # Connect LLM signals
        self.llm_response_received.connect(self._handle_llm_response)
        self.llm_error_occurred.connect(self._handle_llm_error)
        self.dbe_diff_ready.connect(self._show_dbe_diff)

        # Chat panel (created lazily when the agent button is pressed)
        self.chat_dock: QDockWidget | None = None
        self.chat_panel: ChatPanel | None = None

        # Track if indexing is in progress
        self._indexing_in_progress = False
        self._indexing_lock = threading.Lock()

        # Initialize DBE state
        self.dbe_enabled = False
        self.dbe_context_lines = 20  # Number of lines before/after cursor for context
        self.diff_manager = DiffManager()


    def create_actions(self):
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
        # We'll track the last edit-related action so "Repeat" can re-run it
        self._last_edit_action = None

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

        # Redo: use Ctrl+Y
        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcut(QKeySequence("Ctrl+Y"))  # Ctrl+Y
        self.redo_action.triggered.connect(self._on_redo)

        # Repeat: Shift+Ctrl+Y
        self.repeat_action = QAction("Repeat", self)
        self.repeat_action.setShortcut(QKeySequence("Ctrl+Shift+Y"))  # Shift+Ctrl+Y
        self.repeat_action.triggered.connect(self._on_repeat)

        # Extra placeholder actions (icons only, no functionality yet)
        self.agent_action = QAction("Agent", self)
        self.agent_action.setEnabled(True)
        self.agent_action.setToolTip("Open Sammy AI chat panel")
        self.agent_action.triggered.connect(self._toggle_chat_panel)

        self.key_action = QAction("API Key", self)
        self.key_action.setToolTip("Configure API Key")
        self.key_action.triggered.connect(self._on_configure_api_key)

        self.settings_action = QAction("Settings", self)
        self.settings_action.setEnabled(False)

        # Initial enable/disable states
        self.copy_action.setEnabled(False)
        self.cut_action.setEnabled(False)
        # Undo/redo availability will be driven by document signals
        self.undo_action.setEnabled(False)
        self.redo_action.setEnabled(False)

        # Manual RAG indexing action
        self.index_action = QAction("Index Current File for RAG", self)
        self.index_action.setShortcut(QKeySequence("Ctrl+Shift+I"))
        self.index_action.triggered.connect(self._index_current_file_manually)
        self.index_action.setStatusTip("Index current file for AI assistant context")

        # CIN actions
        self.upload_cin_action = QAction("Upload File for CIN", self)
        self.upload_cin_action.triggered.connect(self._upload_cin_file)
        self.upload_cin_action.setStatusTip("Upload a small file (< 50kB) for direct context injection")

        self.clear_cin_action = QAction("Clear CIN Context", self)
        self.clear_cin_action.triggered.connect(self._clear_cin_context)
        self.clear_cin_action.setStatusTip("Clear the current CIN injected context")

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

        # DBE mode toggle
        self.toggle_dbe_action = QAction("Enable DBE Mode", self)
        self.toggle_dbe_action.setCheckable(True)
        self.toggle_dbe_action.setChecked(False)
        self.toggle_dbe_action.triggered.connect(self._toggle_dbe_mode)
        self.toggle_dbe_action.setStatusTip("Enable diff-based editing mode for LLM suggestions")

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
            # Try to derive a visible color from the editor if available
            try:
                color = self.editor._get_editor_text_color().name()
            except Exception:
                color = "#ffffff"

        try:
            icons_dir = os.path.join(os.path.dirname(__file__), "icons")
            svg_path = os.path.join(icons_dir, f"{base_name}.svg")

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

    # We no longer create a top menu bar; the File menu is a drop-down on the toolbar

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
        # Helper to retrieve themed or fallback icons
        # Use the shared icon loader
        def _icon(theme_name, fallback):
            return self._load_icon(theme_name, fallback)

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

        # Bottom-only icons (no functionality yet)
        self.agent_action.setIcon(self._load_colored_svg_icon("agent"))
        self.key_action.setIcon(self._load_colored_svg_icon("key"))
        self.settings_action.setIcon(self._load_colored_svg_icon("settings"))

        toolbar.addAction(self.agent_action)
        toolbar.addAction(self.key_action)
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

        # RAG menu
        rag_menu = menubar.addMenu("RAG")
        rag_menu.addAction(self.index_action)
    
        # Add action to clear RAG index
        clear_rag_action = QAction("Clear RAG Index", self)
        clear_rag_action.triggered.connect(self._clear_rag_index)
        rag_menu.addAction(clear_rag_action)
    
        # Add action to show RAG stats
        rag_stats_action = QAction("Show RAG Statistics", self)
        rag_stats_action.triggered.connect(self._show_rag_stats)
        rag_menu.addAction(rag_stats_action)

        # CIN menu
        cin_menu = menubar.addMenu("CIN")
        cin_menu.addAction(self.upload_cin_action)
        cin_menu.addAction(self.clear_cin_action)

        # DBE (Diff-Based Editing) menu
        dbe_menu = menubar.addMenu("DBE")
        dbe_menu.addAction(self.toggle_dbe_action)
        dbe_menu.addSeparator()
        dbe_menu.addAction(self.compare_file_action)
        dbe_menu.addAction(self.compare_clipboard_action)
        dbe_menu.addSeparator()
        dbe_menu.addAction(self.apply_diff_action)

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
            # When clear chat is requested, clear the session
            self.chat_panel.clear_chat_requested.connect(self._on_clear_chat_requested)

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
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self, "Chat Panel Error", str(e))

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
            self.chat_manager.add_message(MessageRole.USER, message)
        except Exception:
            pass

        # If LLM not available, inform the user
        if not self.llm_client:
            if self.chat_panel:
                self.chat_panel.add_system_message("LLM client not initialized. Configure API key or check environment.")
                self.chat_panel.set_thinking(False)
            return

        # Check if DBE mode is enabled
        if self.dbe_enabled:
            # DBE mode: inject editor context and show diff
            self._handle_dbe_request(message)
        else:
            # Normal mode: standard chat
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
            print(f"Error clearing chat session: {e}")
    
    def _handle_normal_chat(self, message: str):
        """Handle normal chat mode (non-DBE)."""
        # Run LLM query in background thread to avoid blocking UI
        def worker():
            try:
                # Prepare messages for the LLM using the chat manager's active session
                # Always check for potential RAG or CIN context
                if self.chat_manager:
                    msgs = self.chat_manager.get_messages_for_llm_with_context(
                        query=message,
                        top_k=3
                    )
                else:
                    # Fallback unlikely as chat_manager is core
                    msgs = [{"role": "user", "content": message}]
                
                # Call the synchronous chat API (blocking) in the thread
                reply = self.llm_client.chat(msgs)

                # Add assistant message to session
                try:
                    self.chat_manager.add_message(MessageRole.ASSISTANT, reply)
                except Exception:
                    pass

                # Emit signal to update UI on main thread
                self.llm_response_received.emit(reply)
            except Exception as e:
                self.llm_error_occurred.emit(str(e))

        t = threading.Thread(target=worker, daemon=True)
        t.start()
    
    def _handle_dbe_request(self, message: str):
        """Handle DBE mode request with editor context."""
        # Get editor context
        text, cursor_line, selection_start, selection_end = self._get_editor_context_for_dbe()
        
        if not text:
            if self.chat_panel:
                self.chat_panel.set_thinking(False)
                self.chat_panel.add_system_message("⚠️ Editor is empty. Please add some text before using DBE mode.")
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
                
                # Temporarily override system prompt for DBE
                original_prompt = self.llm_client.system_prompt
                self.llm_client.system_prompt = get_dbe_system_prompt()
                
                # Get messages with editor context
                msgs = self.chat_manager.get_messages_for_llm_with_dbe_context(
                    query=message,
                    editor_context=editor_context
                )
                
                # Call LLM
                reply = self.llm_client.chat(msgs)
                
                # Restore original prompt
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
        
        t = threading.Thread(target=worker, daemon=True)
        t.start()
    
    @Slot(str, str, str)
    def _show_dbe_diff(self, original: str, modified: str, user_request: str):
        """Show DBE diff in viewer (called on main thread)."""
        if self.chat_panel:
            self.chat_panel.set_thinking(False)
        
        # Create diff dialog
        dialog = self._create_diff_dialog()
        dialog.setWindowTitle(f"DBE Suggestion - {user_request[:50]}...")
        
        # Load diff
        dialog.diff_viewer.load_diff(
            original, modified,
            "current", "llm_suggestion"
        )
        
        # Show dialog
        if dialog.exec() == QDialog.Accepted:
            # User approved - apply changes
            modified_text = dialog.diff_viewer.get_modified_text()
            if modified_text:
                self.editor.setPlainText(modified_text)
                if self.chat_panel:
                    self.chat_panel.add_system_message("✓ Changes applied successfully!")
                self.statusBar().showMessage("✓ DBE changes applied", 3000)
        else:
            # User rejected
            if self.chat_panel:
                self.chat_panel.add_system_message("✗ Changes rejected")
            self.statusBar().showMessage("✗ DBE changes rejected", 3000)

    
    @Slot(str)
    def _handle_llm_response(self, reply: str):
        """Handle successful LLM response on main thread."""
        if self.chat_panel:
            self.chat_panel.set_thinking(False)
            self.chat_panel.add_assistant_message(reply)
            
    @Slot(str)
    def _handle_llm_error(self, error_msg: str):
        """Handle LLM error on main thread."""
        if self.chat_panel:
            self.chat_panel.set_thinking(False)
            self.chat_panel.add_system_message(f"LLM error: {error_msg}")

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
            if self.chat_panel:
                self.chat_panel.add_system_message(f"Switched model to {model_key}")
            # Also show a short statusbar message
            try:
                self.statusBar().showMessage(f"Using model: {model_key}", 3000)
            except Exception:
                pass
        except Exception as e:
            # Rollback model_key if possible
            try:
                if old_model is not None:
                    self.llm_config.model_key = old_model
            except Exception:
                pass
            # Inform the user in the chat panel
            if self.chat_panel:
                self.chat_panel.add_system_message(f"Failed to switch model to {model_key}: {e}")


    # --- Edit action handlers (TextEditor forwards to the editor widget) ---
    def _on_copy(self):
        self.editor.copy()
        self._last_edit_action = "copy"

    def _on_paste(self):
        self.editor.paste()
        self._last_edit_action = "paste"

    def _on_cut(self):
        self.editor.cut()
        self._last_edit_action = "cut"

    def _on_undo(self):
        self.editor.undo()
        self._last_edit_action = "undo"

    def _on_redo(self):
        self.editor.redo()
        self._last_edit_action = "redo"

    def _on_repeat(self):
        action = self._last_edit_action
        if not action:
            return
        if action == "copy":
            self.editor.copy()
        elif action == "paste":
            self.editor.paste()
        elif action == "cut":
            self.editor.cut()
        elif action == "undo":
            self.editor.undo()
        elif action == "redo":
            self.editor.redo()
    
    def _on_configure_api_key(self):
        """Open the API key configuration dialog."""
        dialog = APIKeyDialog(self)
        # Run the dialog; after it closes, pick up the stored key and refresh
        # the LLM configuration so cloud model selection can succeed.
        dialog.exec()

        try:
            # Update the active LLM configuration
            if hasattr(self, "llm_config") and self.llm_config is not None:
                # We need to refresh the key for the current model's provider
                from llm.client import MODEL_MAPPING
                model_config = MODEL_MAPPING.get(self.llm_config.model_key, {})
                provider = model_config.get("provider", "local")
                
                if provider != "local":
                    self.llm_config.api_key = APIKeyManager.load_api_key(provider)
                else:
                    self.llm_config.api_key = None

                # Try to re-create the client so any errors surface immediately
                try:
                    new_client = self.llm_config.create_client()
                    self.llm_client = new_client
                    if self.chat_panel:
                        self.chat_panel.add_system_message("API key configured. LLM client refreshed.")
                    try:
                        self.statusBar().showMessage("API key configured", 3000)
                    except Exception:
                        pass
                except Exception as e:
                    # If creating the client fails (e.g., no API key for cloud model), keep
                    # the previous client (if any) and inform the user via the chat panel
                    if self.chat_panel:
                        self.chat_panel.add_system_message(f"Failed to refresh LLM client: {e}")
                    try:
                        self.statusBar().showMessage(f"Failed to refresh LLM client: {e}", 5000)
                    except Exception:
                        pass
        except Exception:
            # Non-fatal: do not crash the settings dialog
            pass

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
            print(f"Error checking file size: {e}")
            return False
    
    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open File", "", "Text Files (*.txt)")
        if path:
            try:
                with open(path, "r", encoding="utf-8") as file:
                    self.editor.setPlainText(file.read())
                self.current_file = path
                self.update_window_title()
                
                # Only mark as active, DON'T index automatically
                if self.rag_system:
                    try:
                        self.rag_system.mark_active_file(path)
                        self.statusBar().showMessage(
                            f"Opened {os.path.basename(path)}", 2000
                        )
                    except Exception as e:
                        print(f"Failed to mark active file: {e}")
                        
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))


    def save_file(self):
        if not self.current_file:
            path, _ = QFileDialog.getSaveFileName(self, "Save File", "", "Text Files (*.txt)")
            if not path:
                return
            self.current_file = path

        try:
            with open(self.current_file, "w", encoding="utf-8") as file:
                file.write(self.editor.toPlainText())
            self.update_window_title()
            
            # No auto-reindex on save
            # Just show a saved message
            if self.rag_system:
                self.statusBar().showMessage(
                    f"Saved {os.path.basename(self.current_file)}", 2000
                )
                
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            


    def save_file_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save File As", "", "Text Files (*.txt);;All Files (*)")
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
                print(f"Failed to unmark active file: {e}")
        
        self.editor.clear()
        self.current_file = None
        self.untitled_count += 1
        self.update_window_title()

    def new_file(self):
        # Unmark previous file as active in RAG system
        if self.rag_system and self.current_file:
            try:
                self.rag_system.unmark_active_file(self.current_file)
            except Exception as e:
                print(f"Failed to unmark active file: {e}")
        
        self.editor.clear()
        self.current_file = None
        self.untitled_count += 1
        self.update_window_title()

    def update_window_title(self):
        """Update the window title to show document name and editor name."""
        if self.current_file:
            import os
            doc_name = os.path.basename(self.current_file)
        else:
            doc_name = f"Untitled {self.untitled_count}"
        
        self.setWindowTitle(f"{doc_name} - SammyAI")

    # Manual indexing method
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
        
        self.statusBar().showMessage(
            f"Indexing {os.path.basename(file_to_index)} ({file_size_kb:.1f}KB)...", 
            0  # Keep showing until done
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
                    QTimer.singleShot(0, lambda: self.statusBar().showMessage(
                        f"✓ Indexed {os.path.basename(file_to_index)} "
                        f"({stats['total_documents']} total chunks)", 
                        3000
                    ))
                else:
                    QTimer.singleShot(0, lambda: self.statusBar().showMessage(
                        f"✗ Failed to index {os.path.basename(file_to_index)}", 
                        3000
                    ))
            except Exception as e:
                print(f"Indexing error: {e}")
                QTimer.singleShot(0, lambda: self.statusBar().showMessage(
                    f"✗ Error indexing: {str(e)}", 
                    5000
                ))
            finally:
                # Release the lock
                with self._indexing_lock:
                    self._indexing_in_progress = False
        
        # Start indexing in background
        t = threading.Thread(target=index_worker, daemon=True)
        t.start()

    # Clear RAG index method
    def _clear_rag_index(self):
        """Clear the entire RAG index."""
        if not self.rag_system:
            QMessageBox.warning(self, "RAG Unavailable", "RAG system not initialized.")
            return
        
        reply = QMessageBox.question(
            self,
            "Clear RAG Index",
            "This will remove all indexed files from the RAG system.\n\n"
            "Are you sure you want to continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                self.rag_system.clear_index()
                QMessageBox.information(
                    self, 
                    "Success", 
                    "RAG index cleared successfully."
                )
                self.statusBar().showMessage("RAG index cleared", 3000)
            except Exception as e:
                QMessageBox.critical(
                    self, 
                    "Error", 
                    f"Failed to clear RAG index: {e}"
                )
    
    # Show RAG statistics method
    def _show_rag_stats(self):
        """Display RAG system statistics."""
        if not self.rag_system:
            QMessageBox.warning(self, "RAG Unavailable", "RAG system not initialized.")
            return
        
        try:
            stats = self.rag_system.get_stats()
            
            message = f"""RAG System Statistics

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
            
            QMessageBox.information(self, "RAG Statistics", message)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to get RAG stats: {e}")

    # --- CIN (Context-Injection System) methods ---
    def _upload_cin_file(self):
        """Upload a file for CIN context injection."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Upload File for CIN", "", "Allowed Files (*.txt *.pdf);;Text Files (*.txt);;PDF Files (*.pdf);;All Files (*)"
        )
        if not path:
            return

        # Check file size (50kB limit)
        file_size_kb = os.path.getsize(path) / 1024
        if file_size_kb > 50:
            QMessageBox.warning(
                self, "File Too Large", 
                f"CIN is limited to files smaller than 50kB. Selected file is {file_size_kb:.1f}kB.\n"
                "Please use RAG for larger files."
            )
            return

        self.statusBar().showMessage(f"Injecting {os.path.basename(path)} via CIN...", 0)

        try:
            content = ""
            ext = os.path.splitext(path)[1].lower()
            
            if ext == ".txt":
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            elif ext == ".pdf":
                # Use pdftotext to extract content
                import subprocess
                result = subprocess.run(['pdftotext', path, '-'], capture_output=True, text=True)
                if result.returncode == 0:
                    content = result.stdout
                else:
                    raise Exception(f"pdftotext failed with exit code {result.returncode}: {result.stderr}")
            else:
                # Fallback for other text-based files if user forces it
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

            if content:
                self.chat_manager.cin_context = content
                self.statusBar().showMessage(f"✓ Injected {os.path.basename(path)} via CIN", 3000)
                QMessageBox.information(
                    self, "CIN Success", 
                    f"File '{os.path.basename(path)}' has been injected into the assistant's context.\n"
                    "Sammy AI will now consider this content in your conversation."
                )
            else:
                self.statusBar().showMessage("✗ Failed to extract content for CIN", 3000)
                QMessageBox.warning(self, "CIN Error", "Could not extract any text from the selected file.")

        except Exception as e:
            self.statusBar().showMessage(f"✗ CIN error: {str(e)}", 5000)
            QMessageBox.critical(self, "CIN Error", f"An error occurred during CIN injection: {str(e)}")

    def _clear_cin_context(self):
        """Clear the current CIN context."""
        self.chat_manager.cin_context = None
        self.statusBar().showMessage("CIN context cleared", 3000)
        QMessageBox.information(self, "CIN Cleared", "The injected CIN context has been cleared.")

    # --- DBE (Diff-Based Editing) methods ---
    def _compare_with_file(self):
        """Compare current text with another file using diff viewer."""
        # Get current text
        current_text = self.editor.toPlainText()
        
        if not current_text:
            QMessageBox.warning(self, "No Content", "Current editor is empty.")
            return
        
        # Select file to compare
        path, _ = QFileDialog.getOpenFileName(
            self, "Select File to Compare", "", 
            "Text Files (*.txt);;All Files (*)"
        )
        
        if not path:
            return
        
        try:
            # Read the file
            with open(path, 'r', encoding='utf-8') as f:
                other_text = f.read()
            
            # Create diff dialog
            dialog = self._create_diff_dialog()
            
            current_name = self.current_file if self.current_file else "current"
            dialog.diff_viewer.load_diff(current_text, other_text, current_name, path)
            
            # If user applies the diff, update the editor
            if dialog.exec() == QDialog.Accepted:
                modified_text = dialog.diff_viewer.get_modified_text()
                if modified_text:
                    self.editor.setPlainText(modified_text)
                    self.statusBar().showMessage("Diff applied successfully", 3000)
        
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
            if modified_text:
                self.editor.setPlainText(modified_text)
                self.statusBar().showMessage("Diff applied successfully", 3000)

    def _apply_diff_from_file(self):
        """Apply a diff file to current text."""
        # Get current text
        current_text = self.editor.toPlainText()
        
        if not current_text:
            QMessageBox.warning(self, "No Content", "Current editor is empty.")
            return
        
        # Select diff file
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Diff File", "", 
            "Diff Files (*.diff *.patch);;All Files (*)"
        )
        
        if not path:
            return
        
        try:
            # Read the diff file
            with open(path, 'r', encoding='utf-8') as f:
                diff_string = f.read()
            
            # Create diff dialog
            dialog = self._create_diff_dialog()
            dialog.diff_viewer.load_diff_from_string(diff_string, current_text)
            
            # If user applies the diff, update the editor
            if dialog.exec() == QDialog.Accepted:
                modified_text = dialog.diff_viewer.get_modified_text()
                if modified_text:
                    self.editor.setPlainText(modified_text)
                    self.statusBar().showMessage("Diff applied successfully", 3000)
        
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
        """Toggle DBE mode on/off."""
        self.dbe_enabled = self.toggle_dbe_action.isChecked()
        
        if self.dbe_enabled:
            self.statusBar().showMessage("🔧 DBE Mode ENABLED - LLM suggestions will show as diffs", 3000)
            if self.chat_panel:
                self.chat_panel.add_system_message("🔧 DBE Mode enabled. LLM suggestions will now appear as diffs for your review.")
        else:
            self.statusBar().showMessage("DBE Mode disabled - Normal chat mode", 3000)
            if self.chat_panel:
                self.chat_panel.add_system_message("DBE Mode disabled. Returning to normal chat mode.")
    
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


from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtCore import QRect, QSize


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
        ss = QApplication.instance().styleSheet() or ""
        m = re.search(r"QPlainTextEdit\s*\{[^}]*(?<!-)color\s*:\s*([^;]+);", ss)
        if m:
            try:
                return QColor(m.group(1).strip())
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

def load_stylesheet(app, path):
    with open(path, "r") as f:
        app.setStyleSheet(f.read())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    load_stylesheet(app, "dark_theme.qss")
    editor = TextEditor()
    editor.show()
    sys.exit(app.exec())
