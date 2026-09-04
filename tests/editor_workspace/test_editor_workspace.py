from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QTabBar

from ui.editor_workspace import EditorWorkspace


def _application():
    return QApplication.instance() or QApplication([])


def test_workspace_opens_multiple_files_and_focuses_duplicate(tmp_path):
    app = _application()
    first_path = tmp_path / "chapter-one.md"
    second_path = tmp_path / "notes.txt"
    workspace = EditorWorkspace(create_initial_document=False)

    try:
        first = workspace.open_document(first_path, "Chapter one")
        first_editor = workspace.active_editor()
        cursor = first_editor.textCursor()
        cursor.setPosition(5)
        first_editor.setTextCursor(cursor)

        second = workspace.open_document(second_path, "Notes")
        assert workspace.tabs.count() == 2
        assert workspace.active_session() is second

        reopened = workspace.open_document(first_path.parent / "." / first_path.name, "ignored")
        assert reopened is first
        assert workspace.tabs.count() == 2
        assert workspace.active_session() is first
        assert workspace.active_editor().toPlainText() == "Chapter one"
        assert workspace.active_editor().textCursor().position() == 5
    finally:
        workspace.close()
        app.processEvents()


def test_workspace_uses_unique_untitled_names_and_dirty_markers():
    app = _application()
    workspace = EditorWorkspace()

    try:
        first = workspace.active_session()
        second = workspace.new_document()
        assert first.display_name == "Untitled 1"
        assert second.display_name == "Untitled 2"

        editor = workspace.active_editor()
        editor.insertPlainText("Draft")
        assert second.is_modified
        assert workspace.tabs.tabText(workspace.tabs.currentIndex()).endswith(" ●")

        editor.undo()
        assert not second.is_modified
        assert workspace.tabs.tabText(workspace.tabs.currentIndex()) == "Untitled 2"
    finally:
        workspace.close()
        app.processEvents()


def test_workspace_reload_preserves_cursor_and_refreshes_clean_background(tmp_path):
    app = _application()
    workspace = EditorWorkspace(create_initial_document=False)

    try:
        session = workspace.open_document(tmp_path / "chapter.md", "Old content")
        editor = workspace.active_editor()
        cursor = QTextCursor(editor.document())
        cursor.setPosition(4)
        editor.setTextCursor(cursor)

        workspace.reload_document(session.session_id, "New external content")

        assert editor.toPlainText() == "New external content"
        assert editor.textCursor().position() == 4
        assert not session.is_modified
    finally:
        workspace.close()
        app.processEvents()


def test_tab_close_button_requests_close_without_discarding_content():
    app = _application()
    workspace = EditorWorkspace()
    requested = []
    workspace.close_requested.connect(requested.append)

    try:
        session = workspace.active_session()
        workspace.active_editor().insertPlainText("Unsaved")
        close_button = workspace.tabs.tabBar().tabButton(
            workspace.tabs.currentIndex(),
            QTabBar.RightSide,
        )
        close_button.click()

        assert requested == [session.session_id]
        assert workspace.session(session.session_id) is session
        assert workspace.active_editor().toPlainText() == "Unsaved"
    finally:
        workspace.close()
        app.processEvents()
