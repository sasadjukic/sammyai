"""Run explicitly with a wheel directory; creates an isolated offline installation."""
from pathlib import Path
import subprocess
import sys
import tempfile
import venv
import zipfile

wheel_dir = Path(sys.argv[1]).resolve()
wheel = next(wheel_dir.glob('sammyai-*.whl'))
with zipfile.ZipFile(wheel) as archive:
    assert 'sammyai_core/licenses/SCOWL-en-US.txt' in archive.namelist()
    assert 'sammyai_core/licenses/SPYLLS-MPL-2.0.txt' in archive.namelist()
    assert 'ui/spell_check.py' in archive.namelist()
with tempfile.TemporaryDirectory(prefix='sammyai-spelling-package-') as temporary:
    root = Path(temporary)
    venv.EnvBuilder(with_pip=True).create(root / 'venv')
    python = root / 'venv' / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    subprocess.run([str(python), '-m', 'pip', 'install', '--no-index', '--no-deps',
                    '--find-links', str(wheel_dir), str(wheel), 'spylls==0.1.7'], check=True)
    code = """
import socket
from pathlib import Path
from importlib.resources import files
from sammyai_core.spelling import SpellCheckService
socket.socket.connect = lambda *args: (_ for _ in ()).throw(AssertionError('Network forbidden'))
service = SpellCheckService(Path('config'))
assert not service.scan('The color of the theater is beautiful.')
assert service.scan('mispeling')[0].word == 'mispeling'
assert 'misspelling' in service.suggestions('mispeling')
service.add_word('Zorblax')
assert SpellCheckService(Path('config')).known('Zorblax')
assert (files('sammyai_core') / 'licenses' / 'SCOWL-en-US.txt').is_file()
print('PASS: isolated wheel spelling, suggestions, persistence, notices; network blocked')
"""
    subprocess.run([str(python), '-I', '-c', code], cwd=root, check=True)
