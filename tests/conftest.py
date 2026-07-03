"""Shared test classification and cross-platform Qt configuration."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        path = Path(str(item.path))
        parts = set(path.parts)
        if "llm_tests" in parts and path.name != "test_system_prompt_delivery.py":
            item.add_marker(pytest.mark.external)
        if "integration_tests" in parts:
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.model)
        if path.name in {
            "test_embeddings.py",
            "test_large_file_rag.py",
            "test_rag.py",
            "test_rag_system.py",
        }:
            item.add_marker(pytest.mark.model)
