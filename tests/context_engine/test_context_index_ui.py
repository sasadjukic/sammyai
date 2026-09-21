from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QPushButton

from rag.rag_system import RAGSystem
from sammyai_core.context_index import IndexedFileSummary
from ui.rag_management import ContextIndexDialog


class ReadOnlyIndex:
    def __init__(self):
        self.entries = (
            IndexedFileSummary("C:/novel/chapter.md", "one", 3),
            IndexedFileSummary("C:/other/chapter.md", "two", 2),
            IndexedFileSummary("C:/research/notes.txt", None, 5),
            IndexedFileSummary("", None, 1),
        )
        self.reads = 0
        self.fail = False

    def get_indexed_files(self):
        self.reads += 1
        if self.fail:
            raise RuntimeError("Store unavailable")
        return self.entries


def test_inspector_filters_preserved_legacy_entries_and_copies_source_path():
    app = QApplication.instance() or QApplication([])
    index = ReadOnlyIndex()
    original_entries = index.entries
    project = SimpleNamespace(id="one", name="Novel")
    service = SimpleNamespace(active_project=project, get_project=lambda key: project if key == "one" else None)
    dialog = ContextIndexDialog(index, service)
    try:
        assert dialog.file_list.topLevelItemCount() == 1
        assert dialog.file_list.topLevelItem(0).text(1) == "Novel"
        dialog.scope_combo.setCurrentIndex(dialog.scope_combo.findData("all"))
        assert dialog.file_list.topLevelItemCount() == 4
        dialog.scope_combo.setCurrentIndex(dialog.scope_combo.findData("legacy"))
        assert dialog.file_list.topLevelItemCount() == 2
        item = dialog.file_list.topLevelItem(0)
        dialog.file_list.setCurrentItem(item)
        assert "excluded from project-scoped retrieval" in dialog.details_label.text()
        dialog.copy_path_button.click()
        assert QApplication.clipboard().text() == "C:/research/notes.txt"
        dialog.file_list.setCurrentItem(dialog.file_list.topLevelItem(1))
        assert not dialog.copy_path_button.isEnabled()
        assert "not recorded" in dialog.details_label.text()
        dialog.refresh_button.click()
        assert index.reads == 2
        assert index.entries is original_entries
        assert {button.text() for button in dialog.findChildren(QPushButton)} == {"Refresh", "Copy Source Path", "Close"}
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_inspector_handles_no_project_empty_index_and_read_failure():
    app = QApplication.instance() or QApplication([])
    index = ReadOnlyIndex()
    index.entries = ()
    dialog = ContextIndexDialog(index)
    try:
        assert dialog.scope_combo.currentData() == "all"
        assert "No indexed files" in dialog.summary_label.text()
        index.fail = True
        dialog.refresh_button.click()
        assert "Unable to read" in dialog.summary_label.text()
        assert "Store unavailable" in dialog.details_label.text()
        index.fail = False
        dialog.refresh_button.click()
        assert "No indexed files" in dialog.summary_label.text()
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_rag_inventory_does_not_initialize_embeddings():
    rag = RAGSystem.__new__(RAGSystem)
    rag.vector_store = ReadOnlyIndex()
    assert rag.get_indexed_files() == rag.vector_store.entries
