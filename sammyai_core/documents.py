"""Filesystem operations used by the editor and context-injection workflows."""

from __future__ import annotations

from pathlib import Path
import subprocess


class DocumentError(RuntimeError):
    """Raised when a document cannot be read, written, or converted."""


class DocumentService:
    """Provides one testable boundary around mutable document I/O."""

    TEXT_EXTENSIONS = {".txt", ".md"}

    def read_text(self, path: str | Path, *, errors: str = "strict") -> str:
        return Path(path).read_text(encoding="utf-8", errors=errors)

    def write_text(self, path: str | Path, content: str) -> None:
        Path(path).write_text(content, encoding="utf-8")

    def extract_context_text(self, path: str | Path) -> str:
        document_path = Path(path)
        extension = document_path.suffix.lower()
        if extension == ".pdf":
            try:
                result = subprocess.run(
                    ["pdftotext", str(document_path), "-"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except OSError as error:
                raise DocumentError(f"Unable to run pdftotext: {error}") from error
            if result.returncode != 0:
                raise DocumentError(
                    f"pdftotext failed with exit code {result.returncode}: "
                    f"{result.stderr.strip()}"
                )
            return result.stdout

        return self.read_text(document_path, errors="replace")
