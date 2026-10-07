"""Offline wheel smoke check in a clean environment without provider SDKs."""
from pathlib import Path
import subprocess
import sys
import tempfile
import venv
import zipfile


wheel = Path(sys.argv[1]).resolve()
with zipfile.ZipFile(wheel) as archive:
    for name in ("sammyai_core/diagnostics.py", "sammyai_core/proposal_protocol.py", "ui/diagnostics.py"):
        assert name in archive.namelist(), name

with tempfile.TemporaryDirectory(prefix="sammyai-diagnostics-package-") as temporary:
    root = Path(temporary)
    venv.EnvBuilder(with_pip=True).create(root / "venv")
    python = root / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)], check=True)
    code = r'''
import socket
from pathlib import Path
from dataclasses import replace
from importlib.metadata import version
import sammyai_core.diagnostics
from sammyai_core.database import ProjectDatabase
from sammyai_core.diagnostics import RequestTraceService, inspect_proposal
from sammyai_core.agent_workflows import AgentWorkflowService
socket.socket.connect = lambda *args: (_ for _ in ()).throw(AssertionError("Network forbidden"))
assert Path(sammyai_core.diagnostics.__file__).is_relative_to(Path(__import__('sys').prefix))
assert version("sammyai") == "0.6.1a0"
database = ProjectDatabase("state.sqlite3")
database.migrate(4)
with database.transaction() as db:
    db.execute("INSERT INTO application_state VALUES ('existing','preserved','now')")
database.migrate()
trace = RequestTraceService(database)
trace.save_settings(replace(trace.settings, failed_proposals=True))
identity = trace.begin("chat", None, agent="editor")
source = '<sammyai_changes>{"files": broken}</sammyai_changes>'
result = AgentWorkflowService(None).run("editor", user_request="Edit", messages=[],
    complete=lambda *_: source, trace=trace, identity=identity)
assert result.outcome == "proposal_rejected"
assert inspect_proposal(source)["outcome"] == "rejected"
assert '"text"' not in trace.export_preview(identity.request_id)
database.close()
trace = RequestTraceService(database)
trace.recover_interrupted()
data = trace.detail(identity.request_id, include_content=True)
assert data["request"]["outcome"] == "proposal_rejected"
assert data["request"]["metadata"]["app_version"] == "0.6.1a0"
assert any(item["text"] == source for item in data["content"])
assert not data["request"]["incomplete"]
assert database.connection.execute("SELECT value FROM application_state WHERE key='existing'").fetchone()[0] == "preserved"
trace.delete()
assert not trace.list_requests()
database.close()
from sammyai_core.paths import AppPaths
from sammyai_core.projects import ProjectRepository, ProjectService
from sammyai_core.file_tools import SafeFileTools
from sammyai_core.file_edit_context import FileEditSnapshot
paths = AppPaths(Path('config'), Path('data'), Path('cache'), Path('logs')).ensure_created()
projects = ProjectService(ProjectRepository(database), paths)
Path('novel').mkdir()
project = projects.open_project(Path('novel'))
path = project.root_path / 'chapter.md'
original = 'First old passage.\r\nUnchanged.\r\nSecond old passage.\r\n'
path.write_bytes(original.encode())
source = r"""<sammyai_edits>
summary: Two revisions
file: chapter.md
operation: replace
<<<SAMMYAI_SEARCH>>>
First old passage.
<<<SAMMYAI_REPLACEMENT>>>
First "new" passage.
<<<SAMMYAI_END>>>
<<<SAMMYAI_SEARCH>>>
Second old passage.
<<<SAMMYAI_REPLACEMENT>>>
Second new passage with literal \n and backslashes.
<<<SAMMYAI_END>>>
</sammyai_edits>"""
assert inspect_proposal(source) == {'outcome': 'parsed', 'file_count': 1}
file_tools = SafeFileTools(projects)
result = AgentWorkflowService(file_tools).run('editor', user_request='Revise @chapter.md', messages=[],
    file_snapshots=(FileEditSnapshot(project.id, path.name, original, (), True),), complete=lambda *_: source)
assert result.outcome == 'pending_review', result.notices
assert path.read_bytes() == original.encode()
assert result.change_set.changes[0].after_content == original.replace('First old', 'First "new"').replace('Second old passage.', r'Second new passage with literal \n and backslashes.')
database.close()
print("Packaged diagnostics and raw-text multi-passage review preparation passed; network blocked")
'''
    subprocess.run([str(python), "-I", "-c", code], cwd=root, check=True)
