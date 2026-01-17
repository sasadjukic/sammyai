"""
Diff viewer widget for displaying and interacting with diffs.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QComboBox, QSplitter, QMessageBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCharFormat, QColor, QFont, QSyntaxHighlighter, QTextDocument

try:
    from editing.diff_manager import DiffManager, Diff, DiffFormat, DiffConflict
except ImportError:
    from diff_manager import DiffManager, Diff, DiffFormat, DiffConflict


class DiffSyntaxHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for diff text."""
    
    def __init__(self, parent: QTextDocument):
        super().__init__(parent)
        
        # Define formats for different line types
        self.addition_format = QTextCharFormat()
        self.addition_format.setBackground(QColor("#d4edda"))
        self.addition_format.setForeground(QColor("#155724"))
        
        self.deletion_format = QTextCharFormat()
        self.deletion_format.setBackground(QColor("#f8d7da"))
        self.deletion_format.setForeground(QColor("#721c24"))
        
        self.context_format = QTextCharFormat()
        self.context_format.setForeground(QColor("#6c757d"))
        
        self.header_format = QTextCharFormat()
        self.header_format.setForeground(QColor("#007bff"))
        self.header_format.setFontWeight(QFont.Bold)
        
        self.file_header_format = QTextCharFormat()
        self.file_header_format.setForeground(QColor("#6f42c1"))
        self.file_header_format.setFontWeight(QFont.Bold)
    
    def highlightBlock(self, text: str):
        """Apply syntax highlighting to a block of text."""
        if not text:
            return
        
        # File headers (---, +++)
        if text.startswith('---') or text.startswith('+++'):
            self.setFormat(0, len(text), self.file_header_format)
        # Hunk headers (@@)
        elif text.startswith('@@'):
            self.setFormat(0, len(text), self.header_format)
        # Additions (+)
        elif text.startswith('+'):
            self.setFormat(0, len(text), self.addition_format)
        # Deletions (-)
        elif text.startswith('-'):
            self.setFormat(0, len(text), self.deletion_format)
        # Context (space or no prefix)
        else:
            self.setFormat(0, len(text), self.context_format)


class DiffViewerWidget(QWidget):
    """Widget for viewing and interacting with diffs."""
    
    # Signals
    diff_applied = Signal()  # Emitted when diff is successfully applied
    diff_rejected = Signal()  # Emitted when diff application is rejected
    
    def __init__(self, parent=None, diff_manager=None):
        super().__init__(parent)
        self.diff_manager = diff_manager if diff_manager else DiffManager()
        self.current_diff = None
        self.original_text = ""
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        
        # Top controls
        controls_layout = QHBoxLayout()
        
        # View mode selector
        controls_layout.addWidget(QLabel("View Mode:"))
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems(["Unified", "Side-by-Side"])
        self.view_mode_combo.currentTextChanged.connect(self._on_view_mode_changed)
        controls_layout.addWidget(self.view_mode_combo)
        
        # Format selector
        controls_layout.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Unified", "Context", "NDiff"])
        controls_layout.addWidget(self.format_combo)
        
        controls_layout.addStretch()
        
        # Stats label
        self.stats_label = QLabel("No diff loaded")
        controls_layout.addWidget(self.stats_label)
        
        layout.addLayout(controls_layout)
        
        # Diff display area
        self.splitter = QSplitter(Qt.Horizontal)
        
        # Unified view (single pane)
        self.unified_view = QTextEdit()
        self.unified_view.setReadOnly(True)
        self.unified_view.setFont(QFont("Courier", 10))
        self.highlighter = DiffSyntaxHighlighter(self.unified_view.document())
        self.splitter.addWidget(self.unified_view)
        
        # Side-by-side view (two panes)
        self.left_view = QTextEdit()
        self.left_view.setReadOnly(True)
        self.left_view.setFont(QFont("Courier", 10))
        self.left_view.hide()
        
        self.right_view = QTextEdit()
        self.right_view.setReadOnly(True)
        self.right_view.setFont(QFont("Courier", 10))
        self.right_view.hide()
        
        self.splitter.addWidget(self.left_view)
        self.splitter.addWidget(self.right_view)
        
        layout.addWidget(self.splitter)
        
        # Bottom buttons
        button_layout = QHBoxLayout()
        
        self.apply_button = QPushButton("Apply Diff")
        self.apply_button.clicked.connect(self._on_apply_diff)
        self.apply_button.setEnabled(False)
        button_layout.addWidget(self.apply_button)
        
        self.reject_button = QPushButton("Reject")
        self.reject_button.clicked.connect(self._on_reject_diff)
        self.reject_button.setEnabled(False)
        button_layout.addWidget(self.reject_button)
        
        button_layout.addStretch()
        
        self.copy_button = QPushButton("Copy Diff")
        self.copy_button.clicked.connect(self._on_copy_diff)
        self.copy_button.setEnabled(False)
        button_layout.addWidget(self.copy_button)
        
        layout.addLayout(button_layout)
    
    def load_diff(self, original: str, modified: str, original_name: str = "original", modified_name: str = "modified"):
        """
        Load and display a diff between two texts.
        
        Args:
            original: Original text content
            modified: Modified text content
            original_name: Name/label for original text
            modified_name: Name/label for modified text
        """
        self.original_text = original
        
        # Get selected format
        format_map = {
            "Unified": DiffFormat.UNIFIED,
            "Context": DiffFormat.CONTEXT,
            "NDiff": DiffFormat.NDIFF
        }
        format = format_map.get(self.format_combo.currentText(), DiffFormat.UNIFIED)
        
        # Generate diff
        self.current_diff = self.diff_manager.generate_diff(
            original, modified,
            original_name, modified_name,
            format=format
        )
        
        # Update display
        self._update_display()
        
        # Update stats
        stats = self.diff_manager.get_diff_stats(self.current_diff)
        self.stats_label.setText(
            f"Hunks: {stats['hunks']} | "
            f"+{stats['additions']} -{stats['deletions']}"
        )
        
        # Enable buttons
        self.apply_button.setEnabled(True)
        self.reject_button.setEnabled(True)
        self.copy_button.setEnabled(True)
    
    def load_diff_from_string(self, diff_string: str, original_text: str = ""):
        """
        Load a diff from a string.
        
        Args:
            diff_string: String containing diff content
            original_text: Original text to apply diff to (optional)
        """
        self.original_text = original_text
        self.current_diff = self.diff_manager.parse_diff_string(diff_string)
        
        self._update_display()
        
        # Update stats
        stats = self.diff_manager.get_diff_stats(self.current_diff)
        self.stats_label.setText(
            f"Hunks: {stats['hunks']} | "
            f"+{stats['additions']} -{stats['deletions']}"
        )
        
        # Enable buttons
        self.apply_button.setEnabled(bool(original_text))
        self.reject_button.setEnabled(True)
        self.copy_button.setEnabled(True)
    
    def _update_display(self):
        """Update the diff display based on current view mode."""
        if not self.current_diff:
            return
        
        view_mode = self.view_mode_combo.currentText()
        
        if view_mode == "Unified":
            self._show_unified_view()
        else:
            self._show_side_by_side_view()
    
    def _show_unified_view(self):
        """Show unified diff view."""
        self.unified_view.show()
        self.left_view.hide()
        self.right_view.hide()
        
        # Display diff
        diff_text = str(self.current_diff)
        self.unified_view.setPlainText(diff_text)
    
    def _show_side_by_side_view(self):
        """Show side-by-side diff view."""
        self.unified_view.hide()
        self.left_view.show()
        self.right_view.show()
        
        # Extract original and modified content from diff
        original_lines = []
        modified_lines = []
        
        for hunk in self.current_diff.hunks:
            for line in hunk.lines:
                if line.startswith(' '):
                    # Context line
                    original_lines.append(line[1:])
                    modified_lines.append(line[1:])
                elif line.startswith('-'):
                    # Deleted line
                    original_lines.append(line[1:])
                elif line.startswith('+'):
                    # Added line
                    modified_lines.append(line[1:])
        
        self.left_view.setPlainText(''.join(original_lines))
        self.right_view.setPlainText(''.join(modified_lines))
    
    def _on_view_mode_changed(self, mode: str):
        """Handle view mode change."""
        self._update_display()
    
    def _on_apply_diff(self):
        """Apply the current diff."""
        if not self.current_diff or not self.original_text:
            QMessageBox.warning(
                self, "No Diff",
                "No diff loaded or no original text available."
            )
            return
        
        try:
            # Apply diff
            result = self.diff_manager.apply_diff(
                self.original_text,
                self.current_diff,
                strict=True
            )
            
            # Emit signal with result
            self.diff_applied.emit()
            
            QMessageBox.information(
                self, "Success",
                "Diff applied successfully!"
            )
            
        except DiffConflict as e:
            QMessageBox.critical(
                self, "Conflict",
                f"Cannot apply diff due to conflicts:\n\n{str(e)}"
            )
    
    def _on_reject_diff(self):
        """Reject the current diff."""
        self.diff_rejected.emit()
        self.clear()
    
    def _on_copy_diff(self):
        """Copy diff to clipboard."""
        if not self.current_diff:
            return
        
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(str(self.current_diff))
        
        self.stats_label.setText("Diff copied to clipboard!")
    
    def clear(self):
        """Clear the diff viewer."""
        self.current_diff = None
        self.original_text = ""
        self.unified_view.clear()
        self.left_view.clear()
        self.right_view.clear()
        self.stats_label.setText("No diff loaded")
        self.apply_button.setEnabled(False)
        self.reject_button.setEnabled(False)
        self.copy_button.setEnabled(False)
    
    def get_modified_text(self) -> str:
        """
        Get the modified text after applying the diff.
        
        Returns:
            Modified text, or empty string if diff cannot be applied
        """
        if not self.current_diff or not self.original_text:
            return ""
        
        try:
            return self.diff_manager.apply_diff(
                self.original_text,
                self.current_diff,
                strict=True
            )
        except DiffConflict:
            return ""
