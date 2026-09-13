"""Offline spelling and local writing preferences, independent of Qt."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import islice
import json
from pathlib import Path
import re
from threading import RLock


@dataclass(frozen=True)
class Misspelling:
    word: str
    start: int  # Qt UTF-16 offsets, including astral Unicode characters
    end: int


WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)
SKIP = re.compile(
    r"(`+).*?\1|(?:https?://|www\.)[^\s<>]+|[\w.+-]+@[\w.-]+\.[A-Za-z]+"
    r"|(?:[A-Za-z]:[\\/]|(?:\.\.?|~)?/|\\\\)[^\s<>]+"
    r"|[\w.@-]+(?:[\\/][\w.@-]+)+|[\w@-]+\.(?:md|txt|pdf|py|json|fountain)\b"
    r"|\b\w*\d\w*\b"
)
CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)[\s\S]*?(?<!`)\1(?!`)")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
DEFAULT_SCREENPLAY_TOKENS = ('INT', 'EXT', 'CONT', 'CONTINUED', 'VO', 'OS', 'POV', 'SFX')


def normalize(word: str) -> str:
    return word.replace('’', "'").casefold()


@lru_cache(maxsize=4096)
def line_words(line: str):
    """Cache unchanged blocks; return exact Python ranges before Qt conversion."""
    spans = [(m.start(), m.end()) for m in SKIP.finditer(line)]
    return tuple((m.group(), m.start(), m.end()) for m in WORD.finditer(line)
                 if not any(a < m.end() and b > m.start() for a, b in spans))


class SpyllsBackend:
    def __init__(self):
        from spylls.hunspell import Dictionary
        # Resolve bundled resources explicitly, never a dictionary in the CWD.
        import spylls.hunspell
        base = Path(spylls.hunspell.__file__).parent / 'data' / 'en' / 'en_US'
        self.dictionary = Dictionary.from_files(str(base))

    def lookup(self, word):
        return self.dictionary.lookup(word)

    def suggest(self, word):
        return self.dictionary.suggest(word)


class SpellCheckService:
    language = 'English (United States)'

    def __init__(self, config_dir: Path, backend=None):
        self.path = Path(config_dir) / 'writing_preferences.json'
        self._lock = RLock()
        self._backend_lock = RLock()
        self._backend = backend
        self._known_cache = {}
        self.ignored = set()
        self.preferences = self._read()
        self.enabled = self.preferences.get('spell_check_enabled', True) is not False
        words = self.preferences.get('personal_words', [])
        self.personal = {normalize(w) for w in words if isinstance(w, str)} if isinstance(words, list) else set()
        tokens = self.preferences.get('screenplay_tokens', list(DEFAULT_SCREENPLAY_TOKENS))
        self.screenplay_tokens = frozenset(w for w in tokens if isinstance(w, str)) if isinstance(tokens, list) else frozenset(DEFAULT_SCREENPLAY_TOKENS)

    def _read(self):
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, **updates):
        data = dict(self.preferences, **updates)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.path)
        self.preferences = data

    def set_enabled(self, enabled):
        with self._lock:
            self._save(spell_check_enabled=bool(enabled))
            self.enabled = bool(enabled)

    def add_word(self, word):
        with self._lock:
            words = self.personal | {normalize(word)}
            self._save(personal_words=sorted(words))
            self.personal = words

    def ignore_all(self, word):
        with self._lock:
            self.ignored.add(normalize(word))

    def _get_backend(self):
        if self._backend is None:
            self._backend = SpyllsBackend()
        return self._backend

    def known(self, word):
        normalized = normalize(word)
        with self._lock:
            if normalized in self.personal or normalized in self.ignored or word in self.screenplay_tokens:
                return True
        with self._backend_lock:
            candidate = word.replace('’', "'")
            if candidate not in self._known_cache:
                if len(self._known_cache) >= 20000:
                    self._known_cache.clear()
                self._known_cache[candidate] = self._get_backend().lookup(candidate)
            return self._known_cache[candidate]

    def scan(self, text, cancelled=None):
        results = []
        offset = 0
        fence = None
        code_spans = [(m.start(), m.end()) for m in CODE_SPAN.finditer(text)]
        span_index = 0
        python_offset = 0
        for line in text.splitlines(keepends=True):
            if cancelled is not None and cancelled.is_set():
                return []
            marker = FENCE.match(line)
            skip = fence is not None or marker is not None
            if marker:
                run = marker.group(1)
                if fence is None:
                    fence = run
                elif run[0] == fence[0] and len(run) >= len(fence) and not line[marker.end():].strip():
                    fence = None
            if not skip:
                # Build a linear offset map once per block (no quadratic slicing).
                positions = [offset]
                for char in line:
                    positions.append(positions[-1] + (2 if ord(char) > 0xFFFF else 1))
                for word, start, end in line_words(line):
                    if cancelled is not None and cancelled.is_set():
                        return []
                    while span_index < len(code_spans) and code_spans[span_index][1] <= python_offset + start:
                        span_index += 1
                    if span_index < len(code_spans) and code_spans[span_index][0] < python_offset + end:
                        continue
                    if not self.known(word):
                        results.append(Misspelling(word, positions[start], positions[end]))
            offset += len(line.encode('utf-16-le')) // 2
            python_offset += len(line)
        return results

    def suggestions(self, word):
        # Very long tokens are still marked, but skip expensive candidate generation.
        if len(word) > 40:
            return []
        with self._backend_lock:
            return list(islice(self._get_backend().suggest(word.replace('’', "'")), 5))
