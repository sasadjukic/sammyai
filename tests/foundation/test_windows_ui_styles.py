from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
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


def test_chat_redesign_uses_subtle_surface_separation_without_pink_borders():
    app, previous_stylesheet = _application_with_dark_theme()
    chat_panel = ChatPanel()

    try:
        chat_panel.resize(700, 850)
        chat_panel.show()
        app.processEvents()

        composer = chat_panel.composer.grab().toImage()
        assert composer.pixelColor(0, composer.height() // 2) == QColor("#454545")
        assert composer.pixelColor(
            composer.width() // 2,
            composer.height() // 2,
        ) == QColor("#333333")

        old_border = QColor("#e9a5a5")
        input_image = chat_panel.input_field.grab().toImage()
        assert input_image.pixelColor(0, input_image.height() // 2) != old_border

        chat_panel.add_user_message("A message with its own surface.")
        app.processEvents()
        message_image = chat_panel.chat_display.messages[0].grab().toImage()
        assert message_image.pixelColor(
            message_image.width() // 2,
            message_image.height() // 2,
        ) == QColor("#353232")
        transcript = chat_panel.chat_display.grab().toImage()
        assert transcript.pixelColor(
            transcript.width() // 2,
            transcript.height() - 4,
        ) == QColor("#2b2b2b")
    finally:
        chat_panel.close()
        app.setStyleSheet(previous_stylesheet)
        app.processEvents()
