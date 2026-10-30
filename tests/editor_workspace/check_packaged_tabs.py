"""Test installed tab controls and icons offline in a fresh application environment.

Qt and pytest dependencies are reused from the calling development environment;
the application, stylesheet and SVG assets must come from the installed wheel.
"""

from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import venv

wheel = Path(sys.argv[1]).resolve()
dependencies = sysconfig.get_paths()["purelib"]
tests_source = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix="sammyai-tabs-package-") as temporary:
    root = Path(temporary)
    venv.EnvBuilder(with_pip=True).create(root / "venv")
    python = root / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)], check=True)
    tests = root / "tests"
    tests.mkdir()
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    shutil.copy2(tests_source / "test_tab_overflow.py", tests / "test_tab_overflow.py")
    code = r'''
import os, socket, sys
from pathlib import Path
sys.path.append(sys.argv[1])
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
socket.socket.connect = lambda *args: (_ for _ in ()).throw(AssertionError("Network forbidden"))
import ui.editor_workspace
from sammyai_core.resources import asset_path
assert Path(ui.editor_workspace.__file__).is_relative_to(Path(sys.prefix))
for parts in (("ui", "styles", "dark_theme.qss"), ("icons", "chevron_left.svg"),
              ("icons", "chevron_right.svg"), ("icons", "chevron_down.svg")):
    path = asset_path(*parts)
    assert path.is_file() and path.is_relative_to(Path(sys.prefix)), path
import pytest
raise SystemExit(pytest.main([
    "-q", "-c", "pytest.ini", "--rootdir=.", "--confcutdir=.",
    "tests/test_tab_overflow.py", "--basetemp=pytest-tmp",
]))
'''
    subprocess.run([str(python), "-B", "-I", "-u", "-c", code, dependencies], cwd=root, check=True)
