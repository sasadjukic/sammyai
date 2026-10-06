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
    assert "llm/dbe_system_prompt.py" not in archive.namelist(), "Retired DBE prompt must not ship"
    for name in ("editing/review_session.py", "ui/inline_review.py", "ui/review_controller.py", "sammyai_core/file_edit_context.py"):
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
import json
from llm.chat_manager import ChatManager, MessageRole
from sammyai_core.agent_workflows import AgentType, AgentWorkflowService
from sammyai_core.context_engine import ProjectContextEngine, ProjectFileRepository
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
chat = ChatManager(storage_dir="chats", autosave=True)
chat.create_session("existing-conversation")
chat.add_message(MessageRole.USER, "Continue this conversation")
restored = ChatManager(storage_dir="chats")
restored.load_all_sessions()
assert restored.get_active_session().messages[0].content == "Continue this conversation"
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
large_path = project.root_path / "scene_breakdown.md"
original = "".join(f"## Scene {index}\r\n" + "Existing scene material. " * 100 + "\r\n\r\n" for index in range(1, 20))
large_path.write_bytes(original.encode("utf-8"))
engine = ProjectContextEngine(service, ProjectFileRepository(database), None)
context = engine.build_context("Add Scene 20 to @scene_breakdown.md")
assert context.truncated and not context.complete_referenced_files
addition = "## Scene 20\nNew material.\n"
directive = {"summary": "Add Scene 20", "files": [{"path": large_path.name, "operation": "append", "content": addition}]}
result = AgentWorkflowService(tools).run(
    AgentType.EDITOR, user_request="Add Scene 20 to @scene_breakdown.md",
    messages=[{"role": "system", "content": part} for part in context.system_messages],
    file_snapshots=context.file_snapshots,
    complete=lambda *args: "<sammyai_changes>" + json.dumps(directive) + "</sammyai_changes>",
)
assert result.change_set is not None, result.notices
assert large_path.read_bytes() == original.encode("utf-8")
review = ReviewSession(result.change_set.id, "large-document", str(large_path), result.change_set.changes[0])
review.decide_all(HunkState.ACCEPTED)
tools.apply(ChangeSet(project.id, "Accepted addition", (review.final_change(),)))
assert large_path.read_bytes() == (original + addition.replace("\n", "\r\n")).encode("utf-8")
tools.undo_last()
assert large_path.read_bytes() == original.encode("utf-8")

theme = asset_path("ui", "styles", "dark_theme.qss")
assert theme.is_file() and "QLabel#reviewAddition" in theme.read_text(encoding="utf-8")
database.close()
print("PASS: isolated wheel chat persistence, large-file append/review, CRLF, safe apply/undo/redo, theme; retired DBE absent, network blocked")
'''
    subprocess.run([str(python), "-I", "-c", code], cwd=root, check=True)
