from PySide6.QtWidgets import QApplication

from sammyai_core.resources import asset_path
from ui.chat_panel import AutoGrowingTextEdit, ChatPanel


def _styled_application():
    app = QApplication.instance() or QApplication([])
    previous_stylesheet = app.styleSheet()
    stylesheet = asset_path("ui", "styles", "dark_theme.qss")
    app.setStyleSheet(stylesheet.read_text(encoding="utf-8"))
    return app, previous_stylesheet


def test_composer_moves_from_empty_state_to_active_conversation():
    app, previous_stylesheet = _styled_application()
    panel = ChatPanel()

    try:
        panel.resize(700, 850)
        panel.show()
        app.processEvents()

        initial_composer_top = panel.composer_host.geometry().top()
        assert panel.empty_state.isVisible()
        assert not panel.chat_display.isVisible()

        panel.add_user_message("Help me develop this scene.")
        app.processEvents()

        assert not panel.empty_state.isVisible()
        assert panel.chat_display.isVisible()
        assert panel.composer_host.geometry().top() > initial_composer_top
        assert panel.chat_display.geometry().bottom() < panel.composer_host.geometry().top()
        assert panel.chat_display.toPlainText() == (
            "You:\nHelp me develop this scene."
        )
    finally:
        panel.close()
        app.setStyleSheet(previous_stylesheet)
        app.processEvents()


def test_messages_have_individual_copy_actions_and_streaming_compatibility():
    app, previous_stylesheet = _styled_application()
    panel = ChatPanel()

    try:
        panel.add_user_message("Original question")
        panel.add_assistant_message("First")
        panel.append_to_last_message(" response")
        app.processEvents()

        user_message, assistant_message = panel.chat_display.messages
        assert user_message.copy_button is not None
        assert assistant_message.copy_button is not None
        assistant_message.copy_button.click()

        assert QApplication.clipboard().text() == "First response"
        assert panel.status_label.text() == "Message copied to clipboard"
        assert "Sammy:\nFirst response" in panel.chat_display.toPlainText()
        assert not hasattr(panel, "copy_button")
    finally:
        panel.close()
        app.setStyleSheet(previous_stylesheet)
        app.processEvents()


def test_new_chat_resets_the_panel_and_is_disabled_while_generating():
    app, previous_stylesheet = _styled_application()
    panel = ChatPanel()
    requests = []
    legacy_requests = []
    panel.new_chat_requested.connect(lambda: requests.append(True))
    panel.clear_chat_requested.connect(lambda: legacy_requests.append(True))

    try:
        panel.resize(700, 850)
        panel.show()
        app.processEvents()
        panel.add_user_message("Keep this in the previous session.")
        panel.set_thinking(True)
        assert not panel.new_chat_button.isEnabled()

        panel.new_chat_button.click()
        assert panel.chat_display.toPlainText().startswith("You:")

        panel.set_thinking(False)
        panel.new_chat_button.click()
        app.processEvents()

        assert panel.new_chat_button.isEnabled()
        assert panel.chat_display.toPlainText() == ""
        assert panel.empty_state.isVisible()
        assert requests == [True]
        assert legacy_requests == [True]
    finally:
        panel.close()
        app.setStyleSheet(previous_stylesheet)
        app.processEvents()


def test_composer_input_grows_and_keeps_a_bounded_height():
    app, previous_stylesheet = _styled_application()
    panel = ChatPanel()

    try:
        panel.resize(700, 850)
        panel.show()
        app.processEvents()
        initial_height = panel.input_field.height()

        panel.input_field.setPlainText("\n".join(f"Line {i}" for i in range(20)))
        app.processEvents()

        assert panel.input_field.height() > initial_height
        assert panel.input_field.height() == AutoGrowingTextEdit.MAXIMUM_HEIGHT
    finally:
        panel.close()
        app.setStyleSheet(previous_stylesheet)
        app.processEvents()


def test_model_selection_does_not_add_redundant_composer_status():
    app, previous_stylesheet = _styled_application()
    panel = ChatPanel()
    selected_models = []
    panel.model_selected.connect(selected_models.append)

    try:
        panel.set_status("")
        panel._on_model_changed("local-model")

        assert selected_models == ["local-model"]
        assert panel.status_label.text() == ""
    finally:
        panel.close()
        app.setStyleSheet(previous_stylesheet)
        app.processEvents()
