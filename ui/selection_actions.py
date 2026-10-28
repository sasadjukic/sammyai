"""Selection capture, asynchronous writing, and routing into the existing review UI."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from threading import Event
import time
from uuid import uuid4

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QInputDialog

from editing.change_sets import content_hash
from llm.chat_manager import MessageRole
from sammyai_core.selection_actions import (
    SelectionAction, SelectionActionRequest, SelectionSnapshot, parse_result,
)


def disk_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if path and Path(path).exists() else None


def python_position(text, qt_position):
    """Qt cursors count UTF-16 code units; Python slices count code points."""
    return len(text.encode("utf-16-le")[:qt_position * 2].decode("utf-16-le"))


@dataclass
class PendingSelection:
    request: SelectionActionRequest
    identity: object
    canceled: Event


class SelectionActionController(QObject):
    completed = Signal(object, object, object)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.workspace = window.editor_workspace
        self.pending = None
        self.workspace.context_menus.register("editor", self.populate_menu)
        self.workspace.selection_changed.connect(self.refresh_reference)
        self.workspace.active_document_changed.connect(lambda session: self.refresh_reference(session.session_id if session else ""))
        self.completed.connect(self._complete)

    def bind_panel(self, panel):
        panel.input_field.context_menus = self.workspace.context_menus
        panel.selection_message_sent.connect(self.send_reference)
        panel.cancel_selection_requested.connect(self.cancel)
        self.refresh_reference(self.workspace.active_session().session_id)

    def capture(self, document_id, *, insertion=False):
        session = self.workspace.session(document_id)
        editor = self.workspace.editor_for_session(document_id)
        if session is None or editor is None or self.workspace.review_for_session(document_id):
            raise ValueError("Finish the review or reopen the document before selecting a passage.")
        text, cursor = editor.toPlainText(), editor.textCursor()
        start = end = python_position(text, cursor.position())
        if not insertion:
            start = python_position(text, cursor.selectionStart())
            end = python_position(text, cursor.selectionEnd())
            if start == end:
                raise ValueError("Select a passage first.")
        return SelectionSnapshot(
            document_id, session.normalized_path, session.display_name,
            content_hash(session.clean_snapshot), text, editor.document().revision(),
            disk_hash(session.path), start, end, session.format_id,
        )

    def refresh_reference(self, document_id):
        panel = getattr(self.window, "chat_panel", None)
        session = self.workspace.active_session()
        if not panel or panel._history_busy or panel.selection_pinned or session is None or session.session_id != document_id:
            return
        try:
            snapshot = self.capture(document_id)
        except (ValueError, OSError):
            snapshot = None
        panel.set_selection_reference(snapshot)

    def populate_menu(self, menu, editor):
        document_id = editor.property("documentSessionId")
        if not document_id:
            return
        panel = getattr(self.window, "chat_panel", None)
        available = not editor.isReadOnly() and not (panel and panel._history_busy)
        selected = editor.textCursor().hasSelection()
        menu.addSeparator()
        attach = menu.addAction("Add Selection to Chat")
        attach.setEnabled(available and selected)
        attach.triggered.connect(lambda: self.attach(document_id))
        for action in SelectionAction:
            if action == SelectionAction.CUSTOM:
                continue
            item = menu.addAction(action.label)
            item.setData(action.value)
            item.setEnabled(available and (selected or action == SelectionAction.CONTINUE))
            item.triggered.connect(lambda checked=False, action=action: self.start_action(document_id, action))

    def attach(self, document_id):
        self.window._show_chat_panel()
        try:
            snapshot = self.capture(document_id)
        except (ValueError, OSError) as error:
            self.window.chat_panel.set_status(str(error))
            return
        self.window.chat_panel.set_selection_reference(snapshot, pinned=True)
        self.window.chat_panel.input_field.setFocus()

    def start_action(self, document_id, action):
        try:
            snapshot = self.capture(document_id, insertion=action == SelectionAction.CONTINUE)
            instruction = ""
            if action == SelectionAction.TONE:
                instruction, accepted = QInputDialog.getText(self.window, "Change Tone", "Desired tone (for example, tense or playful):")
                if not accepted or not instruction.strip():
                    return
            self.start(snapshot, action, instruction)
        except (OSError, ValueError) as error:
            self.window.statusBar().showMessage(str(error))

    def send_reference(self, message, snapshot):
        self.start(snapshot, SelectionAction.CUSTOM, message)

    def validate_snapshot(self, snapshot, project_id):
        session = self.workspace.session(snapshot.document_id)
        editor = self.workspace.editor_for_session(snapshot.document_id)
        if (session is None or editor is None or session.normalized_path != snapshot.path
                or self.window._active_chat_project_id() != project_id
                or editor.document().revision() != snapshot.revision
                or editor.toPlainText() != snapshot.original
                or disk_hash(snapshot.path) != snapshot.disk_hash):
            raise ValueError("This passage is stale: its document or project changed. Select it again and regenerate.")
        if self.workspace.review_for_session(snapshot.document_id):
            raise ValueError("Finish or cancel this document's current review first.")

    def start(self, snapshot, action, instruction=""):
        window = self.window
        window._show_chat_panel()
        panel = window.chat_panel
        if self.pending or panel._history_busy:
            panel.set_status("Wait for the current request or cancel the selection action.")
            return
        project_id = window._active_chat_project_id()
        try:
            self.validate_snapshot(snapshot, project_id)
        except (ValueError, OSError) as error:
            panel.add_system_message(str(error))
            return
        if window.chat_manager.get_active_session() is None:
            window._on_new_chat_requested()
        request = SelectionActionRequest(snapshot, action, window.chat_manager.active_session_id, project_id, instruction)
        client, trace = window.llm_client, window.trace_service
        trace.register_secret(getattr(client, "api_key", None))
        identity = trace.begin(request.chat_session_id, project_id, agent="selection",
                               model={"provider": getattr(client, "provider", None), "name": getattr(client, "model_name", None)})
        window._active_request_id = identity.request_id
        pending = PendingSelection(request, identity, Event())
        self.pending = pending
        label = f"{instruction or action.label} [{snapshot.label}]"
        try:
            self._save(pending, MessageRole.USER, label)
        except Exception as error:
            self._complete(pending, None, ("chat_persistence_failed", str(error)))
            return
        panel.add_user_message(label)
        panel.set_thinking(True)
        panel.set_selection_running(True)
        panel.set_status(f"{action.label}: {snapshot.label}…")
        panel.refresh_history()
        trace.event(identity.request_id, "selection.captured", "Selected passage and bounded context captured.", details={
            "action": action.value, "document_id": snapshot.document_id, "path": snapshot.path,
            "clean_hash": snapshot.clean_hash, "snapshot_hash": content_hash(snapshot.original),
            "range": [snapshot.start, snapshot.end], "lines": [snapshot.line_start, snapshot.line_end],
            "format_id": snapshot.format_id, "style_profile_id": request.style_profile_id,
        })
        if client is None:
            self._complete(pending, None, ("provider_unavailable", "Configure a model before using selection actions."))
            return

        def worker():
            step = None
            phase = "provider_failed"
            try:
                with window._llm_lock:
                    if pending.canceled.is_set():
                        return
                    step = trace.start_step(identity.request_id, "model.selection")
                    started = time.monotonic()
                    prompt, messages = request.system_prompt(), request.messages()
                    trace.capture(identity.request_id, "prompts", json.dumps({"system_prompt": prompt, "messages": messages}, ensure_ascii=False), step_id=step)
                    trace.event(identity.request_id, "model.started", "Generating selection result.", step_id=step)
                    original_prompt = client.system_prompt
                    try:
                        client.system_prompt = prompt
                        response = client.chat(messages)
                        metadata = dict(getattr(client, "last_response_metadata", {}) or {})
                    finally:
                        client.system_prompt = original_prompt
                if pending.canceled.is_set():
                    trace.end_step(step, "canceled", (time.monotonic() - started) * 1000)
                    return
                trace.capture(identity.request_id, "responses", response or "", step_id=step)
                trace.event(identity.request_id, "model.responded", "Selection model call returned.", step_id=step, details=metadata)
                trace.end_step(step, "responded", (time.monotonic() - started) * 1000)
                phase = "invalid_result"
                step = trace.start_step(identity.request_id, "selection.validation")
                result = parse_result(response, request, metadata)
                trace.end_step(step, "validated")
                self.completed.emit(pending, result, None)
            except Exception as error:
                trace.end_step(step, "canceled" if pending.canceled.is_set() else phase)
                if not pending.canceled.is_set():
                    trace.exception(identity.request_id, "error.selection", error, step_id=step)
                    if phase == "invalid_result":
                        trace.capture(identity.request_id, "failed_proposals", response or "")
                    self.completed.emit(pending, None, (phase, trace.redact(error)))
        try:
            window.task_runner.submit(worker, name="selection-action")
        except Exception as error:
            self._complete(pending, None, ("app_failed", trace.redact(error)))

    def _save(self, pending, role, text):
        request, identity = pending.request, pending.identity
        message_id = identity.message_id if role == MessageRole.USER else str(uuid4())
        message = self.window.chat_manager.add_message(role, text, session_id=request.chat_session_id, metadata={
            "agent_type": "selection", "action_type": request.action.value,
            "agent_run_id": identity.run_id, "message_id": message_id,
            "request_id": identity.request_id, "document_id": request.selection.document_id,
            "selection_reference": request.selection.label, "project_id": request.project_id,
        })
        if message is None:
            raise ValueError("The originating conversation is no longer available.")
        self.window.trace_service.link(identity.request_id, message_id, role.value + "_message")

    @Slot(object, object, object)
    def _complete(self, pending, result, error):
        if self.pending is not pending or pending.canceled.is_set():
            return
        window, request = self.window, pending.request
        trace, request_id = window.trace_service, pending.identity.request_id
        outcome = "completed"
        try:
            if error:
                outcome, message = error
            else:
                outcome = "stale"
                if self.window.chat_manager.get_session(request.chat_session_id) is None:
                    raise ValueError("The originating conversation was deleted; regenerate in a new conversation.")
                self.validate_snapshot(request.selection, request.project_id)
                if result.kind == "critique":
                    message, outcome = result.text, "completed"
                else:
                    outcome = "conflicted"
                    batch = window.review_controller.start_buffer(
                        request.selection.document_id, request.selection.original, result.proposed_text(request),
                        f"{request.action.label} — {request.selection.label}", agent_id=pending.identity.run_id,
                        chat_session_id=request.chat_session_id, request_id=request_id,
                    )
                    outcome = "awaiting_review" if batch else "no_changes"
                    message = f"{request.action.label}: review the proposal in {request.selection.label}." if batch else "The proposal contains no changes."
            self._save(pending, MessageRole.ASSISTANT if not error else MessageRole.SYSTEM, message)
        except Exception as failure:
            if outcome == "completed":
                outcome = "chat_persistence_failed"
            trace.exception(request_id, "error.selection_result", failure)
            message = trace.redact(failure)
            try:
                self._save(pending, MessageRole.SYSTEM, message)
            except Exception as persistence_error:
                trace.exception(request_id, "error.chat_persistence", persistence_error)
        trace.event(request_id, "selection." + outcome, message if outcome != "completed" else "Selection critique completed.")
        trace.finish(request_id, outcome)
        self.pending = None
        panel = window.chat_panel
        panel.set_thinking(False)
        panel.set_selection_running(False)
        panel.set_status("")
        if request.chat_session_id == window.chat_manager.active_session_id:
            if outcome == "completed":
                panel.add_assistant_message(message)
            else:
                panel.add_system_message(message)
        panel.refresh_history()
        if trace.storage_error:
            panel.add_system_message(trace.storage_error)

    def cancel(self):
        pending = self.pending
        if pending is None:
            return
        pending.canceled.set()
        self.pending = None
        message = "Selection request canceled. Any late response will be ignored."
        trace = self.window.trace_service
        trace.event(pending.identity.request_id, "selection.canceled", message)
        trace.finish(pending.identity.request_id, "canceled")
        try:
            self._save(pending, MessageRole.SYSTEM, message)
        except Exception as error:
            trace.exception(pending.identity.request_id, "error.chat_persistence", error)
        panel = self.window.chat_panel
        panel.set_thinking(False)
        panel.set_selection_running(False)
        panel.set_status(message)
