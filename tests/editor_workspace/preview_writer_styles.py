"""Isolated Windows profile UI preview using temporary data and a fake provider."""

import argparse
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--capture", type=Path)
args = parser.parse_args()
if args.capture:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from test_main_window_multifile import FakeRuntimeServices, _project_components
from sammyai import TextEditor
from sammyai_core.file_tools import SafeFileTools
from sammyai_core.resources import asset_path
from sammyai_core.style_profiles import StyleSelection
from ui.style_profiles import StyleProfileEditor, StyleProfilesDialog

app = QApplication.instance() or QApplication([])
for filename in ("segoeui.ttf", "segoeuib.ttf", "consola.ttf"):
    QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename))
app.setFont(QFont("Segoe UI", 10))
app.setStyleSheet(asset_path("ui", "styles", "dark_theme.qss").read_text(encoding="utf-8"))
build = Path(__file__).resolve().parents[2] / "build"
build.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="style-preview-", dir=build) as temporary:
    paths, database, projects, project = _project_components(Path(temporary))
    runtime = FakeRuntimeServices(projects)
    runtime.file_tools = SafeFileTools(projects)
    window = TextEditor(services=runtime, app_paths=paths)
    window.spell_hub.service.enabled = False
    profile = window.style_service.repository.create("Restrained and concrete",
        "Use plain, precise diction and concrete actions.\nVary sentence length; keep most action sentences compact.\n"
        "Choose one or two telling details. Suggest emotion through behavior.\n"
        "Keep each character's dialogue distinct. Avoid stock metaphors and repeated explanations.",
        "She set two cups on the table, then put one back. The kettle clicked off.\n\n"
        "Notice the simple verbs and gesture suggesting emotion without explanation.")
    window.style_service.select(project.id, StyleSelection("profile", profile.id))
    path = project.root_path / "chapter-one.md"
    path.write_text("CHAPTER ONE\n\nThe station was almost empty. Mara stood under the clock.\nShe had been waiting a long time, and she felt uncertain.\n", encoding="utf-8")
    window._open_file_path(path)
    window._show_chat_panel()
    window.editor.selectAll()
    window.chat_panel.input_field.setPlainText("Tighten this passage while keeping Mara's uncertainty.")
    window.llm_client = SimpleNamespace(system_prompt="", chat=lambda _: '{"kind":"critique","text":"The gesture can carry more of the uncertainty."}')
    window.resize(1250, 800)
    window.show()
    app.processEvents()
    if args.capture:
        args.capture.mkdir(parents=True, exist_ok=True)
        window.grab().save(str(args.capture / "style-selection.png"))
        manager = StyleProfilesDialog(window.style_service, project.id, window)
        manager.show()
        app.processEvents()
        manager.grab().save(str(args.capture / "style-manager.png"))
        manager.close()
        editor = StyleProfileEditor(window.style_service, project.id, profile, window)
        editor.show()
        app.processEvents()
        editor.grab().save(str(args.capture / "style-editor.png"))
        editor.close()
        long_profile = window.style_service.repository.create("A very long personal style profile name for checking the narrow composer and safe elision", "Use concrete details.")
        window.style_service.select(project.id, StyleSelection("profile", long_profile.id))
        window.style_controller.refresh()
        window.resize(1000, 730)
        app.processEvents()
        window.grab().save(str(args.capture / "style-narrow.png"))
        window.close()
    else:
        app.exec()
    database.close()
