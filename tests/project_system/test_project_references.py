"""Reference imports retain source bytes and use ordinary project synchronization."""

from types import SimpleNamespace

import pytest

from sammyai_core.project_references import ProjectReferenceImporter


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "novel"
    root.mkdir()
    return SimpleNamespace(root_path=root)


@pytest.mark.parametrize("name,content", [
    ("notes.md", b"# Research\r\nExact text\r\n"),
    ("notes.txt", "Résumé 😀".encode("utf-8")),
    ("research.PDF", b"%PDF-1.4\nreference bytes"),
])
def test_import_preserves_source_and_creates_project_copy(project, tmp_path, name, content):
    source = tmp_path / name
    source.write_bytes(content)
    target = ProjectReferenceImporter().import_file(project, source)
    assert target == project.root_path / "References" / name
    assert target.read_bytes() == source.read_bytes() == content


def test_duplicate_names_and_open_document_paths_are_never_overwritten(project, tmp_path):
    source = tmp_path / "notes.md"
    source.write_bytes(b"new")
    folder = project.root_path / "References"
    folder.mkdir()
    existing = folder / "notes.md"
    existing.write_bytes(b"old")
    reserved = folder / "notes 2.md"
    target = ProjectReferenceImporter().import_file(project, source, reserved_paths=(reserved,))
    assert target.name == "notes 3.md"
    assert target.read_bytes() == b"new"
    assert existing.read_bytes() == b"old"
    assert not reserved.exists()


def test_file_already_in_project_uses_existing_path(project):
    source = project.root_path / "chapter.md"
    source.write_bytes(b"already here")
    assert ProjectReferenceImporter().import_file(project, source) == source
    assert not (project.root_path / "References").exists()


def test_unsupported_and_missing_sources_do_not_create_project_files(project, tmp_path):
    importer = ProjectReferenceImporter()
    unsupported = tmp_path / "program.exe"
    unsupported.write_bytes(b"not a reference")
    with pytest.raises(ValueError, match="supported"):
        importer.import_file(project, unsupported)
    with pytest.raises(OSError):
        importer.import_file(project, tmp_path / "missing.md")
    assert not (project.root_path / "References").exists()


def test_protected_source_inside_project_is_rejected(project):
    source = project.root_path / ".git" / "notes.md"
    source.parent.mkdir()
    source.write_bytes(b"metadata")
    with pytest.raises(ValueError, match="excluded"):
        ProjectReferenceImporter().import_file(project, source)


def test_reference_folder_cannot_be_a_file(project, tmp_path):
    source = tmp_path / "notes.md"
    source.write_bytes(b"source")
    destination = project.root_path / "References"
    destination.write_bytes(b"existing")
    with pytest.raises(OSError):
        ProjectReferenceImporter().import_file(project, source)
    assert destination.read_bytes() == b"existing"


def test_copy_failure_removes_only_its_temporary_file(project, tmp_path, monkeypatch):
    import sammyai_core.project_references as module
    source = tmp_path / "notes.md"
    source.write_bytes(b"source")
    def fail_copy(source_stream, target_stream):
        target_stream.write(b"partial")
        raise OSError("Disk full")
    monkeypatch.setattr(module.shutil, "copyfileobj", fail_copy)
    with pytest.raises(OSError, match="Disk full"):
        ProjectReferenceImporter().import_file(project, source)
    assert source.read_bytes() == b"source"
    assert not list((project.root_path / "References").iterdir())


def test_reference_folder_symlink_is_not_followed(project, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    source = tmp_path / "notes.md"
    source.write_bytes(b"source")
    try:
        (project.root_path / "References").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation is unavailable on this Windows account")
    with pytest.raises(ValueError, match="link"):
        ProjectReferenceImporter().import_file(project, source)
    assert not list(outside.iterdir())


def test_reference_folder_junction_is_rejected_before_copy(project, tmp_path, monkeypatch):
    from pathlib import Path
    source = tmp_path / "notes.md"
    source.write_bytes(b"source")
    destination = project.root_path / "References"
    destination.mkdir()
    monkeypatch.setattr(Path, "is_junction", lambda path: path == destination, raising=False)
    with pytest.raises(ValueError, match="link"):
        ProjectReferenceImporter().import_file(project, source)
    assert not list(destination.iterdir())


def test_concurrent_destination_creation_chooses_another_name(project, tmp_path, monkeypatch):
    import sammyai_core.project_references as module
    source = tmp_path / "notes.md"
    source.write_bytes(b"source")
    name = "rename" if module.os.name == "nt" else "link"
    publish = getattr(module.os, name)
    calls = []
    def create_collision(source_path, target):
        calls.append(target)
        if len(calls) == 1:
            target.write_bytes(b"concurrent writer")
            raise FileExistsError(str(target))
        return publish(source_path, target)
    monkeypatch.setattr(module.os, name, create_collision)
    target = ProjectReferenceImporter().import_file(project, source)
    assert target.name == "notes 2.md"
    assert target.read_bytes() == b"source"
    assert calls[0].read_bytes() == b"concurrent writer"
