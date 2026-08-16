from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from sammyai_core.resources import asset_path
from ui.chat_panel import (
    GENERIC_WELCOME_MESSAGES,
    AutoGrowingTextEdit,
    ChatPanel,
)


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


def test_welcome_message_varies_without_a_project_and_uses_project_name():
    app, previous_stylesheet = _styled_application()
    panel = ChatPanel()

    try:
        first_generic = panel.empty_title.full_text
        assert first_generic in GENERIC_WELCOME_MESSAGES

        panel._on_clear_clicked()
        second_generic = panel.empty_title.full_text
        assert second_generic in GENERIC_WELCOME_MESSAGES
        assert second_generic != first_generic

        panel.set_project_name("Ten Degrees of Sky")
        assert panel.empty_title.full_text == (
            "How can I help with Ten Degrees of Sky?"
        )

        panel._on_clear_clicked()
        assert panel.empty_title.full_text == (
            "How can I help with Ten Degrees of Sky?"
        )
    finally:
        panel.close()
        app.setStyleSheet(previous_stylesheet)
        app.processEvents()


def test_long_project_welcome_is_elided_to_one_line():
    app, previous_stylesheet = _styled_application()
    panel = ChatPanel()

    try:
        project_name = "A Very Long Project Name " * 12
        expected_welcome = f"How can I help with {project_name.strip()}?"
        panel.resize(500, 850)
        panel.set_project_name(project_name)
        panel.show()
        app.processEvents()

        assert panel.empty_title.full_text == expected_welcome
        assert panel.empty_title.accessibleName() == expected_welcome
        assert not panel.empty_title.wordWrap()
        assert panel.empty_title.text() != expected_welcome
        assert panel.empty_title.text().endswith("…")
        assert panel.empty_title.toolTip() == expected_welcome
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


def test_file_mentions_filter_active_project_text_files_and_insert_paths():
    app, previous_stylesheet = _styled_application()
    panel = ChatPanel()
    provider_calls = []

    def project_files():
        provider_calls.append(True)
        return (
            "draft/scene_one.md",
            "draft/scene two.md",
            "notes.txt",
            "source.pdf",
        )

    try:
        panel.resize(700, 850)
        panel.show()
        panel.set_project_file_provider(project_files)
        panel.input_field.setFocus()
        QTest.keyClicks(panel.input_field, "Rewrite @s")
        app.processEvents()

        assert provider_calls == [True]
        assert panel.input_field._file_completion_model.stringList() == [
            "draft/scene two.md",
            "draft/scene_one.md",
        ]

        QTest.keyClick(panel.input_field, Qt.Key_Return)
        app.processEvents()

        assert panel.input_field.toPlainText() == 'Rewrite @"draft/scene two.md"'
    finally:
        panel.close()
        app.setStyleSheet(previous_stylesheet)
        app.processEvents()


def test_accepting_file_completion_does_not_send_the_message():
    app, previous_stylesheet = _styled_application()
    panel = ChatPanel()
    sent_messages = []
    panel.message_sent.connect(sent_messages.append)

    try:
        panel.resize(700, 850)
        panel.show()
        panel.set_project_file_provider(lambda: ("scene.md",))
        panel.input_field.setFocus()
        QTest.keyClicks(panel.input_field, "Edit @s")
        app.processEvents()

        assert panel.input_field.has_visible_file_completions()
        QTest.keyClick(panel.input_field, Qt.Key_Return)
        app.processEvents()

        assert panel.input_field.toPlainText() == "Edit @scene.md"
        assert sent_messages == []
    finally:
        panel.close()
        app.setStyleSheet(previous_stylesheet)
        app.processEvents()
