"""Offline wheel smoke check in a clean environment without provider SDKs."""
from pathlib import Path
import subprocess
import sys
import tempfile
import venv
import zipfile


wheel = Path(sys.argv[1]).resolve()
with zipfile.ZipFile(wheel) as archive:
    for name in ("sammyai_core/diagnostics.py", "ui/diagnostics.py"):
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
print("Packaged diagnostics migration, persistence, capture, parser and deletion passed")
'''
    subprocess.run([str(python), "-I", "-c", code], cwd=root, check=True)
