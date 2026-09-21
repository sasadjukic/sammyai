"""Copy external references into a project for its normal context lifecycle."""

from collections.abc import Iterable
import os
from pathlib import Path
import shutil
import tempfile

from .context_engine import IGNORED_DIRECTORIES, SUPPORTED_EXTENSIONS
from .projects import Project


class ProjectReferenceImporter:
    """Preserve source files and publish complete copies without overwriting."""

    def import_file(
        self,
        project: Project,
        source: str | Path,
        *,
        reserved_paths: Iterable[Path] = (),
    ) -> Path:
        source_path = Path(source).expanduser().resolve(strict=True)
        if not source_path.is_file():
            raise ValueError("Choose a reference file, not a folder.")
        if source_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError("Only .md, .txt, and .pdf reference files are supported.")
        root = project.root_path.resolve(strict=True)
        try:
            relative = source_path.relative_to(root)
        except ValueError:
            relative = None
        if relative is not None:
            if any(part.startswith(".") or part.casefold() in IGNORED_DIRECTORIES for part in relative.parts[:-1]):
                raise ValueError("This file is in a folder excluded from project context.")
            return source_path

        destination = root / "References"
        if destination.is_symlink() or getattr(destination, "is_junction", lambda: False)():
            raise ValueError("The project's References folder cannot be a link.")
        destination.mkdir(exist_ok=True)
        if destination.resolve(strict=True) != destination:
            raise ValueError("The reference destination must stay inside the project.")

        reserved = {os.path.normcase(str(path.resolve(strict=False))) for path in reserved_paths}
        descriptor, temporary_name = tempfile.mkstemp(prefix=".reference-", suffix=".tmp", dir=destination)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as target_stream, source_path.open("rb") as source_stream:
                shutil.copyfileobj(source_stream, target_stream)
                target_stream.flush()
                os.fsync(target_stream.fileno())
            counter = 1
            while True:
                name = source_path.name if counter == 1 else f"{source_path.stem} {counter}{source_path.suffix}"
                target = destination / name
                counter += 1
                if os.path.normcase(str(target)) in reserved or target.exists() or target.is_symlink():
                    continue
                try:
                    # Windows rename fails if the destination exists. POSIX link
                    # provides the same no-overwrite, complete-file publication.
                    if os.name == "nt":
                        os.rename(temporary, target)
                    else:
                        os.link(temporary, target)
                except FileExistsError:
                    continue
                return target
        finally:
            temporary.unlink(missing_ok=True)
