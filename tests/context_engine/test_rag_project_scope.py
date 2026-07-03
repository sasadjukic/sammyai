from types import SimpleNamespace

from rag.rag_system import RAGSystem


class RecordingRetriever:
    def __init__(self):
        self.filters = []

    def retrieve(self, **kwargs):
        self.filters.append(kwargs["filters"])
        return []


class EmptyContextBuilder:
    def build_context(self, **kwargs):
        return SimpleNamespace(chunks=[], context_text="", total_tokens=0)


def test_rag_queries_are_filtered_and_cached_per_project():
    rag = RAGSystem.__new__(RAGSystem)
    rag.retriever = RecordingRetriever()
    rag.context_builder = EmptyContextBuilder()
    rag._last_context_time = 0
    rag._last_context_query = None
    rag._last_context_result = None
    rag._context_cooldown = 2.0

    rag.get_context("Who has the key?", project_id="project-one")
    rag.get_context("Who has the key?", project_id="project-two")

    assert rag.retriever.filters == [
        {"project_id": "project-one"},
        {"project_id": "project-two"},
    ]
