"""Real themed tab geometry and navigation with more files than available width."""

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolButton

from ui.editor_workspace import EditorWorkspace
from sammyai_core.resources import asset_path


@pytest.fixture
def workspace(tmp_path):
    app = QApplication.instance() or QApplication([])
    previous_style, previous_font = app.styleSheet(), app.font()
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(asset_path("ui", "styles", "dark_theme.qss").read_text(encoding="utf-8"))
    workspace = EditorWorkspace()
    for name in (
        "shelf_life_bible.md", "shelf_life_scene_breakdowns.md", "shelf_life_draft.md",
        "shelf_life_outline.md", "shelf_life_character_notes.md", "notes & research.md",
        "a_very_long_filename_for_the_final_scene_and_alternate_ending.md", "revision_checklist.md",
    ):
        workspace.open_document(tmp_path / name, name)
    workspace.resize(640, 280)
    workspace.show()
    app.processEvents()
    yield workspace
    workspace.close()
    workspace.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.setStyleSheet(previous_style)
    app.setFont(previous_font)
    app.processEvents()


def scroll_buttons(workspace):
    bar = workspace.tabs.tabBar()
    return (bar.findChild(QToolButton, "ScrollLeftButton"), bar.findChild(QToolButton, "ScrollRightButton"))


def tabs_menu(workspace):
    button = workspace.tabs.cornerWidget(Qt.TopRightCorner)
    assert isinstance(button, QToolButton), "Every open file needs an accessible tab-list control"
    assert button.accessibleName() == "Open tabs"
    assert not button.icon().isNull()
    menu = button.menu()
    menu.aboutToShow.emit()
    return menu


def test_overflow_controls_have_visible_icons_and_usable_width(workspace):
    left, right = scroll_buttons(workspace)
    assert left.isVisible() and right.isVisible()
    for button in (left, right):
        assert button.width() >= 28
        assert not button.icon().isNull()
        assert button.accessibleName()
        assert button.contentsRect().width() >= button.iconSize().width()
    assert left.geometry().intersected(right.geometry()).width() <= 1
    assert workspace.tabs.cornerWidget(Qt.TopRightCorner).isVisible()


def test_long_tabs_keep_readable_bounded_width_and_full_path_tooltips(workspace):
    bar = workspace.tabs.tabBar()
    for index, session in enumerate(workspace.sessions()):
        assert 140 <= bar.tabRect(index).width() <= 280
        assert bar.tabToolTip(index) == str(session.path)
        close = bar.tabButton(index, bar.ButtonPosition.RightSide)
        assert close.size().width() == 20


def test_arrow_scrolling_does_not_change_active_document_or_buffer(workspace):
    session = workspace.sessions()[0]
    workspace.activate_document(session.session_id)
    editor = workspace.active_editor()
    editor.insertPlainText("Unsaved ")
    before_text, before_cursor = editor.toPlainText(), editor.textCursor().position()
    bar = workspace.tabs.tabBar()
    left, right = scroll_buttons(workspace)
    before_x = bar.tabRect(0).x()

    right.click()
    QApplication.processEvents()

    assert bar.tabRect(0).x() < before_x
    assert workspace.active_session() is session
    assert editor.toPlainText() == before_text
    assert editor.textCursor().position() == before_cursor
    assert workspace.is_modified(session.session_id)
    for _ in workspace.sessions():
        if not left.isEnabled():
            break
        left.click()
        QApplication.processEvents()
    assert bar.tabRect(0).x() == before_x


def test_open_tabs_menu_lists_full_names_and_selects_by_identity_after_reorder(workspace):
    active = workspace.active_session()
    workspace.active_editor().insertPlainText("Unsaved ")
    menu = tabs_menu(workspace)
    actions = menu.actions()
    assert len(actions) == len(workspace.sessions())
    for action, session in zip(actions, workspace.sessions()):
        assert session.display_name in action.text().replace("&&", "&")
        assert action.toolTip() == str(session.path)
        assert action.isChecked() == (session is active)
    assert "●" in actions[-1].text()
    first, action = workspace.sessions()[0], actions[0]
    workspace.tabs.tabBar().moveTab(0, len(actions) - 1)

    action.trigger()

    assert workspace.active_session() is first
    assert workspace.active_editor().toPlainText() == first.display_name
    bar = workspace.tabs.tabBar()
    rect = bar.tabRect(workspace.tabs.currentIndex())
    assert rect.left() >= 0
    assert rect.right() < scroll_buttons(workspace)[0].x()
    refreshed = tabs_menu(workspace).actions()
    assert refreshed[-1].isChecked()


def test_menu_does_not_reopen_closed_tab_and_close_button_keeps_identity(workspace):
    first = workspace.sessions()[0]
    action = tabs_menu(workspace).actions()[0]
    requested = []
    workspace.close_requested.connect(requested.append)
    bar = workspace.tabs.tabBar()
    bar.tabButton(0, bar.ButtonPosition.RightSide).click()
    assert requested == [first.session_id]
    assert workspace.session(first.session_id) is first
    workspace.close_document(first.session_id)
    remaining = workspace.sessions()

    action.trigger()

    assert workspace.sessions() == remaining
    assert len(tabs_menu(workspace).actions()) == len(remaining)


def test_narrowing_and_expanding_keeps_selected_tab_visible(workspace):
    session = workspace.sessions()[3]
    workspace.activate_document(session.session_id)
    for width in (380, 820, 440, 720):
        workspace.resize(width, 280)
        QApplication.processEvents()
        assert workspace.active_session() is session
        bar = workspace.tabs.tabBar()
        rect = bar.tabRect(workspace.tabs.currentIndex())
        assert rect.left() >= 0
        assert rect.right() < scroll_buttons(workspace)[0].x()
    bar.setFocus()
    QTest.keyClick(bar, Qt.Key_Right)
    assert workspace.active_session() is workspace.sessions()[4]


def test_scroll_arrows_hide_when_remaining_tabs_fit(workspace):
    workspace.close_documents([s.session_id for s in workspace.sessions()[2:]])
    workspace.resize(850, 280)
    QApplication.processEvents()
    assert all(not button.isVisible() for button in scroll_buttons(workspace))
    assert len(tabs_menu(workspace).actions()) == 2
