"""Request-to-review integration with real Qt widgets and local file safeguards."""
from dataclasses import replace
import json
import os
from types import SimpleNamespace

import pytest

from test_inline_review import review_window
from editing.change_sets import FileChangeRequest
from editing.review_session import HunkState
from sammyai_core.agent_workflows import AgentType
from sammyai_core.context_engine import ProjectContextEngine, ProjectFileRepository
from sammyai_core.diagnostics import RequestTraceService, RequestUpdate
from sammyai_core.file_tools import ChangeApplyError
from ui.diagnostics import DiagnosticsDialog


def setup_chat(window, monkeypatch, reply):
    window._create_chat_panel()
    window.chat_panel.agent_combo.setCurrentIndex(window.chat_panel.agent_combo.findData("editor"))
    window.llm_client = SimpleNamespace(system_prompt="base", chat=lambda *_: reply)
    monkeypatch.setattr(window.task_runner, "submit", lambda fn, **kwargs: fn())
    window.chat_manager.context_engine = ProjectContextEngine(window.project_service,
        ProjectFileRepository(window.project_service.repository.database), None)


def test_october_6_failure_retains_typo_partial_context_and_malformed_proposal(review_window, monkeypatch):
    window, root = review_window
    source = "".join(f"## Scene {i}\n" + "Existing material. " * 100 + "\n" for i in range(1, 20))
    path = root / "scenes.md"
    path.write_text(source, encoding="utf-8")
    raw = '<sammyai_changes>{"files": broken}</sammyai_changes>'
    setup_chat(window, monkeypatch, raw)
    window.trace_service.save_settings(replace(window.trace_service.settings, failed_proposals=True))
    window._on_chat_message_sent("Add a scene in @scnes.md using @scenes.md")
    row = window.trace_service.list_requests()[0]
    data = window.trace_service.detail(row["id"], include_content=True)
    assert row["outcome"] == "proposal_rejected"
    assert not window.review_controller.batches
    assert path.read_text(encoding="utf-8") == source
    context = next(e for e in data["events"] if e["code"] == "context.prepared")["details"]
    assert any(ref["reference"] == "scnes.md" and ref["error"] for ref in context["references"])
    assert context["truncated"]
    assert context["files"][0]["source_hash"]
    assert context["files"][0]["ranges"]
    assert not context["files"][0]["complete"]
    assert any(e["code"] == "model.responded" for e in data["events"])
    assert any(c["text"] == raw for c in data["content"])
    assert not any(e["code"].startswith("files.") for e in data["events"])
    # Reopen the durable diagnostics through a new service instance.
    window.chat_manager.trace_service = RequestTraceService(window.trace_service.database)
    session = window.chat_manager.get_active_session()
    window.chat_panel.load_session(session)
    rendered = window.chat_panel.chat_display.toPlainText()
    assert "scnes.md" in rendered and "partial file context" in rendered
    assert rendered.count("File proposal rejected") == 1
    assert "JSONDecodeError:" not in rendered
    assert "Invalid JSON in change directive" in rendered
    assert all("File proposal rejected" not in m["content"] for m in window.chat_manager.get_messages_for_llm())


@pytest.mark.parametrize("capture", [False, True])
def test_missing_brace_recovery_retains_original_evidence_and_requires_review(review_window, monkeypatch, capture):
    window, root = review_window
    path = root / "chapter.md"
    path.write_text("Original chapter.\n", encoding="utf-8")
    body = json.dumps({"summary": "Rewrite chapter", "files": [
        {"path": "chapter.md", "operation": "write", "content": "PRIVATE NEW CHAPTER\n"},
    ]})
    raw = '<sammyai_changes>' + body[:-3] + '\n]}</sammyai_changes>'
    setup_chat(window, monkeypatch, raw)
    window.trace_service.save_settings(replace(window.trace_service.settings, failed_proposals=capture))
    window._on_chat_message_sent("Rewrite @chapter.md")
    data = window.trace_service.detail(window.trace_service.list_requests()[0]["id"], include_content=True)
    assert data["request"]["outcome"] == "pending_review"
    assert window.review_controller.batches
    assert path.read_text(encoding="utf-8") == "Original chapter.\n"
    events = data["events"]
    assert sum(e["code"] == "model.started" for e in events) == 1
    assert any(e["code"] == "proposal.syntax_error" and e["details"]["json_error"] for e in events)
    recovery = next(e for e in events if e["code"] == "proposal.syntax_recovered")
    assert recovery["details"]["inserted"] == "}"
    assert recovery["details"]["original_hash"] != recovery["details"]["recovered_hash"]
    assert not any(e["code"].startswith("files.") for e in events)
    captured = next(c for c in data["content"] if c["kind"] == "failed_proposals")
    assert captured["captured"] == capture
    assert captured["text"] == (raw if capture else None)
    assert "PRIVATE NEW CHAPTER" not in json.dumps(events)
    window.chat_panel.load_session(window.chat_manager.get_active_session())
    rendered = window.chat_panel.chat_display.toPlainText()
    assert rendered.count("File proposal formatting corrected") == 1
    assert "JSONDecodeError:" not in rendered


def test_raw_four_part_replacement_supports_partial_review_and_durable_diagnostics(review_window, monkeypatch):
    window, root = review_window
    source = ''.join(f'Old part {i}.\r\n' + 'Unchanged context.\r\n' * 8 for i in range(4))
    path = root / 'chapter.md'
    path.write_bytes(source.encode())
    raw = '<sammyai_edits>\nsummary: Revise four passages\nfile: chapter.md\noperation: replace\n'
    for i in range(4):
        raw += f'<<<SAMMYAI_SEARCH>>>\nOld part {i}.\n<<<SAMMYAI_REPLACEMENT>>>\nNew "part" {i}.\n<<<SAMMYAI_END>>>\n'
    raw += '</sammyai_edits>'
    setup_chat(window, monkeypatch, raw)
    window._on_chat_message_sent('Revise the four passages in @chapter.md')
    row = window.trace_service.list_requests()[0]
    assert row['outcome'] == 'pending_review'
    assert path.read_bytes() == source.encode()
    batch = next(iter(window.review_controller.batches.values()))
    review = batch.reviews[0]
    assert len(batch.reviews) == 1 and len(review.hunks) == 4
    for index, hunk in enumerate(review.hunks):
        review.decide(hunk.id, HunkState.ACCEPTED if index % 2 == 0 else HunkState.REJECTED)
    assert window.review_controller.apply(batch.id)
    expected = source.replace('Old part 0.', 'New "part" 0.').replace('Old part 2.', 'New "part" 2.')
    assert path.read_bytes() == expected.encode()
    window._undo_last_change_set()
    assert path.read_bytes() == source.encode()
    window._redo_last_change_set()
    assert path.read_bytes() == expected.encode()
    data = window.trace_service.detail(row['id'], include_content=True)
    assert data['request']['outcome'] == 'redone'
    assert data['request']['metadata']['prompt_version'] == 'agent-prompts-v2-text-edits'
    validation = next(e for e in data['events'] if e['code'] == 'proposal.validation')['details']
    assert validation['proposal_format'] == 'text-v2' and validation['operations'] == ['replace']
    assert 'SAMMYAI_SEARCH' not in window.chat_panel.chat_display.toPlainText()
    assert 'Old part' not in json.dumps(data)
    assert all('SAMMYAI_SEARCH' not in m['content'] for m in window.chat_manager.get_messages_for_llm())


@pytest.mark.parametrize('capture', [False, True])
def test_malformed_text_proposal_keeps_opt_in_evidence_and_no_writes(review_window, monkeypatch, capture):
    window, root = review_window
    path = root / 'chapter.md'
    path.write_bytes(b'Original')
    raw = '<sammyai_edits>\nsummary: Rewrite\nfile: chapter.md\noperation: write\n<<<SAMMYAI_CONTENT>>>\nPRIVATE NEW TEXT\n</sammyai_edits>'
    setup_chat(window, monkeypatch, raw)
    window.trace_service.save_settings(replace(window.trace_service.settings, failed_proposals=capture))
    window._on_chat_message_sent('Rewrite @chapter.md')
    data = window.trace_service.detail(window.trace_service.list_requests()[0]['id'], include_content=True)
    assert data['request']['outcome'] == 'proposal_rejected'
    assert not window.review_controller.batches and path.read_bytes() == b'Original'
    assert 'PRIVATE NEW TEXT' not in window.chat_panel.chat_display.toPlainText()
    assert 'PRIVATE NEW TEXT' not in json.dumps(data['events'])
    evidence = next(c for c in data['content'] if c['kind'] == 'failed_proposals')
    assert evidence['text'] == (raw if capture else None)


def traced_review(window, root):
    before = "old\n" + "keep\n" * 10 + "last\n"
    after = "new\n" + "keep\n" * 10 + "changed\n"
    (root / "chapter.md").write_bytes(before.encode("utf-8"))
    source = window.file_tools.prepare_change_set([FileChangeRequest.write("chapter.md", after)], description="Edit chapter")
    identity = window.trace_service.begin(window.chat_manager.active_session_id, source.project_id, agent="editor")
    window.trace_service.link(identity.request_id, source.id, "proposal")
    window.trace_service.finish(identity.request_id, "pending_review")
    batch = window.review_controller.start_change_set(source, request_id=identity.request_id)
    return identity, batch, before, after


def test_partial_review_apply_undo_redo_keep_causal_links(review_window):
    window, root = review_window
    identity, batch, before, after = traced_review(window, root)
    review = batch.reviews[0]
    review.decide(review.hunks[0].id, HunkState.ACCEPTED)
    review.decide(review.hunks[1].id, HunkState.REJECTED)
    assert window.review_controller.apply(batch.id)
    assert (root / "chapter.md").read_text(encoding="utf-8") == before.replace("old", "new")
    window._undo_last_change_set()
    assert (root / "chapter.md").read_text(encoding="utf-8") == before
    window._redo_last_change_set()
    data = window.trace_service.detail(identity.request_id)
    assert data["request"]["outcome"] == "redone"
    codes = [e["code"] for e in data["events"]]
    for expected in ("review.created", "review.partially_accepted", "files.applied", "files.undone", "files.redone"):
        assert expected in codes
    assert {link["kind"] for link in data["links"]} == {"proposal", "review", "accepted_change_set", "undo_change_set"}
    decisions = next(e for e in data["events"] if e["code"] == "review.partially_accepted")["details"]["reviews"][0]
    assert {h["state"] for h in decisions["hunks"]} == {"accepted", "rejected"}


@pytest.mark.parametrize("outcome", ["rejected", "canceled", "conflicted", "applied"])
def test_review_terminal_outcomes_are_distinct(review_window, outcome):
    window, root = review_window
    identity, batch, before, after = traced_review(window, root)
    if outcome == "canceled":
        window.review_controller.cancel(batch.id)
    else:
        batch.reviews[0].decide_all(HunkState.REJECTED if outcome == "rejected" else HunkState.ACCEPTED)
        if outcome == "conflicted":
            (root / "chapter.md").write_text("external edit", encoding="utf-8")
        assert window.review_controller.apply(batch.id) == (outcome != "conflicted")
    assert window.trace_service.detail(identity.request_id)["request"]["outcome"] == outcome
    assert (root / "chapter.md").read_text(encoding="utf-8") == (after if outcome == "applied" else "external edit" if outcome == "conflicted" else before)


def test_rollback_evidence_and_storage_failure_do_not_weaken_file_safety(review_window, monkeypatch):
    window, root = review_window
    for name in ("a.md", "b.md"):
        (root / name).write_text("original", encoding="utf-8")
    change = window.file_tools.prepare_change_set([FileChangeRequest.write(name, "changed") for name in ("a.md", "b.md")], description="Two files")
    identity = window.trace_service.begin("chat", change.project_id, agent="editor")
    window.trace_service.link(identity.request_id, change.id, "accepted_change_set")
    replacements = 0
    def fail_second(source, target):
        nonlocal replacements
        replacements += 1
        if replacements == 2:
            raise OSError("simulated disk failure")
        os.replace(source, target)
    monkeypatch.setattr(window.file_tools, "_replace", fail_second)
    with pytest.raises(ChangeApplyError, match="simulated disk failure"):
        window.file_tools.apply(change)
    assert window.trace_service.detail(identity.request_id)["request"]["outcome"] == "rolled_back"
    assert all((root / name).read_text(encoding="utf-8") == "original" for name in ("a.md", "b.md"))
    with window.trace_service.database.read() as db:
        db.execute("PRAGMA query_only=ON")
    replacements = 0
    with pytest.raises(ChangeApplyError, match="simulated disk failure"):
        window.file_tools.apply(change)
    assert window.trace_service.storage_error
    assert all((root / name).read_text(encoding="utf-8") == "original" for name in ("a.md", "b.md"))
    with window.trace_service.database.read() as db:
        db.execute("PRAGMA query_only=OFF")


def test_errors_progress_and_context_stay_with_origin_after_switch(review_window, monkeypatch):
    window, root = review_window
    setup_chat(window, monkeypatch, "unused")
    queued = []
    monkeypatch.setattr(window.task_runner, "submit", lambda fn, **kwargs: queued.append(fn))
    seen = []
    def fail(messages):
        seen.extend(messages)
        raise TimeoutError("origin timeout")
    window.llm_client.chat = fail
    (root / "chapter.md").write_text("Origin project content", encoding="utf-8")
    origin = window.chat_manager.active_session_id
    project = window.project_service.active_project
    window._on_chat_message_sent("Read @chapter.md")
    identity_id = window.trace_service.list_requests()[0]["id"]
    other_root = root.parent / "other-project"
    other_root.mkdir()
    (other_root / "chapter.md").write_text("Wrong project content", encoding="utf-8")
    window.project_service.open_project(other_root)
    other_chat = window.chat_manager.create_session("other-chat")
    window.chat_manager.set_active_session(other_chat.session_id)
    window.chat_panel.load_session(other_chat)
    queued.pop()()
    assert "origin timeout" not in window.chat_panel.chat_display.toPlainText()
    assert any("Origin project content" in message["content"] for message in seen)
    assert all("Wrong project content" not in message["content"] for message in seen)
    data = window.trace_service.detail(identity_id)
    assert data["request"]["conversation_id"] == origin
    assert data["request"]["project_id"] == project.id
    assert data["request"]["outcome"] == "provider_failed"
    window.chat_panel.load_session(window.chat_manager.get_session(origin))
    assert "origin timeout" in window.chat_panel.chat_display.toPlainText()


def test_context_exception_and_unavailable_client_persist(review_window, monkeypatch):
    window, _ = review_window
    setup_chat(window, monkeypatch, "unused")
    def fail(*args, **kwargs):
        raise ValueError("context failure")
    window.chat_manager.context_engine.build_context = fail
    window._on_chat_message_sent("Request")
    data = window.trace_service.detail(window.trace_service.list_requests()[0]["id"])
    assert data["request"]["outcome"] == "context_failed"
    assert not any(e["code"].startswith("model.") for e in data["events"])
    window.llm_client = None
    window._on_chat_message_sent("Another request")
    assert window.trace_service.list_requests()[0]["outcome"] == "provider_unavailable"


def test_diagnostics_viewer_defaults_to_no_content_and_persists_settings(review_window):
    window, _ = review_window
    trace = window.trace_service
    identity = trace.begin(window.chat_manager.active_session_id, None, agent="general")
    trace.save_settings(replace(trace.settings, responses=True))
    trace.capture(identity.request_id, "responses", "PRIVATE STORY CONTENT")
    trace.finish(identity.request_id, "responded")
    viewer = DiagnosticsDialog(trace, window.chat_manager.active_session_id, window)
    assert not viewer.include_content.isChecked()
    assert "PRIVATE STORY CONTENT" not in viewer.timeline.toPlainText()
    viewer.include_content.setChecked(True)
    assert "PRIVATE STORY CONTENT" in viewer.timeline.toPlainText()
    viewer.capture["prompts"].setChecked(True)
    viewer.days.setValue(7)
    viewer.save_settings()
    assert RequestTraceService(trace.database).settings.prompts
    assert trace.settings.retention_days == 7
    viewer.close()


def test_closing_failed_review_preserves_rollback_failure_outcome(review_window, monkeypatch):
    window, root = review_window
    identity, batch, before, after = traced_review(window, root)
    batch.conflict = "Rollback failed; inspect files"
    window.trace_service.finish(identity.request_id, "rollback_failed")
    window.review_controller.cancel(batch.id)
    data = window.trace_service.detail(identity.request_id)
    assert data["request"]["outcome"] == "rollback_failed"
    event = data["events"][-1]
    assert event["code"] == "review.canceled"
    assert "no proposed changes" not in event["message"]


def test_successful_writes_with_cleanup_failure_are_recorded_truthfully(review_window, monkeypatch):
    window, root = review_window
    identity, batch, before, after = traced_review(window, root)
    batch.reviews[0].decide_all(HunkState.ACCEPTED)
    def fail(*args, **kwargs):
        raise OSError("backup cleanup blocked")
    monkeypatch.setattr(window.file_tools, "_cleanup", fail)
    assert not window.review_controller.apply(batch.id)
    assert (root / "chapter.md").read_text(encoding="utf-8") == after
    assert window.trace_service.detail(identity.request_id)["request"]["outcome"] == "applied_cleanup_failed"
    window.review_controller.cancel(batch.id)
    assert window.trace_service.detail(identity.request_id)["request"]["outcome"] == "applied_cleanup_failed"


def test_request_storage_failure_is_visible_without_blocking_safe_review(review_window):
    window, root = review_window
    identity, batch, before, after = traced_review(window, root)
    batch.reviews[0].decide_all(HunkState.ACCEPTED)
    with window.trace_service.database.read() as db:
        db.execute("PRAGMA query_only=ON")
    assert window.review_controller.apply(batch.id)
    assert "Diagnostics storage unavailable" in window.statusBar().currentMessage()
    assert (root / "chapter.md").read_text(encoding="utf-8") == after
    with window.trace_service.database.read() as db:
        db.execute("PRAGMA query_only=OFF")


@pytest.mark.parametrize("include_content", [False, True])
def test_export_saves_only_reviewed_preview_with_explicit_content_choice(review_window, monkeypatch, tmp_path, include_content):
    from PySide6.QtWidgets import QDialog, QFileDialog, QPlainTextEdit
    window, _ = review_window
    trace = window.trace_service
    identity = trace.begin(window.chat_manager.active_session_id, None, agent="general")
    trace.save_settings(replace(trace.settings, responses=True))
    trace.capture(identity.request_id, "responses", "PRIVATE STORY")
    trace.finish(identity.request_id, "responded")
    viewer = DiagnosticsDialog(trace, window.chat_manager.active_session_id, window)
    viewer.include_content.setChecked(include_content)
    def review_preview(dialog):
        editor = dialog.findChild(QPlainTextEdit)
        original = editor.toPlainText()
        assert ("PRIVATE STORY" in original) == include_content
        editor.setPlainText(original.replace("PRIVATE STORY", "[removed by user]"))
        return QDialog.Accepted
    monkeypatch.setattr(QDialog, "exec", review_preview)
    destination = tmp_path / "export.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(destination), "JSON"))
    viewer.preview_export()
    data = json.loads(destination.read_text(encoding="utf-8"))
    assert data["content_included"] is include_content
    assert "PRIVATE STORY" not in json.dumps(data)
    if include_content:
        assert data["content"][0]["text"] == "[removed by user]"
    else:
        assert "text" not in data["content"][0]
    viewer.close()
