"""Persistent writer preferences and immutable, project-scoped request evidence."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from .database import ProjectDatabase


STYLE_SETTING = "writer_style_selection"
NAME_LIMIT = 120
INSTRUCTION_LIMIT = 6000
EXAMPLE_LIMIT = 3000


class StyleProfileError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _validate(name, instructions, examples):
    for label, value, limit, required in (
        ("Name", name, NAME_LIMIT, True),
        ("Instructions", instructions, INSTRUCTION_LIMIT, True),
        ("Examples", examples, EXAMPLE_LIMIT, False),
    ):
        if not isinstance(value, str) or "\x00" in value:
            raise StyleProfileError(f"{label} must be text without null characters.")
        if required and not value.strip():
            raise StyleProfileError(f"{label} cannot be blank.")
        if len(value) > limit:
            raise StyleProfileError(f"{label} must be at most {limit:,} characters.")


@dataclass(frozen=True)
class StyleSelection:
    mode: str = "none"
    profile_id: str | None = None

    def __post_init__(self):
        if self.mode not in {"none", "inherit", "profile"}:
            raise StyleProfileError("Unknown style selection.")
        if (self.mode == "profile") != bool(self.profile_id):
            raise StyleProfileError("A profile selection requires a profile ID.")

    def to_json(self):
        return json.dumps({"mode": self.mode, "profile_id": self.profile_id}, sort_keys=True)

    @classmethod
    def from_json(cls, text):
        try:
            data = json.loads(text)
            if not isinstance(data, dict) or set(data) != {"mode", "profile_id"}:
                raise ValueError
            if data["profile_id"] is not None and not isinstance(data["profile_id"], str):
                raise ValueError
            return cls(**data)
        except (ValueError, TypeError):
            raise StyleProfileError("The saved style selection is invalid.") from None


@dataclass(frozen=True)
class StyleProfileSnapshot:
    id: str
    project_id: str | None
    name: str
    revision: int
    instructions: str
    examples: str = ""

    def __post_init__(self):
        _validate(self.name, self.instructions, self.examples)
        if not self.id or self.revision < 1:
            raise StyleProfileError("Invalid profile identity or revision.")

    @property
    def canonical_content(self):
        return json.dumps({"instructions": self.instructions, "examples": self.examples},
                          sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    @property
    def content_hash(self):
        return hashlib.sha256(self.canonical_content.encode("utf-8")).hexdigest()

    def metadata(self):
        return {"profile_id": self.id, "name": self.name, "project_id": self.project_id,
                "scope": "project" if self.project_id else "global", "revision": self.revision,
                "content_hash": self.content_hash}


@dataclass(frozen=True)
class StyleProfile:
    id: str
    project_id: str | None
    name: str
    instructions: str
    examples: str
    revision: int
    archived: bool
    created_at: str
    updated_at: str

    def snapshot(self):
        return StyleProfileSnapshot(self.id, self.project_id, self.name, self.revision,
                                    self.instructions, self.examples)


@dataclass(frozen=True)
class ResolvedStyle:
    selection: StyleSelection
    snapshot: StyleProfileSnapshot | None = None
    notice: str = ""


class StyleProfileRepository:
    def __init__(self, database: ProjectDatabase):
        self.database = database

    @staticmethod
    def _profile(row):
        return StyleProfile(**dict(row)) if row is not None else None

    def get(self, profile_id):
        with self.database.read() as db:
            return self._profile(db.execute("SELECT * FROM style_profiles WHERE id=?", (profile_id,)).fetchone())

    def list(self, project_id=None, *, include_archived=False):
        with self.database.read() as db:
            rows = db.execute("""SELECT * FROM style_profiles
                WHERE (project_id IS NULL OR project_id=?) AND (archived=0 OR ?)
                ORDER BY archived, name COLLATE NOCASE, id""", (project_id, include_archived)).fetchall()
        return [self._profile(row) for row in rows]

    def create(self, name, instructions, examples="", *, project_id=None):
        _validate(name, instructions, examples)
        profile_id, now = str(uuid4()), _now()
        with self.database.transaction() as db:
            db.execute("""INSERT INTO style_profiles
                (id,project_id,name,instructions,examples,revision,archived,created_at,updated_at)
                VALUES (?,?,?,?,?,1,0,?,?)""",
                       (profile_id, project_id, name.strip(), instructions, examples, now, now))
        return self.get(profile_id)

    def update(self, profile_id, *, expected_revision, name, instructions, examples=""):
        _validate(name, instructions, examples)
        with self.database.transaction() as db:
            changed = db.execute("""UPDATE style_profiles SET name=?,instructions=?,examples=?,
                revision=revision+1,updated_at=? WHERE id=? AND revision=?""",
                (name.strip(), instructions, examples, _now(), profile_id, expected_revision)).rowcount
            self._require_changed(changed)
        return self.get(profile_id)

    @staticmethod
    def _require_changed(changed):
        if not changed:
            raise StyleProfileError("This profile changed or was deleted. Reopen it before saving.")

    @staticmethod
    def _clear_selections(db, profile_id):
        # All explicit references become OFF, never an implicit global fallback.
        for row in db.execute("SELECT project_id,value_json FROM project_settings WHERE key=?", (STYLE_SETTING,)).fetchall():
            try:
                selection = StyleSelection.from_json(row["value_json"])
            except StyleProfileError:
                continue
            if selection.profile_id == profile_id:
                StyleProfileRepository._write_selection(db, row["project_id"], StyleSelection())
        row = db.execute("SELECT value FROM application_state WHERE key=?", (STYLE_SETTING,)).fetchone()
        if row:
            try:
                selection = StyleSelection.from_json(row["value"])
            except StyleProfileError:
                return
            if selection.profile_id == profile_id:
                StyleProfileRepository._write_selection(db, None, StyleSelection())

    def archive(self, profile_id, *, expected_revision, archived=True):
        with self.database.transaction() as db:
            changed = db.execute("""UPDATE style_profiles SET archived=?,revision=revision+1,updated_at=?
                WHERE id=? AND revision=?""", (int(archived), _now(), profile_id, expected_revision)).rowcount
            self._require_changed(changed)
            if archived:
                self._clear_selections(db, profile_id)
        return self.get(profile_id)

    def delete(self, profile_id, *, expected_revision):
        with self.database.transaction() as db:
            changed = db.execute("DELETE FROM style_profiles WHERE id=? AND revision=?",
                                 (profile_id, expected_revision)).rowcount
            self._require_changed(changed)
            self._clear_selections(db, profile_id)

    @staticmethod
    def _read_selection(db, project_id):
        if project_id is None:
            row = db.execute("SELECT value FROM application_state WHERE key=?", (STYLE_SETTING,)).fetchone()
        else:
            row = db.execute("SELECT value_json FROM project_settings WHERE project_id=? AND key=?",
                             (project_id, STYLE_SETTING)).fetchone()
        return StyleSelection.from_json(row[0]) if row else StyleSelection("inherit" if project_id else "none")

    @staticmethod
    def _write_selection(db, project_id, selection):
        if project_id is None:
            db.execute("""INSERT INTO application_state(key,value,updated_at) VALUES (?,?,?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",
                       (STYLE_SETTING, selection.to_json(), _now()))
        else:
            db.execute("""INSERT INTO project_settings(project_id,key,value_json,updated_at) VALUES (?,?,?,?)
                ON CONFLICT(project_id,key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at""",
                       (project_id, STYLE_SETTING, selection.to_json(), _now()))


class StyleProfileService:
    """Resolve settings atomically; workers receive snapshots, never this service."""

    def __init__(self, repository):
        self.repository = repository

    @staticmethod
    def _check_scope(profile, project_id):
        if profile is None or profile.archived or (profile.project_id is not None and profile.project_id != project_id):
            raise StyleProfileError("The selected profile is unavailable in this project.")
        return profile.snapshot()

    def select(self, project_id, selection):
        with self.repository.database.transaction() as db:
            if selection.mode == "inherit" and project_id is None:
                raise StyleProfileError("The global default cannot inherit a project style.")
            if selection.mode == "profile":
                row = db.execute("SELECT * FROM style_profiles WHERE id=?", (selection.profile_id,)).fetchone()
                self._check_scope(self.repository._profile(row), project_id)
            self.repository._write_selection(db, project_id, selection)

    def resolve(self, project_id=None):
        with self.repository.database.transaction() as db:
            if project_id and not db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
                return ResolvedStyle(StyleSelection(), notice="The originating project is unavailable; no style profile was used.")
            owner = project_id
            selection = StyleSelection()
            try:
                selection = self.repository._read_selection(db, project_id)
                effective = selection
                if selection.mode == "inherit":
                    owner = None
                    effective = self.repository._read_selection(db, None)
                if effective.mode == "inherit":
                    raise StyleProfileError("The global default cannot inherit another style.")
                if effective.mode == "none":
                    return ResolvedStyle(selection)
                row = db.execute("SELECT * FROM style_profiles WHERE id=?", (effective.profile_id,)).fetchone()
                snapshot = self._check_scope(self.repository._profile(row), owner)
                return ResolvedStyle(selection, snapshot)
            except StyleProfileError:
                self.repository._write_selection(db, owner, StyleSelection())
                return ResolvedStyle(StyleSelection("inherit") if selection.mode == "inherit" and project_id else StyleSelection(),
                                     notice="The saved style is unavailable or invalid. No style profile was used; select a profile again.")

    def duplicate(self, profile_id, *, project_id=None):
        original = self.repository.get(profile_id)
        if original is None:
            raise StyleProfileError("The source profile no longer exists.")
        return self.repository.create(original.name[:NAME_LIMIT - 7] + " (copy)", original.instructions,
                                      original.examples, project_id=project_id)
