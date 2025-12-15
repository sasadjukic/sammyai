import sys
import re
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPlainTextEdit, QFileDialog, QMessageBox, QToolBar,
    QToolButton, QMenu, QWidget, QLabel, QStatusBar, QInputDialog, QLineEdit,
    QHBoxLayout, QPushButton, QVBoxLayout, QDockWidget
)
from PySide6.QtGui import QAction, QKeySequence, QIcon, QPainter, QColor, QFont, QTextFormat, QPalette, QTextCursor, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt, QRect, QSize, QTimer
import threading
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtWidgets import QApplication, QStyle, QTextEdit
from api_key_manager import APIKeyDialog, APIKeyManager

# LLM integration
from llm.client import LLMConfig
from llm.chat_manager import ChatManager, MessageRole

# Chat UI
from chat_panel import ChatPanel




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

        # --- Initialize LLM and chat manager ---
        # Chat sessions will be stored under the package's llm/chat_sessions folder (if present)
        try:
            sessions_dir = os.path.join(os.path.dirname(__file__), "llm", "chat_sessions")
            self.chat_manager = ChatManager(storage_dir=sessions_dir)
        except Exception:
            # Fall back to in-memory manager
            self.chat_manager = ChatManager()

        # Create default LLM client via LLMConfig; handle initialization errors gracefully
        try:
            self.llm_config = LLMConfig()
            self.llm_client = self.llm_config.create_client()
            self.statusBar().showMessage("LLM client initialized", 3000)
        except Exception as e:
            self.llm_client = None
            # Non-fatal; show status so user knows LLM features aren't ready
            self.statusBar().showMessage(f"LLM client not initialized: {e}")

        # Chat panel (created lazily when the agent button is pressed)
        self.chat_dock: QDockWidget | None = None
        self.chat_panel: ChatPanel | None = None


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

            self.chat_dock = QDockWidget("Sammy AI", self)
            self.chat_dock.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
            self.chat_dock.setWidget(self.chat_panel)
            self.addDockWidget(Qt.RightDockWidgetArea, self.chat_dock)
        except Exception as e:
            QMessageBox.critical(self, "Chat Panel Error", str(e))

    def _on_chat_message_sent(self, message: str):
        """Handle message sent from chat panel UI: store in session and query LLM in background."""
        if not message:
            return

        # Add user message to session
        try:
            self.chat_manager.add_message(MessageRole.USER, message)
        except Exception:
            pass

        # Immediately show user message in UI
        if self.chat_panel:
            self.chat_panel.add_user_message(message)

        # If LLM not available, inform the user
        if not self.llm_client:
            if self.chat_panel:
                self.chat_panel.add_system_message("LLM client not initialized. Configure API key or check environment.")
            return

        # Run LLM query in background thread to avoid blocking UI
        def worker():
            try:
                # Prepare messages for the LLM using the chat manager's active session
                msgs = self.chat_manager.get_messages_for_llm()
                # Call the synchronous chat API (blocking) in the thread
                reply = self.llm_client.chat(msgs)

                # Add assistant message to session
                try:
                    self.chat_manager.add_message(MessageRole.ASSISTANT, reply)
                except Exception:
                    pass

                # Append assistant message on main thread
                QTimer.singleShot(0, lambda: self.chat_panel.add_assistant_message(reply) if self.chat_panel else None)
            except Exception as e:
                QTimer.singleShot(0, lambda: self.chat_panel.add_system_message(f"LLM error: {e}") if self.chat_panel else None)

        t = threading.Thread(target=worker, daemon=True)
        t.start()


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
        dialog.exec()

    # --- File operations ---
    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open File", "", "Text Files (*.txt)")
        if path:
            try:
                with open(path, "r", encoding="utf-8") as file:
                    self.editor.setPlainText(file.read())
                self.current_file = path
                self.update_window_title()
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
        self.editor.clear()
        self.current_file = None
        self.untitled_count += 1
        self.update_window_title()

    def new_file(self):
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
        
        self.setWindowTitle(f"{doc_name} - My Modern Text Editor")


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
