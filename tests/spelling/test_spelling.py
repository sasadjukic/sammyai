from threading import Event, get_ident
import time

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QTextEdit

from sammyai_core.spelling import SpellCheckService, SpyllsBackend
from ui.chat_panel import AutoGrowingTextEdit
from ui.editor_workspace import EditorWorkspace
from ui.spell_check import SpellCheckController, SpellCheckHub
from ui.app_settings import AppSettingsDialog


class Backend:
    def __init__(self):
        self.calls = []

    def lookup(self, word):
        self.calls.append((word, get_ident()))
        return word.lower() in {"hello", "world", "don't", "writer's", "well", "known"}

    def suggest(self, word):
        return iter(['hello', 'help'])


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def wait(app, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.01)
    assert predicate(), 'Timed out waiting for background spelling'


def test_exact_unicode_ranges_and_punctuation(tmp_path):
    service = SpellCheckService(tmp_path, Backend())
    text = "😀 hello don’t writer’s well-known.\nwrng wrng!"
    matches = service.scan(text)
    assert [m.word for m in matches] == ['wrng', 'wrng']
    encoded = text.encode('utf-16-le')
    assert all(encoded[m.start*2:m.end*2].decode('utf-16-le') == m.word for m in matches)
    assert matches[0].start == len(text[:text.index('wrng')].encode('utf-16-le')) // 2


def test_ignored_syntax_and_screenplay_tokens(tmp_path):
    service = SpellCheckService(tmp_path, Backend())
    text = r"https://wrng.example/a me@wrng.test C:\wrng\file.txt /wrng/file.md notes/wrng.md `wrng` 123 x42 INT EXT" + "\n```python\nwrng\n```\n~~~\nwrng\n~~~\nhello"
    assert service.scan(text) == []
    assert service.scan('`wrng\nwrng` hello') == []
    assert service.scan('UNCONFIGUREDTOKEN')[0].word == 'UNCONFIGUREDTOKEN'


def test_preferences_restart_and_scope(tmp_path):
    service = SpellCheckService(tmp_path, Backend())
    service.add_word('Zorblax')
    service.ignore_all('Flarm')
    service.set_enabled(False)
    reopened = SpellCheckService(tmp_path, Backend())
    assert not reopened.enabled
    assert reopened.known('zorblax')
    assert not reopened.known('Flarm')
    assert service.known('Flarm')


def test_corrupt_preferences_and_failed_save(tmp_path, monkeypatch):
    path = tmp_path / 'writing_preferences.json'
    path.write_text('{broken')
    service = SpellCheckService(tmp_path, Backend())
    assert service.enabled
    monkeypatch.setattr(service, '_save', lambda **kw: (_ for _ in ()).throw(OSError('denied')))
    with pytest.raises(OSError):
        service.set_enabled(False)
    assert service.enabled
    with pytest.raises(OSError):
        service.add_word('wrng')
    assert not service.known('wrng')


def test_offline_us_dictionary_and_ranked_suggestions(tmp_path):
    service = SpellCheckService(tmp_path)
    assert all(service.known(w) for w in ['color', 'center', 'theater', "don't", "writer's"])
    assert not service.known('colour')
    assert not service.known('mispeling')
    assert 'misspelling' in service.suggestions('mispeling')


def test_cached_words_and_cancellation(tmp_path):
    backend = Backend()
    service = SpellCheckService(tmp_path, backend)
    service.scan('hello wrng\n' * 10000)
    assert len(backend.calls) == 2
    service.scan('hello wrng\nhello world')
    assert len(backend.calls) == 3
    cancelled = Event()
    cancelled.set()
    assert service.scan('wrng', cancelled) == []


def test_all_tabs_composer_toggle_and_dictionary(app, tmp_path):
    hub = SpellCheckHub(tmp_path, service=SpellCheckService(tmp_path, Backend()))
    workspace = EditorWorkspace(spell_hub=hub)
    composer = AutoGrowingTextEdit()
    SpellCheckController(composer, hub)
    first = workspace.active_editor()
    workspace.new_document()
    second = workspace.active_editor()
    widgets = [first, second, composer]
    try:
        for widget in widgets:
            widget.setPlainText('wrng')
            widget.document().setModified(False)
        wait(app, lambda: all(w.spell_check.matches for w in widgets))
        assert all(not w.document().isModified() for w in widgets)
        hub.change('set_enabled', False)
        assert all(not w.extraSelections() for w in widgets)
        hub.change('set_enabled', True)
        wait(app, lambda: all(w.spell_check.matches for w in widgets))
        hub.change('add_word', 'wrng')
        wait(app, lambda: all(w.spell_check.future is None and not w.spell_check.debounce.isActive() for w in widgets))
        assert all(not w.spell_check.matches for w in widgets)
        assert SpellCheckService(tmp_path, Backend()).known('wrng')
    finally:
        workspace.deleteLater()
        composer.deleteLater()
        app.processEvents()


def test_correction_undo_ignore_once_and_search(app, tmp_path):
    hub = SpellCheckHub(tmp_path, service=SpellCheckService(tmp_path, Backend()))
    editor = AutoGrowingTextEdit()
    controller = SpellCheckController(editor, hub)
    try:
        editor.setPlainText('😀 wrng wrng')
        wait(app, lambda: len(controller.matches) == 2)
        highlight = QTextEdit.ExtraSelection()
        highlight.cursor = editor.textCursor()
        editor.decorations.set('search', [highlight])
        assert len(editor.extraSelections()) == 3
        first = controller.matches[0]
        controller.replace(first, 'hello', controller.revision)
        assert editor.toPlainText() == '😀 hello wrng'
        assert len(editor.extraSelections()) == 1
        editor.undo()
        assert editor.toPlainText() == '😀 wrng wrng'
        wait(app, lambda: len(controller.matches) == 2)
        controller.ignore_once(controller.matches[0])
        wait(app, lambda: len(controller.matches) == 1)
        assert controller.matches[0].start == 8
        cursor = editor.textCursor()
        cursor.setPosition(0)
        cursor.insertText('hello ')
        wait(app, lambda: len(controller.matches) == 1)
        assert controller.matches[0].start == 14
        hub.change('ignore_all', 'wrng')
        wait(app, lambda: controller.future is None and not controller.debounce.isActive())
        assert controller.matches == []
        assert len(editor.extraSelections()) == 1
    finally:
        editor.deleteLater()
        app.processEvents()


def test_slow_scan_stale_results_and_no_ui_dictionary_work(app, tmp_path):
    started, release = Event(), Event()
    backend = Backend()
    original = backend.lookup
    def lookup(word):
        started.set()
        release.wait(3)
        return original(word)
    backend.lookup = lookup
    hub = SpellCheckHub(tmp_path, service=SpellCheckService(tmp_path, backend))
    editor = AutoGrowingTextEdit()
    controller = SpellCheckController(editor, hub)
    try:
        editor.setPlainText('wrng ' * 10000)
        wait(app, started.is_set)
        old = controller.scan_revision
        editor.setPlainText('hello')
        hub.change('set_enabled', False)
        release.set()
        wait(app, lambda: controller.future is None)
        assert controller.revision != old
        assert controller.matches == []
        assert all(thread != get_ident() for _, thread in backend.calls)
        hub.change('set_enabled', True)
        wait(app, lambda: controller.future is None and not controller.debounce.isActive())
        assert controller.matches == []
    finally:
        release.set()
        editor.deleteLater()
        app.processEvents()


def test_settings_cancel_and_save(app, tmp_path):
    hub = SpellCheckHub(tmp_path, service=SpellCheckService(tmp_path, Backend()))
    dialog = AppSettingsDialog(hub, lambda: None)
    dialog.spell_check.setChecked(False)
    dialog.reject()
    assert hub.service.enabled
    dialog.save()
    assert not hub.service.enabled
    assert not SpellCheckService(tmp_path, Backend()).enabled


def test_stale_correction_does_not_change_other_text(app, tmp_path):
    hub = SpellCheckHub(tmp_path, service=SpellCheckService(tmp_path, Backend()))
    editor = AutoGrowingTextEdit()
    controller = SpellCheckController(editor, hub)
    editor.setPlainText('wrng')
    wait(app, lambda: bool(controller.matches))
    match, revision = controller.matches[0], controller.revision
    editor.setPlainText('world')
    controller.replace(match, 'hello', revision)
    assert editor.toPlainText() == 'world'
    editor.deleteLater()
    app.processEvents()


def test_context_menu_preserves_edit_actions_and_corrects(app, tmp_path):
    from PySide6.QtCore import QPoint
    hub = SpellCheckHub(tmp_path, service=SpellCheckService(tmp_path, Backend()))
    editor = AutoGrowingTextEdit()
    controller = SpellCheckController(editor, hub)
    editor.setPlainText('wrng')
    wait(app, lambda: bool(controller.matches))
    def execute(menu, point):
        names = [a.text().replace('&', '') for a in menu.actions()]
        assert any('Copy' in name for name in names)
        assert any('Paste' in name for name in names)
        assert 'Ignore Once' in names and 'Ignore All' in names and 'Add to Dictionary' in names
        submenu = next(a.menu() for a in menu.actions() if a.text().startswith('Spelling'))
        wait(app, lambda: any(a.text() == 'hello' for a in submenu.actions()))
        next(a for a in submenu.actions() if a.text() == 'hello').trigger()
    menu = controller.create_context_menu(1)
    execute(menu, QPoint(0, 0))
    menu.deleteLater()
    assert editor.toPlainText() == 'hello'
    editor.undo()
    assert editor.toPlainText() == 'wrng'
    editor.deleteLater()
    app.processEvents()


def test_long_document_renders_only_visible_underlines(app, tmp_path):
    from ui.code_editor import CodeEditor
    hub = SpellCheckHub(tmp_path, service=SpellCheckService(tmp_path, Backend()))
    editor = CodeEditor()
    editor.resize(400, 200)
    controller = SpellCheckController(editor, hub)
    editor.setPlainText('wrng\n' * 2000)
    editor.show()
    wait(app, lambda: len(controller.matches) == 2000)
    assert 0 < len(editor.extraSelections()) < 50
    editor.verticalScrollBar().setValue(editor.verticalScrollBar().maximum())
    controller.render()
    assert editor.extraSelections()[-1].cursor.selectionStart() > 9000
    editor.deleteLater()
    app.processEvents()
