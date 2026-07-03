"""Construction and shutdown of SammyAI's runtime services."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from api_key_manager import APIKeyManager
from llm.chat_manager import ChatManager
from llm.client import LLMConfig
from rag.rag_system import RAGSystem

from .database import ProjectDatabase
from .paths import AppPaths
from .projects import ProjectRepository, ProjectService


logger = logging.getLogger(__name__)


@dataclass
class RuntimeServices:
    project_database: ProjectDatabase | None
    project_service: ProjectService | None
    rag_system: RAGSystem | None
    chat_manager: ChatManager
    llm_config: LLMConfig
    llm_client: Any | None
    rag_error: str | None = None
    llm_error: str | None = None
    project_error: str | None = None

    def shutdown(self) -> None:
        self.chat_manager.save_all_sessions()
        if self.rag_system is not None:
            self.rag_system.close()
        if self.project_database is not None:
            self.project_database.close()


def build_runtime_services(paths: AppPaths) -> RuntimeServices:
    project_database: ProjectDatabase | None = None
    project_service: ProjectService | None = None
    project_error: str | None = None
    try:
        project_database = ProjectDatabase(paths.project_database_path)
        project_database.migrate()
        project_service = ProjectService(
            ProjectRepository(project_database),
            paths,
        )
    except Exception as error:
        project_error = str(error)
        logger.exception("Project database initialization failed")
        if project_database is not None:
            project_database.close()
            project_database = None

    rag_system: RAGSystem | None = None
    rag_error: str | None = None
    try:
        rag_system = RAGSystem(
            chunk_size=500,
            overlap=50,
            persist_dir=str(paths.rag_index_dir),
            cache_dir=str(paths.embedding_cache_dir),
            max_documents=1_000_000,
            max_chunks_per_file=150_000,
        )
    except Exception as error:
        rag_error = str(error)
        logger.exception("RAG initialization failed")

    chat_manager = ChatManager(
        storage_dir=str(paths.sessions_dir),
        rag_system=rag_system,
        autosave=True,
    )
    chat_manager.load_all_sessions()
    if not chat_manager.get_active_session():
        chat_manager.create_session()

    llm_config = LLMConfig()
    default_model = APIKeyManager.load_default_model()
    if default_model:
        llm_config.model_key = default_model

    llm_client: Any | None = None
    llm_error: str | None = None
    try:
        llm_client = llm_config.create_client()
    except Exception as error:
        llm_error = str(error)
        logger.warning("LLM client initialization failed: %s", error)

    return RuntimeServices(
        project_database=project_database,
        project_service=project_service,
        rag_system=rag_system,
        chat_manager=chat_manager,
        llm_config=llm_config,
        llm_client=llm_client,
        rag_error=rag_error,
        llm_error=llm_error,
        project_error=project_error,
    )
