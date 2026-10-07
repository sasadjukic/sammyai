"""Bounded, local request evidence. This service has no model or file-write tools.

Writes fail open for the *workflow*, but never claim a complete trace after a
storage failure. Reads/control operations raise so the viewer can explain them.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from functools import wraps
from importlib.metadata import PackageNotFoundError, version
import json
import logging
import re
import traceback
from uuid import uuid4

from .proposal_protocol import PROMPT_VERSION

logger = logging.getLogger(__name__)
CONTENT_LIMIT = 128_000
COLLECTION_LIMIT = 200


def now():
    return datetime.now(timezone.utc).isoformat()


def exception_evidence(error, depth=0):
    evidence = {
        "exception_type": type(error).__name__, "explanation": str(error),
        "traceback": [{"file": frame.filename, "line": frame.lineno, "function": frame.name}
                      for frame in traceback.extract_tb(error.__traceback__)],
    }
    for name in ("request_id", "status_code"):
        value = getattr(error, name, None)
        if isinstance(value, (str, int)):
            evidence[name] = value
    if isinstance(error, json.JSONDecodeError):
        # Keep structural evidence even when content capture is disabled. Never
        # persist error.doc here: the proposal has its own opt-in capture policy.
        evidence["json_error"] = {
            "message": error.msg, "line": error.lineno,
            "column": error.colno, "position": error.pos,
        }
    cause = error.__cause__ or error.__context__
    if cause is not None and cause is not error and depth < 3:
        evidence["caused_by"] = exception_evidence(cause, depth + 1)
    return evidence


@dataclass(frozen=True)
class CaptureSettings:
    prompts: bool = False
    responses: bool = False
    drafts: bool = False
    failed_proposals: bool = False
    retention_days: int = 30
    max_requests: int = 1000


@dataclass(frozen=True)
class RequestIdentity:
    request_id: str
    conversation_id: str | None
    project_id: str | None
    message_id: str
    run_id: str


@dataclass(frozen=True)
class RequestUpdate:
    identity: RequestIdentity
    message: str


def best_effort(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except Exception as error:
            self.storage_error = f"Diagnostics storage unavailable ({type(error).__name__}); this timeline may be incomplete."
            self._gap = True
            # Exception messages can contain story text or credentials.
            logger.warning("Diagnostic storage operation failed: %s", type(error).__name__)
            return None
    return guarded


class RequestTraceService:
    def __init__(self, database):
        self.database = database
        self.settings = CaptureSettings()
        self.storage_error = None
        self._gap = False
        self._secrets = set()
        self._initialize()

    @best_effort
    def _initialize(self):
        with self.database.read() as db:
            row = db.execute("SELECT value FROM application_state WHERE key='diagnostic_settings'").fetchone()
        if row:
            self.settings = CaptureSettings(**json.loads(row["value"]))

    def register_secret(self, secret):
        if isinstance(secret, str) and secret:
            self._secrets.add(secret)

    def redact(self, text):
        text = str(text)
        for secret in sorted(self._secrets, key=len, reverse=True):
            text = text.replace(secret, "[REDACTED]")
        text = re.sub(r"(?i)(bearer\s+)[^\s\"',;]+", r"\1[REDACTED]", text)
        text = re.sub(r"(?i)((?:api[_-]?key|authorization|password|access[_-]?token|secret)[\"']?\s*[:=]\s*[\"']?)[^\s\"',;}]+", r"\1[REDACTED]", text)
        text = re.sub(r"\b(?:sk-[A-Za-z0-9_-]{8,}|AIza[A-Za-z0-9_-]{20,})", "[REDACTED]", text)
        text = re.sub(r"(https?://)[^\s/@:]+:[^\s/@]+@", r"\1[REDACTED]@", text)
        return text

    def _bounded(self, value, depth=0):
        if depth > 8:
            return "[depth limit]"
        if isinstance(value, dict):
            result = {}
            for key, item in list(value.items())[:COLLECTION_LIMIT]:
                name = str(key)
                if re.search(r"(?i)(api.?key|authorization|password|secret|access.?token)", name):
                    result[name] = "[REDACTED]"
                else:
                    result[self.redact(name)[:200]] = self._bounded(item, depth + 1)
            if len(value) > COLLECTION_LIMIT:
                result["omitted_entries"] = len(value) - COLLECTION_LIMIT
            return result
        if isinstance(value, (list, tuple)):
            items = [self._bounded(item, depth + 1) for item in value[:COLLECTION_LIMIT]]
            if len(value) > COLLECTION_LIMIT:
                items.append({"omitted_entries": len(value) - COLLECTION_LIMIT})
            return items
        if value is None or isinstance(value, (int, float, bool)):
            return value
        text = self.redact(value)
        return text if len(text) <= 4000 else text[:4000] + " [truncated]"

    def _json(self, value):
        return json.dumps(self._bounded(value), ensure_ascii=False)

    def begin(self, conversation_id, project_id, *, agent, model=None):
        identity = RequestIdentity(str(uuid4()), conversation_id, project_id, str(uuid4()), str(uuid4()))
        self._insert_request(identity, agent, model)
        return identity

    @best_effort
    def _insert_request(self, identity, agent, model):
        try:
            app_version = version("sammyai")
        except PackageNotFoundError:
            app_version = "unknown"
        metadata = {"agent": agent, "model": model, "app_version": app_version,
                    "build": "unknown", "prompt_version": PROMPT_VERSION,
                    "capture_settings": asdict(self.settings)}
        with self.database.transaction() as db:
            db.execute("INSERT INTO diagnostic_requests VALUES (?,?,?,?,?,?,?,?,?,?)", (
                identity.request_id, identity.conversation_id, identity.project_id,
                identity.message_id, identity.run_id, now(), now(), "running", int(self._gap), self._json(metadata)))
        self.event(identity.request_id, "request.submitted", "Request submitted; no files changed.")
        self.prune()

    @best_effort
    def event(self, request_id, code, message, *, step_id=None, details=None):
        if not request_id:
            return
        with self.database.transaction() as db:
            # Deleted requests must never be resurrected by a late worker.
            if not db.execute("SELECT 1 FROM diagnostic_requests WHERE id=?", (request_id,)).fetchone():
                return
            db.execute("INSERT INTO diagnostic_events(id,request_id,step_id,created_at,code,message,details_json) VALUES (?,?,?,?,?,?,?)",
                       (str(uuid4()), request_id, step_id, now(), code, self.redact(message)[:4000], self._json(details or {})))
            db.execute("UPDATE diagnostic_requests SET updated_at=?, incomplete=MAX(incomplete,?) WHERE id=?", (now(), int(self._gap), request_id))

    @best_effort
    def finish(self, request_id, outcome):
        if not request_id:
            return
        with self.database.transaction() as db:
            db.execute("""UPDATE diagnostic_requests SET outcome=?,updated_at=?,incomplete=MAX(incomplete,?)
                WHERE id=? AND NOT (?='canceled' AND outcome IN ('rollback_failed','applied_cleanup_failed'))""",
                (outcome, now(), int(self._gap), request_id, outcome))

    @best_effort
    def fail_unfinished(self, request_id):
        with self.database.transaction() as db:
            db.execute("UPDATE diagnostic_requests SET outcome='app_failed',updated_at=? WHERE id=? AND outcome='running'", (now(), request_id))
            db.execute("UPDATE diagnostic_steps SET outcome='failed',ended_at=? WHERE request_id=? AND outcome='running'", (now(), request_id))

    @best_effort
    def start_step(self, request_id, name, *, parent_step_id=None, attempt=1):
        step_id = str(uuid4())
        with self.database.transaction() as db:
            if not db.execute("SELECT 1 FROM diagnostic_requests WHERE id=?", (request_id,)).fetchone():
                return
            db.execute("INSERT INTO diagnostic_steps VALUES (?,?,?,?,?,?,?,?,?)", (
                step_id, request_id, parent_step_id, name, attempt, now(), None, None, "running"))
        return step_id

    @best_effort
    def end_step(self, step_id, outcome, duration_ms=None):
        if step_id:
            with self.database.transaction() as db:
                db.execute("UPDATE diagnostic_steps SET ended_at=?,duration_ms=?,outcome=? WHERE id=?", (now(), duration_ms, outcome, step_id))

    def exception(self, request_id, code, error, *, step_id=None):
        # No frame locals or source-code lines: either may contain credentials.
        self.event(request_id, code, f"{type(error).__name__}: {error}", step_id=step_id, details=exception_evidence(error))

    @best_effort
    def capture(self, request_id, kind, text, *, step_id=None):
        if not request_id:
            return
        enabled = bool(getattr(self.settings, kind))
        text = str(text)
        with self.database.transaction() as db:
            if not db.execute("SELECT 1 FROM diagnostic_requests WHERE id=?", (request_id,)).fetchone():
                return
            db.execute("INSERT INTO diagnostic_content VALUES (?,?,?,?,?,?,?,?)", (
                str(uuid4()), request_id, step_id, kind, int(enabled), int(enabled and len(text) > CONTENT_LIMIT),
                len(text), self.redact(text)[:CONTENT_LIMIT] if enabled else None))

    @best_effort
    def link(self, request_id, entity_id, kind):
        if request_id:
            with self.database.transaction() as db:
                if db.execute("SELECT 1 FROM diagnostic_requests WHERE id=?", (request_id,)).fetchone():
                    db.execute("INSERT OR IGNORE INTO diagnostic_links VALUES (?,?,?)", (entity_id, request_id, kind))

    @best_effort
    def request_for(self, entity_id):
        with self.database.read() as db:
            row = db.execute("SELECT request_id FROM diagnostic_links WHERE entity_id=?", (entity_id,)).fetchone()
        return row["request_id"] if row else None

    @best_effort
    def recover_interrupted(self):
        with self.database.read() as db:
            rows = db.execute("SELECT id FROM diagnostic_requests WHERE outcome IN ('running','pending_review','applying')").fetchall()
        for row in rows:
            self.event(row["id"], "request.interrupted", "Application stopped before this request or review finished. File-write outcome may be unknown; inspect files. No work was replayed.")
            self.finish(row["id"], "interrupted")
        with self.database.transaction() as db:
            db.execute("UPDATE diagnostic_steps SET outcome='interrupted',ended_at=? WHERE outcome='running'", (now(),))
        self.prune()

    def list_requests(self, conversation_id=None):
        with self.database.read() as db:
            query = "SELECT * FROM diagnostic_requests"
            args = ()
            if conversation_id is not None:
                query += " WHERE conversation_id=?"
                args = (conversation_id,)
            rows = db.execute(query + " ORDER BY created_at DESC LIMIT 10000", args).fetchall()
        return [dict(row) for row in rows]

    def detail(self, request_id, *, include_content=False):
        with self.database.read() as db:
            row = db.execute("SELECT * FROM diagnostic_requests WHERE id=?", (request_id,)).fetchone()
            if row is None:
                return None
            request = dict(row)
            request["metadata"] = json.loads(request.pop("metadata_json"))
            result = {"schema_version": 1, "request": request}
            for name in ("steps", "events", "content", "links"):
                order = " ORDER BY sequence" if name == "events" else ""
                columns = "*" if name != "content" or include_content else "id,request_id,step_id,kind,captured,truncated,char_count"
                result[name] = [dict(item) for item in db.execute(f"SELECT {columns} FROM diagnostic_{name} WHERE request_id=?" + order, (request_id,))]
            for event in result["events"]:
                event["details"] = json.loads(event.pop("details_json"))
            result["content_included"] = include_content
            return result

    def export_preview(self, request_id, *, include_content=False):
        return self.redact(json.dumps(self.detail(request_id, include_content=include_content), ensure_ascii=False, indent=2))

    def save_settings(self, settings):
        if not 1 <= settings.retention_days <= 3650 or not 1 <= settings.max_requests <= 10000:
            raise ValueError("Retention must be 1–3650 days and 1–10000 requests")
        with self.database.transaction() as db:
            db.execute("INSERT INTO application_state VALUES ('diagnostic_settings',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (json.dumps(asdict(settings)), now()))
        self.settings = settings
        self.prune()

    def delete(self, request_id=None):
        with self.database.transaction() as db:
            db.execute("PRAGMA secure_delete=ON")
            if request_id:
                db.execute("DELETE FROM diagnostic_requests WHERE id=?", (request_id,))
            else:
                db.execute("DELETE FROM diagnostic_requests")
        with self.database.read() as db:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def prune(self):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.settings.retention_days)).isoformat()
        with self.database.transaction() as db:
            db.execute("PRAGMA secure_delete=ON")
            db.execute("DELETE FROM diagnostic_requests WHERE outcome NOT IN ('running','pending_review','applying') AND updated_at < ?", (cutoff,))
            db.execute("""DELETE FROM diagnostic_requests WHERE outcome NOT IN ('running','pending_review','applying')
                AND id NOT IN (SELECT id FROM diagnostic_requests ORDER BY created_at DESC LIMIT ?)""", (self.settings.max_requests,))

    def conversation_notices(self, conversation_id):
        with self.database.read() as db:
            rows = db.execute("""SELECT e.* FROM diagnostic_events e JOIN diagnostic_requests r ON r.id=e.request_id
                WHERE r.conversation_id=? ORDER BY e.sequence""", (conversation_id,)).fetchall()
        proposal_notices = {
            (row["request_id"], row["step_id"]) for row in rows
            if row["code"] == "notice.proposal" and row["message"].startswith("File proposal rejected:")
        }
        # Chat restores the user-facing rejection once. Technical errors remain
        # in the full timeline, or in chat if their friendly notice was not saved.
        return [dict(row) for row in rows
                if row["code"].startswith(("notice.", "error.", "request.interrupted"))
                and not (row["code"] in {"error.proposal_parse", "error.proposal_validation"}
                         and (row["request_id"], row["step_id"]) in proposal_notices)]

    @best_effort
    def record_context(self, identity, prepared, *, step_id=None, engine=None):
        result = prepared.context_result
        if result is None:
            details = {"retrieval_status": prepared.retrieval_status, "retrieval_error": prepared.retrieval_error,
                       "context_budget": None, "source_evidence": "unavailable"}
            notices = ("Retrieval failed; continuing without retrieved context.",) if prepared.retrieval_status == "failed" else ()
        else:
            details = {
                "total_tokens": result.total_tokens, "max_tokens": result.max_tokens,
                "truncated": result.truncated, "retrieval_status": result.retrieval_status,
                "retrieval_sources": result.retrieval_sources, "retrieval_error": result.retrieval_error,
                "references": [{"reference": ref.reference, "resolved": ref.relative_path, "error": ref.error} for ref in result.references],
                "files": [{"path": item.relative_path, "source_hash": item.source_hash,
                           "complete": item.complete, "ranges": item.visible_ranges} for item in result.file_snapshots],
                "memory_ids": result.memory_ids, "summary_ids": result.summary_ids,
                "sync": asdict(result.sync_report),
                "file_policy": asdict(engine.file_context_policy) if engine and hasattr(engine, "file_context_policy") else None,
                "errors": result.diagnostic_errors,
            }
            notices = result.notices
        self.event(identity.request_id, "context.prepared", "Context prepared; inspect references, limits and retrieval outcome.", step_id=step_id, details=details)
        if details.get("retrieval_status") == "failed":
            self.event(identity.request_id, "error.retrieval", "Retrieval failed; this is not an empty search result.", step_id=step_id, details={"error": details.get("retrieval_error")})
        for notice in notices:
            self.event(identity.request_id, "notice.context", notice, step_id=step_id)


def inspect_proposal(text):
    """Offline parser fixture inspection only; deliberately has no file tools."""
    from .agent_workflows import AgentWorkflowService
    try:
        _, directive = AgentWorkflowService._extract_change_directive(text)
        return {"outcome": "parsed" if directive is not None else "no_proposal",
                "file_count": len(directive.get("files", [])) if directive else 0}
    except (ValueError, TypeError) as error:
        return {"outcome": "rejected", "error_type": type(error).__name__, "message": str(error)}
