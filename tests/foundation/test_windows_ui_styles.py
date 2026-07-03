from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QMainWindow,
    QPlainTextEdit,
)

from sammyai_core.resources import asset_path
from ui.chat_panel import ChatPanel


def _application_with_dark_theme():
    app = QApplication.instance() or QApplication([])
    previous_stylesheet = app.styleSheet()
    stylesheet = asset_path("ui", "styles", "dark_theme.qss")
    app.setStyleSheet(stylesheet.read_text(encoding="utf-8"))
    return app, previous_stylesheet


def test_primary_ui_fonts_use_valid_point_sizes():
    app, previous_stylesheet = _application_with_dark_theme()
    editor = QPlainTextEdit()
    chat_panel = ChatPanel()

    try:
        editor.show()
        chat_panel.resize(700, 850)
        chat_panel.show()
        app.processEvents()

        styled_widgets = (
            editor,
            chat_panel.text_label,
            chat_panel.status_label,
            chat_panel.clear_button,
        )
        for widget in styled_widgets:
            assert widget.font().pointSizeF() > 0
            assert widget.font().pixelSize() == -1
    finally:
        editor.close()
        chat_panel.close()
        app.setStyleSheet(previous_stylesheet)
        app.processEvents()


def test_chat_fields_and_dock_title_render_explicit_borders_and_background():
    app, previous_stylesheet = _application_with_dark_theme()
    window = QMainWindow()
    window.setCentralWidget(QPlainTextEdit())
    chat_panel = ChatPanel()
    dock = QDockWidget(window)
    dock.setWidget(chat_panel)
    window.addDockWidget(Qt.RightDockWidgetArea, dock)

    try:
        window.resize(1200, 850)
        window.show()
        app.processEvents()

        expected_border = QColor("#e9a5a5")
        for field in (chat_panel.chat_display, chat_panel.input_field):
            image = field.grab().toImage()
            assert image.pixelColor(0, image.height() // 2) == expected_border
            assert image.pixelColor(1, image.height() // 2) == expected_border

        dock_image = dock.grab().toImage()
        assert dock_image.pixelColor(dock_image.width() // 2, 1) == QColor("#252526")
    finally:
        window.close()
        app.setStyleSheet(previous_stylesheet)
        app.processEvents()
