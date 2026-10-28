"""Story selection workflows, using the real workspace and offline model replies."""

import json
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QTextCursor

from test_inline_review import review_window
from sammyai_core.selection_actions import SelectionAction


def test_standard_text_menus_preserve_clipboard_actions(review_window):
    window, _ = review_window
    window._create_chat_panel()
    for editor in (window.editor, window.chat_panel.input_field):
        editor.setPlainText("Original passage")
        editor.selectAll()
        menu = editor.createStandardContextMenu()
        labels = [action.text().replace("&", "") for action in menu.actions()]
        assert all(any(name in label for label in labels) for name in ("Cut", "Copy", "Paste", "Select All"))
        assert editor.toPlainText() == "Original passage"
        menu.deleteLater()


def test_composer_keeps_typed_text_separate_from_editor(review_window):
    window, _ = review_window
    window._create_chat_panel()
    window.editor.setPlainText("A quiet garden.")
    window.editor.selectAll()
    window.chat_panel.input_field.setPlainText("Make this more vivid.")
    assert window.chat_panel.input_field.toPlainText() == "Make this more vivid."
    assert window.editor.toPlainText() == "A quiet garden."


def select(editor, start, end):
    text = editor.toPlainText()
    cursor = editor.textCursor()
    cursor.setPosition(len(text[:start].encode("utf-16-le")) // 2)
    cursor.setPosition(len(text[:end].encode("utf-16-le")) // 2, QTextCursor.KeepAnchor)
    editor.setTextCursor(cursor)


def prepare(window, monkeypatch, reply, *, text="Before.\nOld passage.\nAfter.", deferred=False):
    window._show_chat_panel()
    window.editor.setPlainText(text)
    select(window.editor, text.index("Old"), text.index("Old") + len("Old passage."))
    calls, workers = [], []
    window.llm_client = SimpleNamespace(system_prompt="original", chat=lambda msgs: calls.extend(msgs) or reply)
    monkeypatch.setattr(window.task_runner, "submit", lambda fn, **kw: workers.append(fn) if deferred else fn())
    snapshot = window.selection_actions.capture(window.editor_workspace.active_session().session_id)
    return snapshot, calls, workers


def test_surface_menus_and_enablement(review_window):
    window, _ = review_window
    window._show_chat_panel()
    registry = window.editor_workspace.context_menus
    for selected in (False, True):
        window.editor.setPlainText("A passage")
        if selected:
            window.editor.selectAll()
        menu = registry.create(window.editor, "editor", 0)
        actions = {a.data(): a for a in menu.actions() if a.data()}
        assert set(actions) == {a.value for a in SelectionAction if a != SelectionAction.CUSTOM}
        assert actions["continue"].isEnabled()
        assert actions["rewrite"].isEnabled() == selected
        assert actions["critique"].isEnabled() == selected
        assert any("Copy" in a.text() for a in menu.actions())
        menu.deleteLater()
    menu = registry.create(window.chat_panel.input_field, "composer", 0)
    assert not any(a.data() == "rewrite" for a in menu.actions())
    menu.deleteLater()


def test_exact_unicode_selection_bounded_context_and_chip(review_window, monkeypatch):
    window, _ = review_window
    text = "😀" + "b" * 1700 + "\nOld passage.\n" + "a" * 1700
    snapshot, calls, _ = prepare(window, monkeypatch, '{"kind":"critique","text":"Useful feedback"}', text=text)
    assert snapshot.selected_text == "Old passage."
    assert snapshot.label == "Untitled 1:2"
    assert window.chat_panel.selection_reference == snapshot
    window.chat_panel.input_field.setPlainText("Explain the mood")
    window.chat_panel._on_send_clicked()
    sent = json.loads(calls[0]["content"])
    assert sent["passage"]["selection"] == "Old passage."
    assert len(sent["passage"]["before"]) == len(sent["passage"]["after"]) == 1500
    assert window.editor.toPlainText() == text
    assert not window.review_controller.batches
    assert window.chat_manager.get_active_session().messages[-1].content == "Useful feedback"
    assert "Old passage." not in window.chat_manager.get_active_session().messages[-2].content
    assert window.llm_client.system_prompt == "original"


@pytest.mark.parametrize("action", [SelectionAction.REWRITE, SelectionAction.TIGHTEN, SelectionAction.EXPAND, SelectionAction.DIALOGUE, SelectionAction.TONE])
def test_mutations_require_review_and_undo(review_window, monkeypatch, action):
    window, _ = review_window
    snapshot, _, _ = prepare(window, monkeypatch, '{"kind":"replacement","text":"New passage."}')
    window.selection_actions.start(snapshot, action, "playful" if action == SelectionAction.TONE else "")
    assert window.editor.toPlainText() == snapshot.original
    batch = next(iter(window.review_controller.batches.values()))
    assert batch.request_id
    widget = window.editor_workspace.review_for_session(snapshot.document_id)
    assert not widget.apply_button.isEnabled()
    widget.accept_all_button.click()
    widget.apply_button.click()
    assert window.editor.toPlainText() == "Before.\nNew passage.\nAfter."
    window.editor.undo()
    assert window.editor.toPlainText() == snapshot.original
    window.editor.redo()
    assert window.editor.toPlainText() == "Before.\nNew passage.\nAfter."
    detail = window.trace_service.detail(batch.request_id)
    assert detail["request"]["outcome"] == "applied"


def test_continue_inserts_at_cursor_and_retains_suffix(review_window, monkeypatch):
    window, _ = review_window
    snapshot, _, _ = prepare(window, monkeypatch, '{"kind":"insertion","text":" And then…"}')
    select(window.editor, snapshot.end, snapshot.end)
    window.selection_actions.start_action(snapshot.document_id, SelectionAction.CONTINUE)
    batch = next(iter(window.review_controller.batches.values()))
    assert batch.reviews[0].change.after_content == "Before.\nOld passage. And then…\nAfter."


@pytest.mark.parametrize("mutation", ["edit", "undo", "close", "rename", "project", "disk"])
def test_stale_result_never_opens_review(review_window, monkeypatch, mutation):
    window, root = review_window
    snapshot, _, workers = prepare(window, monkeypatch, '{"kind":"replacement","text":"New"}', deferred=True)
    path = root / "chapter.md"
    if mutation == "disk":
        path.write_text(snapshot.original, encoding="utf-8")
        window.editor_workspace.assign_path(snapshot.document_id, path)
        snapshot = window.selection_actions.capture(snapshot.document_id)
    window.selection_actions.start(snapshot, SelectionAction.REWRITE)
    if mutation in {"edit", "undo"}:
        window.editor.insertPlainText("Changed")
        if mutation == "undo":
            window.editor.undo()
    elif mutation == "close":
        window.editor_workspace.close_document(snapshot.document_id)
    elif mutation == "rename":
        window.editor_workspace.assign_path(snapshot.document_id, path)
    elif mutation == "project":
        window.project_service.close_project()
    else:
        path.write_text("Changed externally", encoding="utf-8")
    workers.pop()()
    assert not window.review_controller.batches
    assert "stale" in window.chat_manager.get_active_session().messages[-1].content


def test_result_keeps_origin_document_and_conversation(review_window, monkeypatch):
    window, _ = review_window
    snapshot, _, workers = prepare(window, monkeypatch, '{"kind":"replacement","text":"New"}', deferred=True)
    origin = window.chat_manager.active_session_id
    window.selection_actions.start(snapshot, SelectionAction.REWRITE)
    other = window.editor_workspace.new_document()
    window.editor.setPlainText("Other document")
    second_chat = window.chat_manager.create_session("second-chat")
    window.chat_manager.set_active_session(second_chat.session_id)
    workers.pop()()
    batch = next(iter(window.review_controller.batches.values()))
    assert batch.reviews[0].target_document_id == snapshot.document_id
    assert batch.reviews[0].originating_session_id == origin
    assert window.editor_workspace.editor_for_session(other.session_id).toPlainText() == "Other document"
    assert not second_chat.messages


@pytest.mark.parametrize("reply", ["", "not JSON", '{"kind":"replacement","text":""}', '{"kind":"insertion","text":"x"}', '{"kind":"replacement","text":"a","extra":true}', '{"kind":"replacement","text":"a","text":"b"}'])
def test_invalid_results_leave_source_untouched(review_window, monkeypatch, reply):
    window, _ = review_window
    snapshot, _, _ = prepare(window, monkeypatch, reply)
    window.selection_actions.start(snapshot, SelectionAction.REWRITE)
    assert not window.review_controller.batches
    assert window.editor.toPlainText() == snapshot.original
    assert not window.chat_panel._history_busy
    assert window.trace_service.list_requests()[0]["outcome"] == "invalid_result"


def test_provider_error_and_truncation(review_window, monkeypatch):
    window, _ = review_window
    snapshot, _, _ = prepare(window, monkeypatch, '{"kind":"replacement","text":"New"}')
    window.llm_client.last_response_metadata = {"finish_reason": "length"}
    window.selection_actions.start(snapshot, SelectionAction.REWRITE)
    assert not window.review_controller.batches
    def fail(messages):
        raise RuntimeError("offline provider")
    window.llm_client.chat = fail
    window.selection_actions.start(snapshot, SelectionAction.REWRITE)
    assert not window.review_controller.batches
    assert window.editor.toPlainText() == snapshot.original
    assert window.llm_client.system_prompt == "original"
    assert "offline provider" in window.chat_manager.get_active_session().messages[-1].content


def test_cancellation_ignores_late_response(review_window, monkeypatch):
    window, _ = review_window
    snapshot, _, _ = prepare(window, monkeypatch, "")
    def complete(messages):
        window.selection_actions.cancel()
        return '{"kind":"replacement","text":"New"}'
    window.llm_client.chat = complete
    window.selection_actions.start(snapshot, SelectionAction.REWRITE)
    assert not window.review_controller.batches
    assert window.trace_service.list_requests()[0]["outcome"] == "canceled"
    assert not window.chat_panel._history_busy
    assert window.editor.toPlainText() == snapshot.original


def test_line_ranges_remove_chip_and_conversation_drafts(review_window, monkeypatch):
    window, _ = review_window
    snapshot, _, _ = prepare(window, monkeypatch, "")
    select(window.editor, 0, len("Before.\nOld passage.\n"))
    assert window.chat_panel.selection_reference.label == "Untitled 1:1–2"
    origin = window.chat_manager.active_session_id
    second = window.chat_manager.create_session("other")
    window.chat_panel.select_conversation(second.session_id)
    assert window.chat_panel.selection_reference is None
    window.chat_panel.select_conversation(origin)
    assert window.chat_panel.selection_reference.label == "Untitled 1:1–2"
    window.chat_panel.selection_remove.click()
    assert window.chat_panel.selection_reference is None


def test_critique_contract_cannot_create_edit(review_window, monkeypatch):
    window, _ = review_window
    snapshot, _, _ = prepare(window, monkeypatch, '{"kind":"replacement","text":"New"}')
    window.selection_actions.start(snapshot, SelectionAction.CRITIQUE)
    assert not window.review_controller.batches
    assert window.editor.toPlainText() == snapshot.original


def test_clean_file_selection_uses_atomic_review_and_history(review_window, monkeypatch):
    window, root = review_window
    snapshot, _, _ = prepare(window, monkeypatch, '{"kind":"replacement","text":"New passage."}')
    path = root / "chapter.md"
    path.write_bytes(snapshot.original.replace("\n", "\r\n").encode())
    window._open_file_path(path)
    select(window.editor, snapshot.start, snapshot.end)
    snapshot = window.selection_actions.capture(window.editor_workspace.active_session().session_id)
    window.selection_actions.start(snapshot, SelectionAction.REWRITE)
    batch = next(iter(window.review_controller.batches.values()))
    assert batch.change_set is not None
    widget = window.editor_workspace.review_for_session(snapshot.document_id)
    widget.accept_all_button.click()
    widget.apply_button.click()
    assert path.read_bytes() == b"Before.\r\nNew passage.\r\nAfter."
    window._undo_last_change_set()
    assert path.read_bytes() == snapshot.original.replace("\n", "\r\n").encode()
    window._redo_last_change_set()
    assert path.read_bytes() == b"Before.\r\nNew passage.\r\nAfter."


def test_explicit_attachment_survives_tab_switch(review_window, monkeypatch):
    window, _ = review_window
    snapshot, _, _ = prepare(window, monkeypatch, '{"kind":"critique","text":"Feedback"}')
    window.selection_actions.attach(snapshot.document_id)
    window.editor_workspace.new_document()
    window.editor.setPlainText("Other passage")
    window.editor.selectAll()
    assert window.chat_panel.selection_reference == snapshot
    window.chat_panel.input_field.setPlainText("Critique this")
    window.chat_panel._on_send_clicked()
    assert not window.review_controller.batches
    assert window.editor.toPlainText() == "Other passage"


def test_cancel_tone_dialog_does_not_send(review_window, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    window, _ = review_window
    snapshot, calls, _ = prepare(window, monkeypatch, "")
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("", False))
    window.selection_actions.start_action(snapshot.document_id, SelectionAction.TONE)
    assert not calls
    assert not window.selection_actions.pending


def test_deleted_origin_conversation_cannot_create_review(review_window, monkeypatch):
    window, _ = review_window
    snapshot, _, workers = prepare(window, monkeypatch, '{"kind":"replacement","text":"New"}', deferred=True)
    window.selection_actions.start(snapshot, SelectionAction.REWRITE)
    window.chat_manager.delete_session(window.chat_manager.active_session_id)
    workers.pop()()
    assert not window.review_controller.batches
    assert window.editor.toPlainText() == snapshot.original


def test_story_menu_keeps_spelling_suggestions(review_window):
    window, _ = review_window
    window.editor.setPlainText("mispeling")
    window.editor.selectAll()
    window.editor.spell_check.matches = window.spell_hub.service.scan("mispeling")
    menu = window.editor.context_menus.create(window.editor, "editor", 0)
    assert menu.spelling_menu
    assert any(a.data() == "rewrite" for a in menu.actions())
    assert any("Copy" in a.text() for a in menu.actions())
    menu.deleteLater()


def test_real_background_completion_routes_on_ui_thread(review_window, monkeypatch):
    from threading import Event, get_ident
    import time
    from PySide6.QtWidgets import QApplication
    from sammyai_core.tasks import BackgroundTaskRunner
    window, _ = review_window
    snapshot, _, _ = prepare(window, monkeypatch, "")
    runner = BackgroundTaskRunner()
    monkeypatch.setattr(window.task_runner, "submit", runner.submit)
    entered, release = Event(), Event()
    ui_thread, worker_threads = get_ident(), []
    def reply(messages):
        worker_threads.append(get_ident())
        entered.set()
        release.wait(5)
        return '{"kind":"replacement","text":"New passage."}'
    window.llm_client.chat = reply
    window.selection_actions.start(snapshot, SelectionAction.REWRITE)
    try:
        assert entered.wait(5)
        window.editor_workspace.new_document()
        release.set()
        deadline = time.monotonic() + 5
        while window.selection_actions.pending and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(.01)
        assert worker_threads[0] != ui_thread
        assert not window.selection_actions.pending
        assert window.editor_workspace.review_for_session(snapshot.document_id)
    finally:
        release.set()
        runner.shutdown(5)
