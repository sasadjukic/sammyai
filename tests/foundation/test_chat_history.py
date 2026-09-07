from datetime import datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from llm.chat_manager import ChatManager, MessageRole
from ui.chat_panel import ChatPanel


def test_history_titles_order_filters_and_restoration(tmp_path):
    manager = ChatManager(str(tmp_path), autosave=True)
    manager.create_session("legacy")
    manager.add_message(MessageRole.USER, "  A useful\n title  ")
    manager.create_session("project", metadata={"project_id": "p"})
    manager.add_message(MessageRole.USER, "Project question", session_id="project")
    manager.get_session("legacy").updated_at = datetime.now() - timedelta(days=1)
    manager.save_session("legacy")
    assert [s.id for s in manager.conversation_summaries()] == ["project", "legacy"]
    assert manager.conversation_summaries(project_id="p", scope="project")[0].id == "project"
    assert manager.conversation_summaries(scope="unassigned")[0].title == "A useful title"
    assert manager.rename_session("project", "My chapter")
    manager.set_active_session("legacy")
    reloaded = ChatManager(str(tmp_path), autosave=True)
    assert reloaded.load_all_sessions() == 2
    assert reloaded.active_session_id == "legacy"
    assert reloaded.conversation_summaries()[0].title == "My chapter"
    assert reloaded.delete_session("legacy")
    assert not (tmp_path / "legacy.json").exists()


def test_corrupt_sessions_do_not_hide_valid_history(tmp_path):
    manager = ChatManager(str(tmp_path), autosave=True)
    manager.create_session("valid")
    (tmp_path / "broken.json").write_text("{broken")
    (tmp_path / "wrong.json").write_text('{"session_id": "wrong"}')
    loaded = ChatManager(str(tmp_path))
    assert loaded.load_all_sessions() == 1
    assert len(loaded.load_errors) == 2
    assert loaded.active_session_id == "valid"


def test_history_switch_renders_metadata_and_preserves_drafts(tmp_path):
    app = QApplication.instance() or QApplication([])
    manager = ChatManager(str(tmp_path), autosave=True)
    manager.create_session("a")
    manager.add_message(MessageRole.USER, "Question A")
    manager.add_message(MessageRole.ASSISTANT, "Answer A", metadata={"agent_type": "brainstormer"})
    manager.create_session("b")
    panel = ChatPanel()
    panel.bind_history(manager)
    try:
        assert "Answer A" in panel.chat_display.toPlainText()
        assert "brainstormer" in panel.chat_display.messages[-1].toolTip()
        panel.input_field.setPlainText("Unsent A")
        panel.select_conversation("b")
        assert panel.chat_display.toPlainText() == ""
        panel.select_conversation("a")
        assert panel.input_field.toPlainText() == "Unsent A"
        panel.set_thinking(True)
        panel.select_conversation("b")
        assert manager.active_session_id == "a"
        assert not panel.history_list.isEnabled()
        panel.set_thinking(False)
        panel.select_conversation("b")
        assert manager.active_session_id == "b"
    finally:
        panel.close()
        app.processEvents()


def test_history_delete_confirmation_and_persistence(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    manager = ChatManager(str(tmp_path), autosave=True)
    manager.create_session("a")
    panel = ChatPanel()
    panel.bind_history(manager)
    try:
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.No)
        panel._delete_conversation()
        assert manager.get_session("a") is not None
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
        panel._delete_conversation()
        assert manager.get_session("a") is None
        assert not (tmp_path / "a.json").exists()
        assert manager.get_active_session() is not None
    finally:
        panel.close()
        app.processEvents()


def test_response_uses_origin_even_if_active_session_changes(tmp_path):
    from threading import Lock
    from types import SimpleNamespace
    from sammyai import TextEditor
    from sammyai_core.agent_workflows import AgentType

    for mode in ("normal", "dbe"):
        manager = ChatManager(str(tmp_path / mode), autosave=True)
        manager.create_session("a")
        manager.add_message(MessageRole.USER, "Question from A")
        manager.create_session("b")
        manager.add_message(MessageRole.USER, "Question from B", session_id="b")
        queued, contexts, errors, results = [], [], [], []
        def complete(messages):
            contexts.extend(messages)
            return "Answer for A"
        def run(agent, **kwargs):
            response = kwargs["complete"](kwargs["messages"], "Test prompt")
            return SimpleNamespace(response=response, agent_type=agent, run_id="run", model_calls=1)
        target = SimpleNamespace(
            chat_manager=manager, active_agent_type=AgentType.GENERAL,
            llm_client=SimpleNamespace(system_prompt="base", chat=complete),
            _active_chat_project_id=lambda: None,
            task_runner=SimpleNamespace(submit=lambda fn, **kwargs: queued.append(fn)),
            _llm_lock=Lock(), agent_workflows=SimpleNamespace(run=run),
            agent_progress=SimpleNamespace(emit=lambda value: None),
            agent_run_completed=SimpleNamespace(emit=results.append),
            llm_error_occurred=SimpleNamespace(emit=errors.append),
            editor_workspace=SimpleNamespace(active_session=lambda: SimpleNamespace(session_id="document")),
            _get_editor_context_for_dbe=lambda: ("Original line", 1, None, None),
            current_file=None, dbe_context_lines=20,
            _extract_text_from_llm_response=lambda reply: reply,
            dbe_diff_ready=SimpleNamespace(emit=results.append),
        )
        handler = TextEditor._handle_normal_chat if mode == "normal" else TextEditor._handle_dbe_request
        handler(target, "Question from A")
        manager.set_active_session("b")
        queued.pop()()
        assert errors == []
        assert results
        assert any(m["content"] == "Question from A" for m in contexts)
        assert not any(m["content"] == "Question from B" for m in contexts)
        reloaded = ChatManager(str(tmp_path / mode))
        reloaded.load_all_sessions()
        assert reloaded.get_session("a").messages[-1].content == "Answer for A"
        assert len(reloaded.get_session("b").messages) == 1


def test_failed_delete_keeps_conversation_in_memory(tmp_path, monkeypatch):
    manager = ChatManager(str(tmp_path), autosave=True)
    manager.create_session("a")
    def fail(*args, **kwargs):
        raise PermissionError("Read-only storage")
    from pathlib import Path
    monkeypatch.setattr(Path, "unlink", fail)
    assert not manager.delete_session("a")
    assert manager.get_active_session().session_id == "a"


def test_missing_selection_falls_back_to_newest(tmp_path):
    manager = ChatManager(str(tmp_path), autosave=True)
    manager.create_session("old")
    manager.create_session("new")
    (tmp_path / ".history-state").write_text('{"active_session_id": "gone"}')
    loaded = ChatManager(str(tmp_path))
    loaded.load_all_sessions()
    assert loaded.active_session_id == "new"


def test_history_drawer_keeps_composer_available_and_filters_legacy(tmp_path):
    app = QApplication.instance() or QApplication([])
    manager = ChatManager(str(tmp_path), autosave=True)
    manager.create_session("legacy")
    manager.create_session("project", metadata={"project_id": "p"})
    manager.set_active_session("project")
    panel = ChatPanel()
    panel.bind_history(manager, "p")
    panel.resize(500, 750)
    panel.show()
    try:
        panel.history_button.click()
        app.processEvents()
        assert panel.history_drawer.isVisible()
        assert panel.history_drawer.height() <= 230
        assert panel.input_field.isVisible()
        assert panel.history_list.count() == 1
        panel.history_filter.setCurrentIndex(2)
        assert panel.history_list.count() == 1
        assert panel.history_list.item(0).data(Qt.UserRole) == "legacy"
        panel.history_list.setCurrentRow(0)
        assert manager.active_session_id == "legacy"
        panel.history_button.click()
        assert panel.history_drawer.isHidden()
    finally:
        panel.close()
        app.processEvents()
