"""Check installed reference import and inspector assets offline, without the checkout."""

from pathlib import Path
import subprocess
import sys
import tempfile
import venv
import zipfile


wheel = Path(sys.argv[1]).resolve()
with zipfile.ZipFile(wheel) as archive:
    for name in (
        "sammyai_core/project_references.py",
        "sammyai_core/context_index.py",
        "ui/rag_management.py",
    ):
        assert name in archive.namelist(), name

with tempfile.TemporaryDirectory(prefix="sammyai-reference-package-") as temporary:
    root = Path(temporary)
    venv.EnvBuilder(with_pip=True).create(root / "venv")
    python = root / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)], check=True)
    code = r'''
import socket
import sys
from pathlib import Path
from types import SimpleNamespace

socket.socket.connect = lambda *args: (_ for _ in ()).throw(AssertionError("Network forbidden"))
import sammyai_core.project_references
from sammyai_core.context_index import IndexedFileSummary
from sammyai_core.project_references import ProjectReferenceImporter
from sammyai_core.resources import asset_path

assert Path(sammyai_core.project_references.__file__).is_relative_to(Path(sys.prefix))
folder = Path("novel").resolve()
folder.mkdir()
project = SimpleNamespace(root_path=folder)
source = Path("research.md").resolve()
source.write_bytes(b"# Research\r\nExact reference bytes\r\n")
importer = ProjectReferenceImporter()
first = importer.import_file(project, source)
second = importer.import_file(project, source)
assert first.name == "research.md" and second.name == "research 2.md"
assert first.read_bytes() == second.read_bytes() == source.read_bytes()
assert IndexedFileSummary(str(first), None, 2).project_id is None
theme = asset_path("ui", "styles", "dark_theme.qss").read_text(encoding="utf-8")
assert "#contextIndexDialog" in theme
print("PASS: isolated wheel reference imports, collision handling, inventory model and theme; network blocked")
'''
    subprocess.run([str(python), "-I", "-c", code], cwd=root, check=True)
