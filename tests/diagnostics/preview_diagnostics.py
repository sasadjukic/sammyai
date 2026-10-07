"""Render the real diagnostics dialog with synthetic evidence for visual QA."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
import tempfile

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase

from sammyai_core.database import ProjectDatabase
from sammyai_core.diagnostics import RequestTraceService
from sammyai_core.agent_workflows import AgentWorkflowService
from ui.diagnostics import DiagnosticsDialog


app = QApplication.instance() or QApplication([])
if os.name == "nt":
    for name in ("segoeui.ttf", "segoeuib.ttf", "consola.ttf"):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name))
app.setFont(QFont("Segoe UI", 10))
repo = Path(__file__).resolve().parents[2]
app.setStyleSheet((repo / "ui/styles/dark_theme.qss").read_text(encoding="utf-8"))
with tempfile.TemporaryDirectory() as temporary:
    database = ProjectDatabase(Path(temporary) / "diagnostics.sqlite3")
    database.migrate()
    trace = RequestTraceService(database)
    identity = trace.begin("Example conversation", "Example writing project", agent="editor",
                           model={"provider": "example", "name": "Writing model"})
    trace.event(identity.request_id, "notice.context", "@scnes.md was not found. @scenes.md supplied partial file context.")
    AgentWorkflowService(None).run("editor", user_request="Add a scene", messages=[],
        complete=lambda *_: '<sammyai_changes>{"files": broken}</sammyai_changes>', trace=trace, identity=identity)
    dialog = DiagnosticsDialog(trace, identity.conversation_id)
    dialog.show()
    app.processEvents()
    target = Path(sys.argv[1]).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    assert dialog.grab().save(str(target))
    dialog.close()
    database.close()
    print(target)
