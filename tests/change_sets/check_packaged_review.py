"""Offline isolated wheel check for review synthesis, safe apply/history and assets.

This tests the installed core in a fresh virtual environment, without importing
from the checkout. Full GUI installation remains an interactive acceptance gate.
"""

from pathlib import Path
import subprocess
import sys
import tempfile
import venv
import zipfile

wheel = Path(sys.argv[1]).resolve()
with zipfile.ZipFile(wheel) as archive:
    for name in ("editing/review_session.py", "ui/inline_review.py", "ui/review_controller.py"):
        assert name in archive.namelist(), name

with tempfile.TemporaryDirectory(prefix="sammyai-review-package-") as temporary:
    root = Path(temporary)
    venv.EnvBuilder(with_pip=True).create(root / "venv")
    python = root / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)], check=True)
    code = r'''
import socket
import sys
from pathlib import Path
import editing.review_session
from editing.review_session import HunkState, ReviewSession
from editing.change_sets import ChangeSet, FileChangeRequest
from sammyai_core.database import ProjectDatabase
from sammyai_core.file_tools import SafeFileTools
from sammyai_core.paths import AppPaths
from sammyai_core.projects import ProjectRepository, ProjectService
from sammyai_core.resources import asset_path
socket.socket.connect = lambda *args: (_ for _ in ()).throw(AssertionError("Network forbidden"))
assert Path(editing.review_session.__file__).is_relative_to(Path(sys.prefix))
paths = AppPaths(config_dir=Path("config"), data_dir=Path("data"), cache_dir=Path("cache"), log_dir=Path("logs")).ensure_created()
database = ProjectDatabase(paths.project_database_path)
database.migrate()
service = ProjectService(ProjectRepository(database), paths)
Path("novel").mkdir()
project = service.open_project(Path("novel"))
path = project.root_path / "chapter.md"
path.write_bytes(b"old\r\nkeep\r\nlast\r\n")
tools = SafeFileTools(service)
source = tools.prepare_change_set([FileChangeRequest.write("chapter.md", "new\r\nextra\r\nkeep\r\nend\r\n")], description="Review")
review = ReviewSession(source.id, "document", str(path), source.changes[0])
review.decide(review.hunks[0].id, HunkState.ACCEPTED)
review.decide(review.hunks[1].id, HunkState.REJECTED)
accepted = ChangeSet(project.id, "Accepted review", (review.final_change(),))
tools.apply(accepted)
assert path.read_bytes() == b"new\r\nextra\r\nkeep\r\nlast\r\n"
tools.undo_last()
assert path.read_bytes() == b"old\r\nkeep\r\nlast\r\n"
tools.redo_last()
assert path.read_bytes() == b"new\r\nextra\r\nkeep\r\nlast\r\n"
theme = asset_path("ui", "styles", "dark_theme.qss")
assert theme.is_file() and "QLabel#reviewAddition" in theme.read_text(encoding="utf-8")
database.close()
print("PASS: isolated wheel review synthesis, CRLF, safe apply/undo/redo, theme; network blocked")
'''
    subprocess.run([str(python), "-I", "-c", code], cwd=root, check=True)
