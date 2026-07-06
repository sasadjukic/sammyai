from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from llm.chat_manager import ChatManager
from sammyai import TextEditor
from sammyai_core.paths import AppPaths


class FakeRuntimeServices:
    def __init__(self):
        self.rag_system = None
        self.chat_manager = ChatManager()
        self.chat_manager.create_session("characterization")
        self.llm_config = SimpleNamespace(
            model_key="test-model",
            temperature=0.9,
            top_p=0.9,
            seed=None,
        )
        self.llm_client = None
        self.project_service = None
        self.rag_error = None
        self.llm_error = "No test LLM configured"
        self.project_error = None
        self.shutdown_called = False

    def shutdown(self):
        self.shutdown_called = True


def test_editor_accepts_injected_runtime_services(tmp_path):
    app = QApplication.instance() or QApplication([])
    paths = AppPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        log_dir=tmp_path / "logs",
    ).ensure_created()
    services = FakeRuntimeServices()

    editor = TextEditor(services=services, app_paths=paths)

    assert editor.runtime_services is services
    assert editor.chat_manager.get_active_session().session_id == "characterization"
    assert "SammyAI" in editor.windowTitle()
    assert [action.text() for action in editor.compare_menu.actions()] == [
        "Compare with File...",
        "Compare with Clipboard",
        "",
        "Apply Diff from File...",
        "",
        "Undo Last Applied Change Set",
        "Redo Last Applied Change Set",
    ]
    assert [action.text() for action in editor.advanced_menu.actions()] == [
        "Persistent Memory",
        "Project Context",
        "Legacy Manual Indexing",
        "",
        "Enable Legacy DBE Mode",
    ]
    assert [
        action.text() for action in editor.persistent_memory_menu.actions()
    ] == [
        "Manage Project Memory...",
        "Summarize Current Chat...",
    ]
    assert not editor.rebuild_project_context_action.isEnabled()
    assert not editor.manage_memory_action.isEnabled()
    assert not editor.summarize_chat_action.isEnabled()

    editor._create_chat_panel()
    assert editor.chat_panel.attach_button.text() == "Attach Reference"
    assert [action.text() for action in editor.chat_panel.attach_button.menu().actions()] == [
        "Attach Reference...",
        "Remove Attached Reference",
    ]
    assert not hasattr(editor.chat_panel, "rag_button")
    assert not hasattr(editor.chat_panel, "dbe_button")
    assert [
        editor.chat_panel.agent_combo.itemText(index)
        for index in range(editor.chat_panel.agent_combo.count())
    ] == ["Assistant", "Brainstormer", "Writer", "Editor", "Critic"]

    editor.close()
    app.processEvents()
    assert services.shutdown_called is True
