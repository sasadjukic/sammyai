from pathlib import Path

from sammyai_core.documents import DocumentService


def test_document_service_round_trip(tmp_path: Path):
    service = DocumentService()
    document = tmp_path / "chapter.md"
    content = "# Chapter One\n\nA storm gathered over the harbor.\n"

    service.write_text(document, content)

    assert service.read_text(document) == content
    assert service.extract_context_text(document) == content
