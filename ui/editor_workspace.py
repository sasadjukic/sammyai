"""Tabbed multi-document editor workspace."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import QFileInfo, QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileIconProvider,
    QLabel,
    QStyle,
    QTabBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from sammyai_core.document_session import (
    DocumentSession,
    normalize_document_path,
)
from sammyai_core.resources import asset_path
from ui.code_editor import CodeEditor


class EditorWorkspace(QWidget):
    """Own open document sessions, their editors, and tab activation."""

    active_document_changed = Signal(object)
    modified_state_changed = Signal(str, bool)
    cursor_position_changed = Signal(str, int, int)
    text_changed = Signal(str)
    copy_available = Signal(bool)
    undo_available = Signal(bool)
    redo_available = Signal(bool)
    close_requested = Signal(str)

    def __init__(self, parent=None, *, create_initial_document: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("editorWorkspace")
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("editorTabs")
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.tabBar().setElideMode(Qt.ElideNone)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.tabs)

        self._sessions: dict[str, DocumentSession] = {}
        self._editors: dict[str, CodeEditor] = {}
        self._pages: dict[str, QWidget] = {}
        self._breadcrumbs: dict[str, QLabel] = {}
        self._path_to_session: dict[str, str] = {}
        self._untitled_counter = 0
        self._icon_provider = QFileIconProvider()

        self.tabs.currentChanged.connect(self._on_current_changed)
        self.tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        if create_initial_document:
            self.new_document()

    def active_session(self) -> DocumentSession | None:
        return self.session_at(self.tabs.currentIndex())

    def active_editor(self) -> CodeEditor | None:
        session = self.active_session()
        return self._editors.get(session.session_id) if session is not None else None

    def session(self, session_id: str) -> DocumentSession | None:
        return self._sessions.get(session_id)

    def editor_for_session(self, session_id: str) -> CodeEditor | None:
        return self._editors.get(session_id)

    def sessions(self) -> tuple[DocumentSession, ...]:
        return tuple(
            session
            for index in range(self.tabs.count())
            if (session := self.session_at(index)) is not None
        )

    def session_at(self, index: int) -> DocumentSession | None:
        if index < 0:
            return None
        page = self.tabs.widget(index)
        if page is None:
            return None
        session_id = page.property("documentSessionId")
        return self._sessions.get(str(session_id))

    def sessions_for_path(self, path: str | Path) -> tuple[DocumentSession, ...]:
        session_id = self._path_to_session.get(normalize_document_path(path))
        session = self._sessions.get(session_id) if session_id else None
        return (session,) if session is not None else ()

    def dirty_sessions(self) -> tuple[DocumentSession, ...]:
        return tuple(
            session
            for session in self.sessions()
            if self.is_modified(session.session_id)
        )

    def is_modified(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        editor = self._editors.get(session_id)
        return bool(
            session is not None
            and (
                session.is_modified
                or (editor is not None and editor.document().isModified())
            )
        )

    def new_document(self) -> DocumentSession:
        self._untitled_counter += 1
        session = DocumentSession.untitled(self._untitled_counter)
        self._add_session(session)
        return session

    def open_document(self, path: str | Path, content: str) -> DocumentSession:
        existing = self.sessions_for_path(path)
        if existing:
            self.activate_document(existing[0].session_id)
            return existing[0]
        session = DocumentSession.from_path(path, content)
        self._add_session(session)
        return session

    def activate_document(self, session_id: str) -> bool:
        page = self._pages.get(session_id)
        index = self.tabs.indexOf(page) if page is not None else -1
        if index < 0:
            return False
        self.tabs.setCurrentIndex(index)
        editor = self._editors[session_id]
        editor.setFocus()
        return True

    def assign_path(self, session_id: str, path: str | Path) -> None:
        session = self._require_session(session_id)
        normalized = normalize_document_path(path)
        owner = self._path_to_session.get(normalized)
        if owner is not None and owner != session_id:
            raise ValueError("That file is already open in another tab.")
        if session.normalized_path is not None:
            self._path_to_session.pop(session.normalized_path, None)
        session.assign_path(path)
        self._path_to_session[normalized] = session_id
        self._refresh_session_chrome(session_id)

    def mark_clean(self, session_id: str) -> None:
        session = self._require_session(session_id)
        editor = self._editors[session_id]
        session.mark_clean(editor.toPlainText())
        editor.document().setModified(False)
        self._refresh_session_chrome(session_id)
        self.modified_state_changed.emit(session_id, False)

    def reload_document(self, session_id: str, content: str) -> None:
        session = self._require_session(session_id)
        editor = self._editors[session_id]
        cursor_position = editor.textCursor().position()
        vertical_scroll = editor.verticalScrollBar().value()
        horizontal_scroll = editor.horizontalScrollBar().value()
        editor.setPlainText(content)
        session.update_content(content)
        session.mark_clean()
        cursor = editor.textCursor()
        cursor.setPosition(min(cursor_position, len(content)))
        editor.setTextCursor(cursor)
        editor.verticalScrollBar().setValue(vertical_scroll)
        editor.horizontalScrollBar().setValue(horizontal_scroll)
        editor.document().setModified(False)
        self._refresh_session_chrome(session_id)

    def close_document(
        self,
        session_id: str,
        *,
        ensure_document: bool = True,
    ) -> bool:
        session = self._sessions.get(session_id)
        page = self._pages.get(session_id)
        if session is None or page is None:
            return False
        index = self.tabs.indexOf(page)
        if session.normalized_path is not None:
            self._path_to_session.pop(session.normalized_path, None)
        self._sessions.pop(session_id, None)
        self._editors.pop(session_id, None)
        self._pages.pop(session_id, None)
        self._breadcrumbs.pop(session_id, None)
        self.tabs.removeTab(index)
        page.deleteLater()
        if ensure_document and not self._sessions:
            self.new_document()
        return True

    def close_documents(
        self,
        session_ids: Iterable[str],
        *,
        ensure_document: bool = True,
    ) -> None:
        for session_id in tuple(session_ids):
            self.close_document(session_id, ensure_document=False)
        if ensure_document and not self._sessions:
            self.new_document()

    def _add_session(self, session: DocumentSession) -> None:
        editor = CodeEditor(self)
        editor.setPlainText(session.content)
        editor.document().setModified(False)

        breadcrumb = QLabel(self)
        breadcrumb.setObjectName("editorBreadcrumb")
        breadcrumb.setTextInteractionFlags(Qt.TextSelectableByMouse)
        page = QWidget(self.tabs)
        page.setProperty("documentSessionId", session.session_id)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        page_layout.addWidget(breadcrumb)
        page_layout.addWidget(editor)

        self._sessions[session.session_id] = session
        self._editors[session.session_id] = editor
        self._pages[session.session_id] = page
        self._breadcrumbs[session.session_id] = breadcrumb
        if session.normalized_path is not None:
            self._path_to_session[session.normalized_path] = session.session_id

        editor.textChanged.connect(
            lambda session_id=session.session_id: self._on_editor_text_changed(
                session_id
            )
        )
        editor.cursorPositionChanged.connect(
            lambda session_id=session.session_id: self._on_cursor_changed(session_id)
        )
        editor.copyAvailable.connect(
            lambda available, session_id=session.session_id: self._forward_if_active(
                session_id,
                self.copy_available,
                available,
            )
        )
        editor.document().undoAvailable.connect(
            lambda available, session_id=session.session_id: self._forward_if_active(
                session_id,
                self.undo_available,
                available,
            )
        )
        editor.document().redoAvailable.connect(
            lambda available, session_id=session.session_id: self._forward_if_active(
                session_id,
                self.redo_available,
                available,
            )
        )
        editor.document().modificationChanged.connect(
            lambda modified, session_id=session.session_id: self._on_qt_modified(
                session_id,
                modified,
            )
        )
        editor.verticalScrollBar().valueChanged.connect(
            lambda value, session_id=session.session_id: self._set_scroll(
                session_id,
                vertical=value,
            )
        )
        editor.horizontalScrollBar().valueChanged.connect(
            lambda value, session_id=session.session_id: self._set_scroll(
                session_id,
                horizontal=value,
            )
        )

        index = self.tabs.addTab(page, self._icon_for(session), session.display_name)
        close_button = QToolButton(self.tabs.tabBar())
        close_button.setObjectName("editorTabCloseButton")
        close_button.setIcon(QIcon(str(asset_path("icons", "close.svg"))))
        close_button.setIconSize(QSize(12, 12))
        close_button.setToolTip(f"Close {session.display_name}")
        close_button.setAccessibleName(f"Close {session.display_name}")
        close_button.setFixedSize(20, 20)
        close_button.clicked.connect(
            lambda _checked=False, session_id=session.session_id: (
                self.close_requested.emit(session_id)
            )
        )
        self.tabs.tabBar().setTabButton(index, QTabBar.RightSide, close_button)
        self._refresh_session_chrome(session.session_id)
        self.tabs.setCurrentIndex(index)

    def _require_session(self, session_id: str) -> DocumentSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Unknown document session: {session_id}")
        return session

    def _on_current_changed(self, _index: int) -> None:
        session = self.active_session()
        self.active_document_changed.emit(session)
        editor = self.active_editor()
        if session is None or editor is None:
            self.copy_available.emit(False)
            self.undo_available.emit(False)
            self.redo_available.emit(False)
            return
        self.copy_available.emit(editor.textCursor().hasSelection())
        self.undo_available.emit(editor.document().isUndoAvailable())
        self.redo_available.emit(editor.document().isRedoAvailable())
        self._on_cursor_changed(session.session_id)

    def _on_tab_close_requested(self, index: int) -> None:
        session = self.session_at(index)
        if session is not None:
            self.close_requested.emit(session.session_id)

    def _on_editor_text_changed(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        editor = self._editors.get(session_id)
        if session is None or editor is None:
            return
        was_modified = session.is_modified
        session.update_content(editor.toPlainText())
        is_modified = session.is_modified
        editor.document().setModified(is_modified)
        if was_modified != is_modified:
            self._refresh_session_chrome(session_id)
            self.modified_state_changed.emit(session_id, is_modified)
        if self.active_session() is session:
            self.text_changed.emit(session_id)

    def _on_qt_modified(self, session_id: str, modified: bool) -> None:
        if session_id not in self._sessions:
            return
        self._refresh_session_chrome(session_id)
        self.modified_state_changed.emit(session_id, modified)

    def _on_cursor_changed(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        editor = self._editors.get(session_id)
        if session is None or editor is None:
            return
        cursor = editor.textCursor()
        session.cursor_position = cursor.position()
        if self.active_session() is session:
            self.cursor_position_changed.emit(
                session_id,
                cursor.blockNumber() + 1,
                cursor.positionInBlock() + 1,
            )

    def _set_scroll(
        self,
        session_id: str,
        *,
        vertical: int | None = None,
        horizontal: int | None = None,
    ) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        if vertical is not None:
            session.vertical_scroll = vertical
        if horizontal is not None:
            session.horizontal_scroll = horizontal

    def _forward_if_active(self, session_id: str, signal, value: bool) -> None:
        session = self.active_session()
        if session is not None and session.session_id == session_id:
            signal.emit(value)

    def _refresh_session_chrome(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        page = self._pages.get(session_id)
        if session is None or page is None:
            return
        index = self.tabs.indexOf(page)
        if index < 0:
            return
        dirty_marker = " ●" if self.is_modified(session_id) else ""
        self.tabs.setTabText(index, f"{session.display_name}{dirty_marker}")
        self.tabs.setTabToolTip(
            index,
            str(session.path) if session.path is not None else session.display_name,
        )
        self.tabs.setTabIcon(index, self._icon_for(session))
        close_button = self.tabs.tabBar().tabButton(index, QTabBar.RightSide)
        if close_button is not None:
            close_button.setToolTip(f"Close {session.display_name}")
            close_button.setAccessibleName(f"Close {session.display_name}")
        breadcrumb = self._breadcrumbs[session_id]
        if session.path is None:
            breadcrumb_text = session.display_name
        else:
            breadcrumb_text = " › ".join(session.path.parts)
        breadcrumb.setText(breadcrumb_text)
        breadcrumb.setToolTip(str(session.path or session.display_name))

    def _icon_for(self, session: DocumentSession) -> QIcon:
        if session.path is not None:
            icon = self._icon_provider.icon(QFileInfo(str(session.path)))
            if not icon.isNull():
                return icon
        application = QApplication.instance()
        style = application.style() if application is not None else None
        return style.standardIcon(QStyle.SP_FileIcon) if style is not None else QIcon()
