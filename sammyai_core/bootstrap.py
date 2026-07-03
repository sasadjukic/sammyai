"""Construction and shutdown of SammyAI's runtime services."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from api_key_manager import APIKeyManager
from llm.chat_manager import ChatManager
from llm.client import LLMConfig
from rag.rag_system import RAGSystem

from .paths import AppPaths


logger = logging.getLogger(__name__)


@dataclass
class RuntimeServices:
    rag_system: RAGSystem | None
    chat_manager: ChatManager
    llm_config: LLMConfig
    llm_client: Any | None
    rag_error: str | None = None
    llm_error: str | None = None

    def shutdown(self) -> None:
        self.chat_manager.save_all_sessions()
        if self.rag_system is not None:
            self.rag_system.close()


def build_runtime_services(paths: AppPaths) -> RuntimeServices:
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
        rag_system=rag_system,
        chat_manager=chat_manager,
        llm_config=llm_config,
        llm_client=llm_client,
        rag_error=rag_error,
        llm_error=llm_error,
    )
