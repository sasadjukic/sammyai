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
        self.rag_error = None
        self.llm_error = "No test LLM configured"
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

    editor.close()
    app.processEvents()
    assert services.shutdown_called is True
