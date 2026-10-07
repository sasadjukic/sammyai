from types import SimpleNamespace

from test_context_engine import make_engine
from sammyai_core.diagnostics import RequestTraceService
from llm.chat_manager import PreparedChatRequest


def test_empty_failed_and_unavailable_retrieval_are_distinct(tmp_path):
    database, project, _, rag, engine = make_engine(tmp_path)
    trace = RequestTraceService(database)
    try:
        rag.context_text = ""
        assert engine.build_context("Question").retrieval_status == "empty"
        def fail(*args, **kwargs):
            raise RuntimeError("index inaccessible")
        rag.get_context = fail
        result = engine.build_context("Question")
        assert result.retrieval_status == "failed"
        assert result.diagnostic_errors[0]["traceback"]
        identity = trace.begin("chat", project.id, agent="general")
        trace.record_context(identity, PreparedChatRequest([], result), engine=engine)
        data = trace.detail(identity.request_id)
        assert any(e["code"] == "error.retrieval" for e in data["events"])
        assert any(e["code"] == "notice.context" for e in data["events"])
        engine.rag_system = None
        assert engine.build_context("Question").retrieval_status == "unavailable"
    finally:
        database.close()


def test_explicit_no_project_does_not_resolve_active_project_files(tmp_path):
    database, project, _, rag, engine = make_engine(tmp_path)
    try:
        (project.root_path / "chapter.md").write_text("Do not use", encoding="utf-8")
        result = engine.build_context("Read @chapter.md", project=None)
        assert not result.file_snapshots
        assert "requires an open project" in result.notices[0]
    finally:
        database.close()
