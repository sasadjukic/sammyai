"""Durability, migration, bounded capture and failure isolation."""
from dataclasses import replace
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from sammyai_core.database import ProjectDatabase
from sammyai_core.diagnostics import CaptureSettings, CONTENT_LIMIT, RequestTraceService, inspect_proposal
from sammyai_core.agent_workflows import AgentWorkflowService


@pytest.fixture
def trace(tmp_path):
    database = ProjectDatabase(tmp_path / "state.sqlite3")
    database.migrate()
    yield RequestTraceService(database)
    database.close()


def test_upgrade_preserves_v4_state_and_old_chat(tmp_path):
    database = ProjectDatabase(tmp_path / "old.sqlite3")
    database.migrate(4)
    with database.transaction() as db:
        db.execute("INSERT INTO projects VALUES ('project','Novel','C:/novel','c:/novel','now','now','now')")
        db.execute("INSERT INTO application_state VALUES ('old_setting','kept','now')")
    chat = tmp_path / "chat.json"
    chat.write_text('{"session_id":"old","messages":[]}', encoding="utf-8")
    before = chat.read_bytes()
    database.migrate()
    with database.read() as db:
        assert db.execute("SELECT name FROM projects").fetchone()[0] == "Novel"
        assert db.execute("SELECT value FROM application_state WHERE key='old_setting'").fetchone()[0] == "kept"
    assert chat.read_bytes() == before
    database.close()


def test_restart_retains_completed_steps_and_marks_pending_work_interrupted(trace):
    completed = trace.begin("chat-a", "project", agent="writer")
    parent = trace.start_step(completed.request_id, "workflow")
    child = trace.start_step(completed.request_id, "model.draft", parent_step_id=parent, attempt=2)
    trace.event(completed.request_id, "model.responded", "Draft ready", step_id=child)
    trace.end_step(child, "responded", 12.5)
    trace.end_step(parent, "responded", 20)
    trace.finish(completed.request_id, "responded")
    pending = trace.begin("chat-b", "project", agent="editor")
    trace.start_step(pending.request_id, "model.response")
    trace.finish(pending.request_id, "pending_review")
    trace.database.close()
    restored = RequestTraceService(trace.database)
    restored.recover_interrupted()
    done = restored.detail(completed.request_id)
    assert done["request"]["outcome"] == "responded"
    assert done["steps"][1]["parent_step_id"] == parent
    assert done["steps"][1]["attempt"] == 2
    assert done["steps"][1]["duration_ms"] == 12.5
    interrupted = restored.detail(pending.request_id)
    assert interrupted["request"]["outcome"] == "interrupted"
    assert interrupted["steps"][0]["outcome"] == "interrupted"
    restored.recover_interrupted()
    assert len(restored.detail(pending.request_id)["events"]) == 2


def test_capture_flags_redaction_limits_and_export_opt_in(trace):
    identity = trace.begin("chat", None, agent="editor")
    trace.capture(identity.request_id, "prompts", "private writing")
    trace.register_secret("opaque-provider-credential")
    trace.save_settings(CaptureSettings(failed_proposals=True))
    source = 'API_KEY="opaque-provider-credential"\nAuthorization: Bearer other-secret\n' + "x" * CONTENT_LIMIT
    trace.capture(identity.request_id, "failed_proposals", source)
    trace.event(identity.request_id, "error.provider", "opaque-provider-credential", details={"api_key": "never", "safe": "https://user:pass@example.com"})
    metadata_only = trace.export_preview(identity.request_id)
    included = trace.export_preview(identity.request_id, include_content=True)
    assert "private writing" not in included
    assert "opaque-provider-credential" not in included
    assert "other-secret" not in included
    assert "user:pass" not in included
    assert '"text"' not in metadata_only
    content = trace.detail(identity.request_id, include_content=True)["content"]
    assert content[0]["captured"] == 0 and content[0]["text"] is None
    assert content[1]["captured"] == 1 and content[1]["truncated"] == 1
    assert len(content[1]["text"]) <= CONTENT_LIMIT
    assert RequestTraceService(trace.database).settings.failed_proposals


def test_retention_and_deletion_cascade_without_resurrecting(trace):
    first = trace.begin("a", "project", agent="general")
    trace.finish(first.request_id, "responded")
    second = trace.begin("b", "project", agent="writer")
    trace.link(second.request_id, "proposal", "proposal")
    trace.capture(second.request_id, "responses", "test")
    trace.start_step(second.request_id, "model")
    trace.save_settings(replace(trace.settings, max_requests=1))
    assert trace.detail(first.request_id) is None
    assert trace.detail(second.request_id) is not None
    trace.delete(second.request_id)
    trace.event(second.request_id, "late.event", "discarded")
    trace.capture(second.request_id, "responses", "late")
    trace.link(second.request_id, "late-proposal", "proposal")
    assert not trace.list_requests()
    with trace.database.read() as db:
        for name in ("events", "content", "steps", "links"):
            assert db.execute(f"SELECT count(*) FROM diagnostic_{name}").fetchone()[0] == 0


def test_retention_age_preserves_inflight(trace):
    complete = trace.begin("a", None, agent="general")
    running = trace.begin("a", None, agent="general")
    trace.finish(complete.request_id, "responded")
    with trace.database.transaction() as db:
        db.execute("UPDATE diagnostic_requests SET updated_at='2000-01-01'")
    trace.prune()
    assert trace.detail(complete.request_id) is None
    assert trace.detail(running.request_id) is not None


def test_storage_failure_preserves_original_provider_error_and_marks_gap(trace):
    identity = trace.begin("chat", None, agent="general")
    with trace.database.read() as db:
        db.execute("PRAGMA query_only=ON")
    def fail(*args):
        raise RuntimeError("original provider failure")
    with pytest.raises(RuntimeError, match="original provider failure"):
        AgentWorkflowService(None).run("general", user_request="test", messages=[], complete=fail, trace=trace, identity=identity)
    assert trace.storage_error and "incomplete" in trace.storage_error
    with trace.database.read() as db:
        db.execute("PRAGMA query_only=OFF")
    trace.event(identity.request_id, "recovered", "Storage available again")
    assert trace.detail(identity.request_id)["request"]["incomplete"] == 1


def test_concurrent_events_keep_identity_unique_and_ordered(trace):
    identities = [trace.begin(f"chat-{i}", None, agent="general") for i in range(4)]
    def record(identity):
        for i in range(15):
            trace.event(identity.request_id, "progress", "Step", details={"n": i})
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(record, identities))
    for identity in identities:
        data = trace.detail(identity.request_id)
        assert len(data["events"]) == 16
        assert len({e["id"] for e in data["events"]}) == 16
        assert [e["details"]["n"] for e in data["events"][1:]] == list(range(15))


@pytest.mark.parametrize("source", [
    '<sammyai_changes>{"files":[]}',
    '</sammyai_changes>',
    '<sammyai_changes>[]</sammyai_changes>',
    '<sammyai_changes>{"files": broken}</sammyai_changes>',
    '<sammyai_changes>{"files":[]}</sammyai_changes><sammyai_changes>',
])
def test_offline_malformed_fixture_rejected_without_file_tools(source):
    assert inspect_proposal(source)["outcome"] == "rejected"


def test_offline_parser_never_applies_a_valid_write(tmp_path):
    target = tmp_path / "untouched.md"
    source = '<sammyai_changes>' + json.dumps({"files": [{"path": str(target), "operation": "write", "content": "bad"}]}) + '</sammyai_changes>'
    assert inspect_proposal(source) == {"outcome": "parsed", "file_count": 1}
    assert not target.exists()


@pytest.mark.parametrize("error_code", ["error.proposal_parse", "error.proposal_validation"])
def test_restored_chat_prefers_friendly_notice_but_preserves_technical_evidence(trace, error_code):
    first = trace.begin("chat", None, agent="editor")
    step = trace.start_step(first.request_id, "proposal.validation")
    trace.exception(first.request_id, error_code, ValueError("bad proposal"), step_id=step)
    trace.event(first.request_id, "notice.proposal", "File proposal rejected: bad proposal", step_id=step)
    # An unrelated error, another validation step and another request must stay
    # visible even when a friendly rejection exists elsewhere in the chat.
    trace.exception(first.request_id, "error.provider", TimeoutError("provider timeout"), step_id=step)
    other_step = trace.start_step(first.request_id, "proposal.validation")
    trace.exception(first.request_id, error_code, ValueError("other step"), step_id=other_step)
    second = trace.begin("chat", None, agent="editor")
    trace.exception(second.request_id, error_code, ValueError("unsaved notice"))
    restored = RequestTraceService(trace.database)
    notices = restored.conversation_notices("chat")
    assert [n["message"] for n in notices] == [
        "File proposal rejected: bad proposal", "TimeoutError: provider timeout",
        "ValueError: other step", "ValueError: unsaved notice",
    ]
    assert any(e["code"] == error_code and e["step_id"] == step
               for e in restored.detail(first.request_id)["events"])
