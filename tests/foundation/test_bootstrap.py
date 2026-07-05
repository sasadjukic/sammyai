from unittest.mock import MagicMock, patch

from sammyai_core.bootstrap import build_runtime_services
from sammyai_core.paths import AppPaths


def test_runtime_services_are_built_from_application_paths(tmp_path):
    paths = AppPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        log_dir=tmp_path / "logs",
    ).ensure_created()
    fake_rag = MagicMock()
    fake_config = MagicMock()
    fake_client = MagicMock()
    fake_config.create_client.return_value = fake_client

    with (
        patch("sammyai_core.bootstrap.RAGSystem", return_value=fake_rag) as rag_factory,
        patch("sammyai_core.bootstrap.LLMConfig", return_value=fake_config),
        patch(
            "sammyai_core.bootstrap.APIKeyManager.load_default_model",
            return_value="",
        ),
    ):
        services = build_runtime_services(paths)

    rag_factory.assert_called_once_with(
        chunk_size=500,
        overlap=50,
        persist_dir=str(paths.rag_index_dir),
        cache_dir=str(paths.embedding_cache_dir),
        max_documents=1_000_000,
        max_chunks_per_file=150_000,
    )
    assert services.rag_system is fake_rag
    assert services.llm_client is fake_client
    assert services.project_database.path == paths.project_database_path
    assert services.project_service is not None
    assert services.context_engine.project_service is services.project_service
    assert services.chat_manager.context_engine is services.context_engine
    assert services.file_tools.project_service is services.project_service
    assert services.chat_manager.autosave is True
    assert services.chat_manager.get_active_session() is not None

    services.shutdown()
    fake_rag.close.assert_called_once()
