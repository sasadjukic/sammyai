"""Local request timeline and explicit, editable diagnostic export preview."""
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QSplitter, QVBoxLayout,
)


class DiagnosticsDialog(QDialog):
    def __init__(self, service, conversation_id=None, parent=None):
        super().__init__(parent)
        self.service = service
        self.conversation_id = conversation_id
        self.setWindowTitle("Chat and Agent Diagnostics")
        self.setObjectName("diagnosticsDialog")
        self.resize(1000, 740)
        layout = QVBoxLayout(self)
        self.status = QLabel("Local request records. Model responses, review decisions and file changes have separate outcomes.")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        controls = QHBoxLayout()
        self.all_requests = QCheckBox("All conversations and projects")
        self.all_requests.toggled.connect(self.refresh)
        controls.addWidget(self.all_requests)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        controls.addWidget(refresh)
        layout.addLayout(controls)
        splitter = QSplitter()
        self.requests = QListWidget()
        self.requests.setAccessibleName("Recorded requests")
        self.requests.currentItemChanged.connect(self.show_request)
        splitter.addWidget(self.requests)
        self.timeline = QPlainTextEdit()
        self.timeline.setReadOnly(True)
        self.timeline.setAccessibleName("Request timeline and evidence")
        splitter.addWidget(self.timeline)
        splitter.setSizes([280, 680])
        layout.addWidget(splitter, 1)
        self.include_content = QCheckBox("Show and include captured content in export (may contain private writing)")
        self.include_content.toggled.connect(self.show_request)
        layout.addWidget(self.include_content)
        actions = QHBoxLayout()
        for label, callback in (("Preview / redact export…", self.preview_export),
                                ("Delete selected…", self.delete_selected), ("Delete all diagnostics…", self.delete_all)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        layout.addWidget(QLabel("Capture for future steps (off by default; each item is capped at 128,000 characters):"))
        settings = QHBoxLayout()
        self.capture = {}
        for key, label in (("prompts", "Prompts"), ("responses", "Responses"),
                           ("drafts", "Writer drafts / evaluations"), ("failed_proposals", "Failed proposals")):
            checkbox = QCheckBox(label)
            checkbox.setChecked(getattr(service.settings, key))
            self.capture[key] = checkbox
            settings.addWidget(checkbox)
        layout.addLayout(settings)
        retention = QHBoxLayout()
        retention.addWidget(QLabel("Retain completed records for days:"))
        self.days = QSpinBox()
        self.days.setRange(1, 3650)
        self.days.setValue(service.settings.retention_days)
        retention.addWidget(self.days)
        retention.addWidget(QLabel("Maximum requests:"))
        self.maximum = QSpinBox()
        self.maximum.setRange(1, 10000)
        self.maximum.setValue(service.settings.max_requests)
        retention.addWidget(self.maximum)
        save = QPushButton("Save capture and retention")
        save.clicked.connect(self.save_settings)
        retention.addWidget(save)
        layout.addLayout(retention)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)
        self.refresh()

    def _selected_id(self):
        item = self.requests.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _error(self, error):
        self.status.setText(f"Diagnostics unavailable: {self.service.redact(error)}. Existing editing protections still apply.")

    def refresh(self, *_):
        selected = self._selected_id()
        try:
            rows = self.service.list_requests(None if self.all_requests.isChecked() else self.conversation_id)
            self.requests.clear()
            for row in rows:
                metadata = json.loads(row["metadata_json"])
                item = QListWidgetItem(f"{row['created_at'][:19].replace('T', ' ')} UTC\n{metadata.get('agent', 'Agent')} · {row['outcome'].replace('_', ' ')}\n{row['id'][:8]}")
                item.setData(Qt.UserRole, row["id"])
                self.requests.addItem(item)
                if row["id"] == selected:
                    self.requests.setCurrentItem(item)
            if self.requests.currentItem() is None and rows:
                self.requests.setCurrentRow(0)
            if not rows:
                self.timeline.setPlainText("No diagnostic records in this view. Older conversations have no retroactive traces.")
            if self.service.storage_error:
                self.status.setText(self.service.storage_error)
        except Exception as error:
            self._error(error)

    def show_request(self, *_):
        request_id = self._selected_id()
        if not request_id:
            return
        try:
            data = self.service.detail(request_id, include_content=self.include_content.isChecked())
            if data is None:
                return
            request = data["request"]
            lines = [f"REQUEST {request_id}", f"Outcome: {request['outcome'].replace('_', ' ')}",
                     f"Conversation: {request['conversation_id']}\nProject: {request['project_id']}\nRun: {request['run_id']}",
                     "Timeline incomplete: " + ("YES — diagnostic storage failed" if request["incomplete"] else "no known storage gaps"), ""]
            steps = {step["id"]: step for step in data["steps"]}
            for event in data["events"]:
                step = steps.get(event["step_id"], {})
                lines.append(f"{event['created_at'][11:23]} UTC  {event['code']}  {step.get('name', '')}")
                lines.append(event["message"])
                if event["details"]:
                    lines.append(json.dumps(event["details"], ensure_ascii=False, indent=2))
                lines.append("")
            lines.append("Steps and durations\n" + json.dumps(data["steps"], indent=2))
            lines.append("Captured evidence (absence is explicit):")
            for item in data["content"]:
                lines.append(f"{item['kind']}: {'captured' if item['captured'] else 'not captured — setting off'}, {item['char_count']} characters" + ("; truncated at capture limit" if item["truncated"] else ""))
                if "text" in item and item["text"] is not None:
                    lines.append(item["text"])
            lines.append("Request configuration\n" + json.dumps(request["metadata"], ensure_ascii=False, indent=2))
            self.timeline.setPlainText("\n".join(lines))
        except Exception as error:
            self._error(error)

    def save_settings(self):
        try:
            self.service.save_settings(replace(self.service.settings,
                **{key: checkbox.isChecked() for key, checkbox in self.capture.items()},
                retention_days=self.days.value(), max_requests=self.maximum.value()))
            self.status.setText("Capture settings saved. Retention applied to completed records; unfinished work is preserved.")
            self.refresh()
        except Exception as error:
            self._error(error)

    def delete_selected(self):
        request_id = self._selected_id()
        if request_id and QMessageBox.question(self, "Delete request diagnostics?", "Delete this timeline and its captured content? The chat and project files are preserved.") == QMessageBox.Yes:
            self._delete(request_id)

    def delete_all(self):
        if QMessageBox.question(self, "Delete all diagnostics?", "Delete every diagnostic record and captured item? Chats and project files are preserved.") == QMessageBox.Yes:
            self._delete(None)

    def _delete(self, request_id):
        try:
            self.service.delete(request_id)
            self.timeline.clear()
            self.refresh()
        except Exception as error:
            self._error(error)

    def preview_export(self):
        request_id = self._selected_id()
        if not request_id:
            return
        try:
            preview = self.service.export_preview(request_id, include_content=self.include_content.isChecked())
        except Exception as error:
            self._error(error)
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Review and redact diagnostic export")
        dialog.setObjectName("diagnosticsDialog")
        dialog.resize(850, 600)
        layout = QVBoxLayout(dialog)
        label = QLabel("Inspect paths, notices and any included writing. Edit or remove private values below before saving. Nothing is sent to a provider.")
        label.setWordWrap(True)
        layout.addWidget(label)
        editor = QPlainTextEdit()
        editor.setPlainText(preview)
        layout.addWidget(editor)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            # Keep a machine-readable fixture after manual redaction.
            data = json.loads(editor.toPlainText())
            contents = self.service.redact(json.dumps(data, ensure_ascii=False, indent=2))
            destination, _ = QFileDialog.getSaveFileName(self, "Save diagnostic bundle", f"diagnostic-{request_id[:8]}.json", "JSON (*.json)")
            if not destination:
                return
            target = Path(destination)
            temp = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as output:
                    temp = output.name
                    output.write(contents)
                os.replace(temp, target)
            finally:
                if temp and Path(temp).exists():
                    Path(temp).unlink()
            self.status.setText(f"Saved diagnostic bundle: {target.name}")
        except Exception as error:
            self._error(error)
