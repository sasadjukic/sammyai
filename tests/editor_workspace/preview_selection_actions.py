"""Offline Windows selection-action demo. Use --capture DIRECTORY for PNG checks."""

import argparse
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--capture", type=Path)
args = parser.parse_args()
if args.capture:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtGui import QFont, QFontDatabase, QTextCursor
from PySide6.QtWidgets import QApplication
from test_main_window_multifile import FakeRuntimeServices, _project_components
from sammyai import TextEditor
from sammyai_core.file_tools import SafeFileTools
from sammyai_core.resources import asset_path

app = QApplication.instance() or QApplication([])
for font_file in ("segoeui.ttf", "segoeuib.ttf", "consola.ttf"):
    QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font_file))
app.setFont(QFont("Segoe UI", 10))
app.setStyleSheet(asset_path("ui", "styles", "dark_theme.qss").read_text(encoding="utf-8"))
build = Path(__file__).resolve().parents[2] / "build"
build.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="selection-preview-", dir=build) as temporary:
    paths, database, service, project = _project_components(Path(temporary))
    runtime = FakeRuntimeServices(service)
    runtime.file_tools = SafeFileTools(service)
    window = TextEditor(services=runtime, app_paths=paths)
    window.spell_hub.service.enabled = False
    original = (
        "CHAPTER ONE\n\nThe last train had already gone.\n"
        "Mara waited under the station clock.\n\n"
        "The platform was quiet.\nA light flickered in the ticket office.\n\n"
        "She reached for the letter in her coat.\n"
        "Tomorrow, she would try again.\n"
    )
    path = project.root_path / "chapter-one.md"
    path.write_text(original, encoding="utf-8")
    window._open_file_path(path)
    window._show_chat_panel()
    cursor = window.editor.textCursor()
    cursor.setPosition(original.index("The platform"))
    cursor.setPosition(original.index("She reached"), QTextCursor.KeepAnchor)
    window.editor.setTextCursor(cursor)
    window.chat_panel.input_field.setPlainText("Make this moment more tense.")
    def complete(messages):
        action = json.loads(messages[0]["content"])["action"]
        kind = "critique" if action == "critique" else "insertion" if action == "continue" else "replacement"
        text = "The scene has a clear mood; try adding one sound that interrupts the silence." if kind == "critique" else "Rain ticked against the platform roof.\nBehind the ticket-office glass, a shadow moved.\n\n"
        return json.dumps({"kind": kind, "text": text})
    window.llm_client = SimpleNamespace(system_prompt="", chat=complete)
    window.resize(1400, 850)
    window.show()
    app.processEvents()
    if args.capture:
        args.capture.mkdir(parents=True, exist_ok=True)
        window.grab().save(str(args.capture / "composer-reference.png"))
        for name, widget in (("editor", window.editor), ("composer", window.chat_panel.input_field)):
            menu = widget.context_menus.create(widget, name, widget.textCursor().position())
            menu.show()
            app.processEvents()
            menu.grab().save(str(args.capture / f"{name}-menu.png"))
            menu.close()
        window.chat_panel._on_send_clicked()
        while window.selection_actions.pending:
            app.processEvents()
        app.processEvents()
        window.grab().save(str(args.capture / "selection-review.png"))
        window.review_controller.cancel_all()
        window.close()
    else:
        app.exec()
    database.close()
