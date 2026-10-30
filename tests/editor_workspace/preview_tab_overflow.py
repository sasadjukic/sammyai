"""Render or interact with tab overflow using temporary files and no model calls."""

import argparse
import json
import os
from pathlib import Path
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--capture", type=Path)
parser.add_argument("--with-chat", action="store_true")
parser.add_argument("--menu", action="store_true", help="Also capture the Open tabs menu")
parser.add_argument("--width", type=int, default=1440)
parser.add_argument("--height", type=int, default=850)
args = parser.parse_args()
if args.capture:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QToolButton
from PySide6.QtTest import QTest
from test_main_window_multifile import FakeRuntimeServices, _project_components
from sammyai import TextEditor
from sammyai_core.resources import asset_path

app = QApplication.instance() or QApplication([])
if args.capture and os.name == "nt":
    for font_file in ("segoeui.ttf", "segoeuib.ttf", "consola.ttf"):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font_file))
app.setFont(QFont("Segoe UI", 10))
app.setStyleSheet(asset_path("ui", "styles", "dark_theme.qss").read_text(encoding="utf-8"))
with tempfile.TemporaryDirectory(prefix="sammyai-tabs-") as directory:
    paths, database, service, project = _project_components(Path(directory))
    window = TextEditor(services=FakeRuntimeServices(service), app_paths=paths)
    window.spell_hub.service.enabled = False
    names = (
        "shelf_life_bible.md", "shelf_life_scene_breakdowns.md", "shelf_life_draft.md",
        "shelf_life_outline.md", "shelf_life_character_notes.md", "research_notes.txt",
        "a_very_long_filename_for_the_final_scene_and_alternate_ending.md", "revision_checklist.md",
    )
    for name in names:
        path = project.root_path / name
        path.write_text("# Tab overflow preview\n\nEach file remains a separate editor tab.\n", encoding="utf-8")
        window._open_file_path(path)
    workspace = window.editor_workspace
    workspace.activate_document(workspace.sessions()[2].session_id)
    window.editor.insertPlainText("Unsaved draft\n\n")
    if args.with_chat:
        window._create_chat_panel()
        window.chat_dock.show()
    window.resize(args.width, args.height)
    window.show()
    if args.with_chat:
        window.resizeDocks([window.project_dock, window.chat_dock], [240, 500], Qt.Horizontal)
    app.processEvents()
    QTest.qWait(100)
    bar = workspace.tabs.tabBar()
    print(json.dumps({
        "window": [window.width(), window.height()],
        "bar": [bar.width(), bar.height()],
        "tabs": [bar.tabRect(i).getRect() for i in range(bar.count())],
        "buttons": [
            {"name": b.objectName(), "rect": b.geometry().getRect(), "visible": b.isVisible(),
             "icon": not b.icon().isNull(), "arrow": b.arrowType().name}
            for b in bar.findChildren(QToolButton)
        ],
    }), flush=True)
    if args.capture:
        args.capture.parent.mkdir(parents=True, exist_ok=True)
        window.grab().save(str(args.capture))
        workspace.tabs.grab(QRect(0, 0, workspace.tabs.width(), bar.height())).save(
            str(args.capture.with_stem(args.capture.stem + "-bar"))
        )
        if args.menu:
            button = workspace.tabs.cornerWidget(Qt.TopRightCorner)
            button.menu().popup(button.mapToGlobal(QPoint(0, button.height())))
            app.processEvents()
            button.menu().grab().save(str(args.capture.with_stem(args.capture.stem + "-menu")))
            button.menu().hide()
    else:
        app.exec()
    for session in workspace.dirty_sessions():
        workspace.mark_clean(session.session_id)
    window.close()
    window.deleteLater()
    app.processEvents()
    database.close()
