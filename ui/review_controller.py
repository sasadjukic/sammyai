"""Coordinate tab-bound reviews and the existing safe apply/history services."""

from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QTextCursor, QTextDocument

from editing.change_sets import ChangeSet, FileChange, FileChangeKind, FileChangeRequest, content_hash
from editing.review_session import ReviewSession
from sammyai_core.file_tools import FileToolError
from ui.inline_review import InlineReviewWidget


def display_text(text):
    """Compare raw file snapshots with Qt's normalized plain-text representation."""
    document = QTextDocument()
    document.setPlainText(text)
    return document.toPlainText()


@dataclass(frozen=True)
class BufferSnapshot:
    text: str
    revision: int
    path: str | None
    disk: bytes | None


@dataclass
class ReviewBatch:
    id: str
    reviews: tuple[ReviewSession, ...]
    snapshots: dict[str, BufferSnapshot]
    change_set: ChangeSet | None = None
    temporary_documents: set[str] = field(default_factory=set)
    conflict: str | None = None

    @property
    def pending_count(self):
        return sum(review.pending_count for review in self.reviews)


class ReviewController(QObject):
    applied = Signal(object)
    finished = Signal(str)

    def __init__(self, workspace, file_tools=None, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.file_tools = file_tools
        self.batches: dict[str, ReviewBatch] = {}
        workspace.document_closing.connect(self._document_closing)

    def batch_for_document(self, document_id):
        return next((batch for batch in self.batches.values()
                     if any(review.target_document_id == document_id for review in batch.reviews)), None)

    def _snapshot(self, session, *, capture_disk=False):
        editor = self.workspace.editor_for_session(session.session_id)
        disk = None
        if capture_disk and session.path is not None and session.path.exists():
            disk = session.path.read_bytes()
        return BufferSnapshot(editor.toPlainText(), editor.document().revision(), session.normalized_path, disk)

    def start_change_set(self, change_set, *, agent_id=None, chat_session_id=None):
        if self.file_tools is None:
            raise FileToolError("Project file tools are unavailable")
        resolved = self.file_tools.validate(change_set)
        # Preflight every tab before opening or locking any of them.
        for change, path in resolved:
            for session in self.workspace.sessions_for_path(path):
                if self.workspace.review_for_session(session.session_id):
                    raise FileToolError(f"Finish or cancel the existing review of {path.name} first")
                if self.workspace.is_modified(session.session_id):
                    raise FileToolError(f"Save or discard unsaved edits in {path.name} before requesting another proposal")
                editor = self.workspace.editor_for_session(session.session_id)
                if editor.toPlainText() != display_text(change.before_content or ""):
                    raise FileToolError(f"The open buffer for {path.name} no longer matches the proposal; reopen it and request a new proposal")
        reviews, snapshots, temporary = [], {}, set()
        for change, path in resolved:
            already_open = bool(self.workspace.sessions_for_path(path))
            session = self.workspace.open_document(path, display_text(change.before_content or ""))
            if change.kind == FileChangeKind.CREATE and not already_open:
                temporary.add(session.session_id)
            snapshots[session.session_id] = self._snapshot(session)
            reviews.append(ReviewSession(change_set.id, session.session_id, session.normalized_path, change, agent_id, chat_session_id))
        batch = ReviewBatch(change_set.id, tuple(reviews), snapshots, change_set, temporary)
        self._show(batch, change_set.description)
        return batch

    def start_buffer(self, document_id, original, proposed, description, *, agent_id=None, chat_session_id=None):
        session = self.workspace.session(document_id)
        editor = self.workspace.editor_for_session(document_id)
        if session is None or editor is None:
            raise FileToolError("The originating document is no longer open")
        if self.batch_for_document(document_id):
            raise FileToolError("Finish or cancel this document's current review first")
        if editor.toPlainText() != original:
            raise FileToolError("The document changed after this proposal was requested; request a new proposal")
        if original == proposed:
            self.finished.emit("The proposal contains no changes.")
            return None
        # Clean project files take the same atomic apply path as structured agents.
        project = self.file_tools.project_service.active_project if self.file_tools else None
        if project and session.path and not self.workspace.is_modified(document_id):
            try:
                relative_path = session.path.relative_to(project.root_path.resolve()).as_posix()
            except ValueError:
                relative_path = None
            if relative_path is not None:
                raw_original = self.file_tools.read_text(relative_path)
                if display_text(raw_original) != original:
                    raise FileToolError("The file changed on disk; reopen it and request a new proposal")
                # Preserve the source newline convention when DBE started from Qt text.
                disk_proposed = proposed.replace("\n", "\r\n") if "\r\n" in raw_original and "\r" not in proposed else proposed
                source = self.file_tools.prepare_change_set(
                    [FileChangeRequest.write(relative_path, disk_proposed)], description=description,
                )
                if source.changes[0].before_content != raw_original:
                    raise FileToolError("The file changed while the review was opening")
                return self.start_change_set(source, agent_id=agent_id, chat_session_id=chat_session_id)
        change = FileChange(session.display_name, FileChangeKind.UPDATE, original, proposed, content_hash(original), content_hash(proposed))
        batch_id = str(uuid4())
        review = ReviewSession(batch_id, document_id, session.normalized_path, change, agent_id, chat_session_id)
        batch = ReviewBatch(batch_id, (review,), {document_id: self._snapshot(session, capture_disk=True)})
        self._show(batch, description)
        return batch

    def _show(self, batch, description):
        self.batches[batch.id] = batch
        for review in batch.reviews:
            widget = InlineReviewWidget(review, description)
            widget.decisions_changed.connect(lambda batch_id=batch.id: self._refresh(batch_id))
            widget.apply_requested.connect(lambda batch_id=batch.id: self.apply(batch_id))
            widget.cancel_requested.connect(lambda batch_id=batch.id: self.cancel(batch_id))
            self.workspace.show_review(review.target_document_id, widget)
        self.workspace.activate_document(batch.reviews[0].target_document_id)
        self._refresh(batch.id)

    def _refresh(self, batch_id):
        batch = self.batches.get(batch_id)
        if batch is None:
            return
        for review in batch.reviews:
            widget = self.workspace.review_for_session(review.target_document_id)
            if widget:
                widget.set_batch_status(batch.pending_count, len(batch.reviews), conflict=batch.conflict, writes_files=batch.change_set is not None)

    def _validate_buffers(self, batch):
        for review in batch.reviews:
            document_id = review.target_document_id
            session = self.workspace.session(document_id)
            editor = self.workspace.editor_for_session(document_id)
            snapshot = batch.snapshots[document_id]
            if session is None or editor is None:
                raise FileToolError("A reviewed document was closed")
            if session.normalized_path != snapshot.path:
                raise FileToolError("A reviewed document was renamed")
            if editor.toPlainText() != snapshot.text or editor.document().revision() != snapshot.revision:
                raise FileToolError("A reviewed buffer changed")
            if batch.change_set is None and session.path is not None:
                current = session.path.read_bytes() if session.path.exists() else None
                if current != snapshot.disk:
                    raise FileToolError("The draft's file changed on disk")

    def apply(self, batch_id):
        batch = self.batches.get(batch_id)
        if batch is None or batch.pending_count or batch.conflict:
            return False
        changes = tuple(change for review in batch.reviews if (change := review.final_change()) is not None)
        if not changes:
            self.cancel(batch_id, message="All proposed changes rejected; no text or files changed.")
            return True
        try:
            self._validate_buffers(batch)
            if batch.change_set is not None:
                # Validate the full proposal, including rejected files, and retain
                # original preconditions in the synthesized accepted change set.
                self.file_tools.validate(batch.change_set)
                accepted = ChangeSet(batch.change_set.project_id, batch.change_set.description, changes)
                applied = self.file_tools.apply(accepted)
            else:
                applied = None
                editor = self.workspace.editor_for_session(batch.reviews[0].target_document_id)
                cursor = QTextCursor(editor.document())
                cursor.beginEditBlock()
                cursor.select(QTextCursor.Document)
                cursor.insertText(changes[0].after_content)
                cursor.endEditBlock()
        except (FileToolError, OSError, ValueError) as error:
            batch.conflict = str(error)
            self._refresh(batch_id)
            return False
        self._finish(batch, applied_paths={change.relative_path for change in changes})
        if applied is not None:
            self.applied.emit(applied)
        self.finished.emit("Reviewed changes applied. Use change-set history to undo." if applied else "Reviewed changes applied to the draft. Use Undo to revert.")
        return True

    def cancel(self, batch_id, *, message="Review canceled; no proposed changes applied.", closing_document=None):
        batch = self.batches.get(batch_id)
        if batch is not None:
            self._finish(batch, closing_document=closing_document)
            self.finished.emit(message)

    def _finish(self, batch, *, applied_paths=frozenset(), closing_document=None):
        self.batches.pop(batch.id, None)
        for review in batch.reviews:
            document_id = review.target_document_id
            self.workspace.hide_review(document_id)
            if (document_id in batch.temporary_documents and document_id != closing_document
                    and review.change.relative_path not in applied_paths
                    and not self.workspace.is_modified(document_id)):
                self.workspace.close_document(document_id)

    def _document_closing(self, document_id):
        batch = self.batch_for_document(document_id)
        if batch:
            self.cancel(batch.id, closing_document=document_id)

    def cancel_all(self):
        for batch_id in tuple(self.batches):
            self.cancel(batch_id)
