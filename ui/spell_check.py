"""Debounced background spelling shared by editor tabs and the composer."""
from concurrent.futures import Future
from threading import Event

from PySide6.QtCore import QEvent, QObject, QTimer, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QMenu, QMessageBox, QTextEdit

from sammyai_core.spelling import SpellCheckService
from sammyai_core.tasks import BackgroundTaskRunner
from ui.editor_decorations import EditorDecorationManager


class SpellCheckHub(QObject):
    changed = Signal()

    def __init__(self, config_dir, parent=None, *, service=None):
        super().__init__(parent)
        self.service = service or SpellCheckService(config_dir)
        self.runner = BackgroundTaskRunner()

    def submit(self, function, *args):
        future = Future()
        def run():
            try:
                future.set_result(function(*args))
            except Exception as error:
                future.set_exception(error)
        self.runner.submit(run, name='spell-check')
        return future

    def change(self, operation, *args):
        getattr(self.service, operation)(*args)
        self.changed.emit()


class SpellCheckController(QObject):
    def __init__(self, editor, hub):
        super().__init__(editor)
        self.editor = editor
        self.hub = hub
        if not hasattr(editor, 'decorations'):
            editor.decorations = EditorDecorationManager(editor)
        editor.spell_check = self
        self.matches = []
        self.ignored_once = []  # Live cursors track occurrences through preceding edits.
        self.future = None
        self.cancelled = Event()
        self.revision = 0
        self.scan_revision = -1
        self.error = None
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(300)
        self.debounce.timeout.connect(self.start_scan)
        self.poll = QTimer(self)
        self.poll.setInterval(40)
        self.poll.timeout.connect(self.finish_scan)
        editor.textChanged.connect(self.invalidate)
        hub.changed.connect(self.invalidate)
        editor.verticalScrollBar().valueChanged.connect(self.render)
        editor.viewport().installEventFilter(self)
        self._cancellation = [self.cancelled]
        cancellation = self._cancellation
        self.destroyed.connect(lambda: cancellation[0].set())
        self.invalidate()

    def invalidate(self):
        self.revision += 1
        self.cancelled.set()
        self.matches = []
        self.editor.decorations.set('spell', [])
        self.debounce.stop()
        if self.hub.service.enabled:
            self.debounce.start()

    def start_scan(self):
        if self.future is not None:
            self.debounce.start()
            return
        if not self.hub.service.enabled:
            return
        self.cancelled = Event()
        self._cancellation[0] = self.cancelled
        self.scan_revision = self.revision
        self.future = self.hub.submit(self.hub.service.scan, self.editor.toPlainText(), self.cancelled)
        self.poll.start()

    def finish_scan(self):
        if self.future is None or not self.future.done():
            return
        self.poll.stop()
        future, self.future = self.future, None
        try:
            matches = future.result()
            self.error = None
        except Exception as error:
            self.error = str(error)
            return
        if self.scan_revision != self.revision or not self.hub.service.enabled:
            return
        self.ignored_once = [(cursor, word) for cursor, word in self.ignored_once if cursor.selectedText() == word]
        ignored = {(c.selectionStart(), c.selectionEnd(), w) for c, w in self.ignored_once}
        self.matches = [m for m in matches if (m.start, m.end, m.word) not in ignored]
        self.render()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Resize:
            QTimer.singleShot(0, self.render)
        return False

    def render(self):
        # Only materialize decorations in the viewport, even for very long chapters.
        rect = self.editor.viewport().rect()
        start = self.editor.cursorForPosition(rect.topLeft()).block().position()
        last = self.editor.cursorForPosition(rect.bottomRight()).block()
        end = last.position() + last.length()
        selections = []
        for match in self.matches:
            if match.end <= start or match.start >= end:
                continue
            selection = QTextEdit.ExtraSelection()
            selection.cursor = self.cursor_for(match)
            selection.format.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)
            selection.format.setUnderlineColor(QColor('#e9a5a5'))
            selections.append(selection)
        self.editor.decorations.set('spell', selections)

    def cursor_for(self, match):
        cursor = QTextCursor(self.editor.document())
        cursor.setPosition(match.start)
        cursor.setPosition(match.end, QTextCursor.KeepAnchor)
        return cursor

    def replace(self, match, replacement, revision):
        if revision != self.revision or self.editor.isReadOnly():
            return
        cursor = self.cursor_for(match)
        if cursor.selectedText() != match.word:
            return
        cursor.beginEditBlock()
        cursor.insertText(replacement)
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)

    def ignore_once(self, match):
        self.ignored_once.append((self.cursor_for(match), match.word))
        self.invalidate()

    def change_dictionary(self, operation, word):
        try:
            self.hub.change(operation, word)
        except OSError as error:
            QMessageBox.warning(self.editor, 'Spelling', f'Could not save your dictionary: {error}')

    def create_context_menu(self, position):
        menu = self.editor.createStandardContextMenu()
        match = next((m for m in self.matches if m.start <= position < m.end), None)
        if self.hub.service.enabled and self.error:
            menu.addSeparator()
            menu.addAction('Spell check unavailable: ' + self.error).setEnabled(False)
        if match and not self.editor.isReadOnly():
            revision = self.revision
            menu.addSeparator()
            submenu = QMenu('Spelling — English (United States)', menu)
            menu.addMenu(submenu)
            menu.spelling_menu = submenu
            loading = submenu.addAction('Finding suggestions…')
            loading.setEnabled(False)
            future = self.hub.submit(self.hub.service.suggestions, match.word)
            timer = QTimer(menu)
            timer.setInterval(40)
            def populate():
                if not future.done():
                    return
                timer.stop()
                submenu.removeAction(loading)
                try:
                    suggestions = future.result()
                except Exception:
                    suggestions = []
                if not suggestions:
                    submenu.addAction('No suggestions').setEnabled(False)
                for word in suggestions:
                    action = submenu.addAction(word)
                    action.triggered.connect(lambda checked=False, word=word: self.replace(match, word, revision))
            timer.timeout.connect(populate)
            timer.start()
            menu.addAction('Ignore Once', lambda: self.ignore_once(match) if revision == self.revision else None)
            menu.addAction('Ignore All', lambda: self.change_dictionary('ignore_all', match.word))
            menu.addAction('Add to Dictionary', lambda: self.change_dictionary('add_word', match.word))
        return menu

    def context_menu(self, event):
        position = self.editor.cursorForPosition(event.pos()).position()
        menu = self.create_context_menu(position)
        menu.exec(event.globalPos())
        menu.deleteLater()
