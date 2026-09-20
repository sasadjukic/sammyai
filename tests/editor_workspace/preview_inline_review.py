"""Reproducible Windows review demo with temporary files and no model requests.

Run directly for interactive acceptance, or pass --capture PATH for an offscreen
PNG. All project/config files are isolated in a temporary directory.
"""

import argparse
import os
from pathlib import Path
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--capture", type=Path)
parser.add_argument("--with-chat", action="store_true")
parser.add_argument("--width", type=int, default=1250)
parser.add_argument("--height", type=int, default=850)
args = parser.parse_args()
if args.capture:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase
from test_main_window_multifile import FakeRuntimeServices, _project_components
from editing.change_sets import FileChangeRequest
from editing.review_session import HunkState
from sammyai import TextEditor
from sammyai_core.file_tools import SafeFileTools
from sammyai_core.resources import asset_path

app = QApplication.instance() or QApplication([])
if args.capture and os.name == "nt":
    for font_file in ("segoeui.ttf", "segoeuib.ttf", "consola.ttf"):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font_file))
app.setFont(QFont("Segoe UI", 10))
app.setStyleSheet(asset_path("ui", "styles", "dark_theme.qss").read_text(encoding="utf-8"))
with tempfile.TemporaryDirectory(prefix="sammyai-review-") as directory:
    paths, database, service, project = _project_components(Path(directory))
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
    proposed = original.replace(
        "The last train had already gone.",
        "The last train vanished into the rain.\nIts whistle lingered over the empty tracks.",
    ).replace("The platform was quiet.", "Rain ticked against the platform roof.").replace(
        "Tomorrow, she would try again.", "Behind the glass, someone called her name.")
    (project.root_path / "chapter-one.md").write_bytes(original.encode("utf-8"))
    (project.root_path / "story-notes.txt").write_text("A station. A letter. An unexpected visitor.", encoding="utf-8")
    window._open_file_path(project.root_path / "story-notes.txt")
    source = runtime.file_tools.prepare_change_set([
        FileChangeRequest.write("chapter-one.md", proposed),
    ], description="Strengthen the atmosphere and give the scene a more immediate ending.")
    batch = window.review_controller.start_change_set(source)
    view = window.editor_workspace.review_for_session(batch.reviews[0].target_document_id)
    view.decide(HunkState.ACCEPTED)
    view.navigate(1)
    view.decide(HunkState.REJECTED)
    if args.with_chat:
        window._create_chat_panel()
        window.chat_dock.show()
    window.resize(args.width, args.height)
    window.show()
    app.processEvents()
    if args.capture:
        args.capture.parent.mkdir(parents=True, exist_ok=True)
        window.grab().save(str(args.capture))
        window.review_controller.cancel_all()
        window.close()
    else:
        app.exec()
    database.close()
