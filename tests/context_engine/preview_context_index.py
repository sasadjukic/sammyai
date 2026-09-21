"""Render the index inspector with sample metadata and no live index access."""

import argparse
import os
from pathlib import Path
from types import SimpleNamespace

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--capture", type=Path)
args = parser.parse_args()
if args.capture:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from sammyai_core.context_index import IndexedFileSummary
from sammyai_core.resources import asset_path
from ui.rag_management import ContextIndexDialog

app = QApplication.instance() or QApplication([])
if args.capture and os.name == "nt":
    for font_name in ("segoeui.ttf", "segoeuib.ttf"):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font_name))
app.setFont(QFont("Segoe UI", 10))
app.setStyleSheet(asset_path("ui", "styles", "dark_theme.qss").read_text(encoding="utf-8"))
projects = {"novel": SimpleNamespace(id="novel", name="The Meridian"), "notes": SimpleNamespace(id="notes", name="Story notes")}
entries = (
    IndexedFileSummary("C:/Stories/The Meridian/chapter-one.md", "novel", 18),
    IndexedFileSummary("C:/Stories/The Meridian/References/station-history.pdf", "novel", 34),
    IndexedFileSummary("C:/Stories/Notes/characters.md", "notes", 7),
    IndexedFileSummary("C:/Research/old-station-notes.txt", None, 12),
)
dialog = ContextIndexDialog(
    SimpleNamespace(get_indexed_files=lambda: entries),
    SimpleNamespace(active_project=projects["novel"], get_project=projects.get),
)
dialog.scope_combo.setCurrentIndex(dialog.scope_combo.findData("all"))
dialog.file_list.setCurrentItem(dialog.file_list.topLevelItem(3))
dialog.show()
app.processEvents()
if args.capture:
    args.capture.parent.mkdir(parents=True, exist_ok=True)
    dialog.grab().save(str(args.capture))
    dialog.close()
else:
    app.exec()
