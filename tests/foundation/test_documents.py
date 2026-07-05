from pathlib import Path

import pytest

from sammyai_core.documents import DocumentService


def test_document_service_round_trip(tmp_path: Path):
    service = DocumentService()
    document = tmp_path / "chapter.md"
    content = "# Chapter One\n\nA storm gathered over the harbor.\n"

    service.write_text(document, content)

    assert service.read_text(document) == content
    assert service.extract_context_text(document) == content


def test_document_write_is_atomic_when_replace_fails(tmp_path, monkeypatch):
    service = DocumentService()
    document = tmp_path / "chapter.md"
    document.write_text("Original\n", encoding="utf-8")

    def fail_replace(source, target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("sammyai_core.documents.os.replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        service.write_text(document, "Replacement\n")

    assert document.read_text(encoding="utf-8") == "Original\n"
    assert not list(tmp_path.glob(".*.sammyai-tmp"))
