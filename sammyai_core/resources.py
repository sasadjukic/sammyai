"""Resolve read-only application assets in source and installed layouts."""

from __future__ import annotations

from pathlib import Path
import sys


def source_root() -> Path:
    return Path(__file__).resolve().parent.parent


def asset_path(*parts: str) -> Path:
    candidates = (
        source_root().joinpath(*parts),
        Path(sys.prefix).joinpath("share", "sammyai", *parts),
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]
