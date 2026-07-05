import time
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from llm.chat_manager import ChatManager, MessageRole
from sammyai import TextEditor
from sammyai_core.agent_workflows import AgentWorkflowService
from sammyai_core.paths import AppPaths


class FakeClient:
    def __init__(self):
        self.system_prompt = "base prompt"
        self.prompts = []

    def chat(self, messages):
        self.prompts.append(self.system_prompt)
        return "Consider making the locked room a deliberate trap."


class FakeRuntimeServices:
    def __init__(self):
        self.rag_system = None
        self.context_engine = None
        self.file_tools = None
        self.agent_workflows = AgentWorkflowService(None)
        self.chat_manager = ChatManager()
        self.chat_manager.create_session("agent-ui")
        self.llm_config = SimpleNamespace(
            model_key="test-model",
            temperature=0.9,
            top_p=0.9,
            seed=None,
        )
        self.llm_client = FakeClient()
        self.project_service = None
        self.rag_error = None
        self.llm_error = None
        self.project_error = None

    def shutdown(self):
        pass


def test_selected_agent_runs_through_chat_and_persists_metadata(tmp_path):
    app = QApplication.instance() or QApplication([])
    paths = AppPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        log_dir=tmp_path / "logs",
    ).ensure_created()
    services = FakeRuntimeServices()
    editor = TextEditor(services=services, app_paths=paths)
    editor._create_chat_panel()
    editor._on_agent_selected("brainstormer")

    editor._on_chat_message_sent("Help me improve the locked-room reveal.")
    deadline = time.monotonic() + 3
    while editor.task_runner.active_count and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()

    session = services.chat_manager.get_active_session()
    assert [message.role for message in session.messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]
    assert session.messages[0].metadata["agent_type"] == "brainstormer"
    assert session.messages[1].metadata["agent_type"] == "brainstormer"
    assert "Brainstormer Role" in services.llm_client.prompts[0]
    assert services.llm_client.system_prompt == "base prompt"
    assert "deliberate trap" in editor.chat_panel.chat_display.toPlainText()

    editor.close()
    app.processEvents()
