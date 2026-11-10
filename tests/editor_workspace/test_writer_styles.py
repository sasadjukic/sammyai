"""End-to-end profile selection, request ownership, review, and local editing."""

import json
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt

from test_inline_review import review_window
from test_selection_actions import prepare, select
from sammyai_core.agent_workflows import AgentType
from sammyai_core.style_profiles import StyleSelection
from sammyai_core.selection_actions import SelectionAction
from ui.style_profiles import StyleProfileEditor, StyleProfilesDialog


def activate(window):
    profile = window.style_service.repository.create("Personal voice", "PRIVATE_STYLE: use concrete details.", "PRIVATE_SAMPLE: The hinge clicked.")
    window.style_service.select(window._active_chat_project_id(), StyleSelection("profile", profile.id))
    return profile


@pytest.mark.parametrize("action,kind", [
    (SelectionAction.REWRITE, "replacement"), (SelectionAction.TIGHTEN, "replacement"),
    (SelectionAction.EXPAND, "replacement"), (SelectionAction.DIALOGUE, "replacement"),
    (SelectionAction.TONE, "replacement"), (SelectionAction.CONTINUE, "insertion"),
    (SelectionAction.CRITIQUE, "critique"), (SelectionAction.CUSTOM, "replacement"),
    (SelectionAction.CUSTOM, "critique"),
])
def test_all_story_actions_use_captured_style_and_preserve_review(review_window, monkeypatch, action, kind):
    window, _ = review_window
    profile = activate(window)
    reply = json.dumps({"kind": kind, "text": "New passage." if kind != "critique" else "Useful feedback."})
    snapshot, _, workers = prepare(window, monkeypatch, reply, deferred=True)
    if action == SelectionAction.CONTINUE:
        snapshot = window.selection_actions.capture(snapshot.document_id, insertion=True)
    prompts = []
    window.llm_client.chat = lambda messages: prompts.append(window.llm_client.system_prompt) or reply
    window.selection_actions.start(snapshot, action, "playful" if action == SelectionAction.TONE else "Improve this" if kind == "replacement" else "Assess this")
    request = window.selection_actions.pending.request
    assert request.style_snapshot.id == profile.id
    window.style_service.repository.delete(profile.id, expected_revision=1)
    workers.pop()()
    assert prompts[0].count("PRIVATE_STYLE") == 1
    assert request.style_used["revision"] == 1
    assert window.editor.toPlainText() == snapshot.original
    history = window.chat_manager.get_active_session().messages[-1]
    assert history.metadata["style_used"]["profile_id"] == profile.id
    detail = window.trace_service.detail(history.metadata["request_id"], include_content=True)
    assert "PRIVATE_STYLE" not in json.dumps(detail)
    assert "PRIVATE_SAMPLE" not in json.dumps(detail)
    assert "Personal voice" in window.chat_panel.chat_display.messages[-1].toolTip()
    if kind == "critique":
        assert not window.review_controller.batches
    else:
        assert window.review_controller.batches
        review = window.editor_workspace.review_for_session(snapshot.document_id)
        review.accept_all_button.click()
        review.apply_button.click()
        assert window.editor.toPlainText() == snapshot.original[:snapshot.start] + "New passage." + snapshot.original[snapshot.end:]
        window.editor.undo()
        assert window.editor.toPlainText() == snapshot.original
        window.editor.redo()
        assert "New passage." in window.editor.toPlainText()
    window.chat_panel.load_session(window.chat_manager.get_active_session())
    assert profile.id in window.chat_panel.chat_display.messages[-1].toolTip()


@pytest.mark.parametrize("mutation", ["edit", "close", "project", "cancel", "invalid", "provider-error"])
def test_profile_does_not_weaken_selection_failure_protections(review_window, monkeypatch, mutation):
    window, _ = review_window
    activate(window)
    snapshot, _, workers = prepare(window, monkeypatch, '{"kind":"replacement","text":"New"}', deferred=True)
    if mutation == "invalid":
        window.llm_client.chat = lambda *_: '{"kind":"insertion","text":"Wrong kind"}'
    if mutation == "provider-error":
        def fail(*_):
            raise RuntimeError("Test provider failure")
        window.llm_client.chat = fail
    window.selection_actions.start(snapshot, SelectionAction.REWRITE)
    if mutation == "edit":
        window.editor.insertPlainText("Changed")
    elif mutation == "close":
        window.editor_workspace.close_document(snapshot.document_id)
    elif mutation == "project":
        window.project_service.close_project()
    elif mutation == "cancel":
        window.selection_actions.cancel()
    workers.pop()()
    assert not window.review_controller.batches
    if mutation not in {"edit", "close"}:
        assert window.editor.toPlainText() == snapshot.original


def test_writer_stages_use_submission_snapshot_after_edit_and_deletion(review_window, monkeypatch):
    window, _ = review_window
    profile = activate(window)
    window._create_chat_panel()
    window.active_agent_type = AgentType.WRITER
    prompts, workers = [], []
    def complete(messages):
        prompts.append(window.llm_client.system_prompt)
        if len(prompts) == 1:
            window.style_service.repository.delete(profile.id, expected_revision=2)
        return "Generated prose."
    window.llm_client = SimpleNamespace(system_prompt="original", chat=complete)
    monkeypatch.setattr(window.task_runner, "submit", lambda fn, **kw: workers.append(fn))
    origin_chat = window.chat_manager.active_session_id
    window._on_chat_message_sent("Write a paragraph.")
    window.style_service.repository.update(profile.id, expected_revision=1, name="Later style", instructions="LATER_STYLE")
    workers.pop()()
    assert len(prompts) == 3
    assert all(p.count("PRIVATE_STYLE") == 1 and "LATER_STYLE" not in p for p in prompts)
    assert "Evaluate adherence" in prompts[1]
    message = window.chat_manager.get_session(origin_chat).messages[-1]
    assert message.metadata["style_used"]["revision"] == 1
    data = window.trace_service.detail(message.metadata["request_id"])
    assert {e["details"]["content_hash"] for e in data["events"] if e["code"] == "style.used"} == {profile.snapshot().content_hash}


def test_style_control_remains_visible_for_selection_and_switches_scope(review_window):
    window, root = review_window
    profile = activate(window)
    window._create_chat_panel()
    window.editor.setPlainText("A passage")
    window.editor.selectAll()
    panel = window.chat_panel
    assert not panel.style_combo.isHidden()
    assert panel.agent_combo.isHidden()
    assert panel.style_combo.currentData().profile_id == profile.id
    panel.style_combo.setCurrentIndex(0)
    assert window.style_service.resolve(window._active_chat_project_id()).snapshot is None
    window.style_service.select(None, StyleSelection("profile", profile.id))
    local = window.style_service.repository.create("Local", "Local preferences", project_id=window._active_chat_project_id())
    new_root = root.parent / "other"
    new_root.mkdir()
    other = window.project_service.open_project(new_root)
    window.style_controller.refresh()
    assert panel.style_combo.currentData().mode == "inherit"
    assert "Personal voice" in panel.style_combo.currentText()
    assert all(panel.style_combo.itemData(i) != StyleSelection("profile", local.id) for i in range(panel.style_combo.count()))
    menu = window.editor_workspace.context_menus.create(window.editor, "editor", 0)
    assert any("Style: Personal voice" in a.text() for a in menu.actions())
    menu.deleteLater()


def test_local_editor_cancel_save_limits_and_global_default(review_window, monkeypatch):
    window, _ = review_window
    profile = activate(window)
    service = window.style_service
    editor = StyleProfileEditor(service, window._active_chat_project_id(), profile, window)
    editor.instructions_edit.setPlainText("Discard this edit")
    editor.reject()
    assert service.repository.get(profile.id).instructions == profile.instructions
    editor = StyleProfileEditor(service, window._active_chat_project_id(), profile, window)
    editor.instructions_edit.setPlainText("Saved preference")
    editor.save()
    assert service.repository.get(profile.id).revision == 2
    assert editor.saved_profile.instructions == "Saved preference"
    manager = StyleProfilesDialog(service, window._active_chat_project_id(), window)
    manager.set_default()
    assert service.resolve().snapshot.id == profile.id
    manager.archive()
    assert service.resolve().snapshot is None
    manager.show_archived.setChecked(True)
    assert manager.buttons["Archive"].text() == "Restore"
    manager.archive()
    assert service.repository.get(profile.id).archived == 0
    manager.close()


def test_style_load_failure_sends_no_request(review_window, monkeypatch):
    window, _ = review_window
    activate(window)
    snapshot, calls, workers = prepare(window, monkeypatch, '{"kind":"replacement","text":"New"}', deferred=True)
    monkeypatch.setattr(window.style_service, "resolve", lambda *_: (_ for _ in ()).throw(RuntimeError("unavailable")))
    window.selection_actions.start(snapshot, SelectionAction.REWRITE)
    assert not workers and not calls and window.selection_actions.pending is None
    assert "No model request was sent" in window.chat_panel.chat_display.toPlainText()


@pytest.mark.parametrize("agent", [AgentType.GENERAL, AgentType.BRAINSTORMER])
def test_unstyled_agents_do_not_depend_on_profile_storage(review_window, monkeypatch, agent):
    window, _ = review_window
    window._create_chat_panel()
    window.active_agent_type = agent
    calls = []
    window.llm_client = SimpleNamespace(system_prompt="original", chat=lambda messages: calls.append(messages) or "Helpful answer.")
    monkeypatch.setattr(window.task_runner, "submit", lambda fn, **kwargs: fn())
    monkeypatch.setattr(window.style_service, "resolve", lambda *_: (_ for _ in ()).throw(RuntimeError("profile storage unavailable")))
    window._on_chat_message_sent("Suggest a plot.")
    assert len(calls) == 1
    assert window.chat_manager.get_active_session().messages[-1].metadata["style_used"]["state"] == "not_applicable"
