import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, 
    QListWidgetItem, QPushButton, QLabel, QMessageBox,
    QFrame
)
from PySide6.QtCore import Qt, Signal


class RAGFileManagementDialog(QDialog):
    """
    Dialog for managing indexed files in the RAG system.
    Allows users to view indexed files and selectively delete them.
    """
    
    def __init__(self, rag_system, parent=None):
        super().__init__(parent)
        self.rag_system = rag_system
        self.setWindowTitle("Manage RAG Index")
        self.setMinimumSize(500, 400)
        self.setup_ui()
        self.load_files()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Header
        header = QLabel("Indexed Files")
        header.setObjectName("ragHeader")
        layout.addWidget(header)
        
        # Description
        desc = QLabel("Select files to remove from the RAG index:")
        desc.setObjectName("ragDescription")
        layout.addWidget(desc)
        
        # List of files
        self.file_list = QListWidget()
        self.file_list.setObjectName("ragFileList")
        layout.addWidget(self.file_list)
        
        # Action buttons row
        btn_layout = QHBoxLayout()
        
        self.btn_remove = QPushButton("Remove Selected")
        self.btn_remove.setObjectName("ragBtnRemove")
        self.btn_remove.clicked.connect(self.remove_selected)
        
        self.btn_clear_all = QPushButton("Clear All")
        self.btn_clear_all.setObjectName("ragBtnClearAll")
        self.btn_clear_all.clicked.connect(self.clear_all_index)
        
        btn_layout.addWidget(self.btn_remove)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_clear_all)
        
        layout.addLayout(btn_layout)
        
        # Dialog buttons (Close)
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("ragBtnClose")
        self.btn_close.clicked.connect(self.accept)
        close_layout.addWidget(self.btn_close)
        
        layout.addLayout(close_layout)
        
        # Set overall dialog style
        self.setObjectName("ragDialog")

    def load_files(self):
        """Fetch indexed files from RAG system and populate the list."""
        self.file_list.clear()
        if not self.rag_system:
            return
            
        try:
            stats = self.rag_system.get_stats()
            files = stats.get('files', [])
            
            if not files:
                item = QListWidgetItem("No files indexed.")
                item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
                item.setForeground(Qt.gray)
                self.file_list.addItem(item)
                self.btn_remove.setEnabled(False)
                self.btn_clear_all.setEnabled(False)
                return

            for file_path in files:
                # Store full path in data role, display basename
                filename = os.path.basename(file_path)
                item = QListWidgetItem(filename)
                item.setData(Qt.UserRole, file_path)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                item.setToolTip(file_path)
                self.file_list.addItem(item)
            
            self.btn_remove.setEnabled(True)
            self.btn_clear_all.setEnabled(True)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load indexed files: {e}")

    def remove_selected(self):
        """Remove checked files from the RAG index."""
        selected_items = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.checkState() == Qt.Checked:
                selected_items.append(item)
        
        if not selected_items:
            QMessageBox.information(self, "No Selection", "Please check the files you want to remove.")
            return
            
        reply = QMessageBox.question(
            self, "Confirm Removal",
            f"Are you sure you want to remove {len(selected_items)} selected file(s) from the index?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                for item in selected_items:
                    file_path = item.data(Qt.UserRole)
                    self.rag_system.remove_file(file_path)
                
                QMessageBox.information(self, "Success", f"Successfully removed {len(selected_items)} file(s).")
                self.load_files()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to remove files: {e}")

    def clear_all_index(self):
        """Clear the entire RAG index after confirmation."""
        reply = QMessageBox.question(
            self, "Confirm Clear All",
            "This will remove ALL files from the RAG index. Are you sure?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                self.rag_system.clear_index()
                QMessageBox.information(self, "Success", "RAG index cleared successfully.")
                self.load_files()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clear RAG index: {e}")
