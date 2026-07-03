"""Cross-platform paths for mutable SammyAI runtime data."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sys
from typing import Mapping


APP_NAME = "SammyAI"
APP_SLUG = "sammyai"


@dataclass(frozen=True)
class AppPaths:
    """All mutable locations used by one SammyAI installation."""

    config_dir: Path
    data_dir: Path
    cache_dir: Path
    log_dir: Path

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    @property
    def rag_index_dir(self) -> Path:
        return self.data_dir / "rag" / "index"

    @property
    def embedding_cache_dir(self) -> Path:
        return self.cache_dir / "embeddings"

    def ensure_created(self) -> "AppPaths":
        for path in (
            self.config_dir,
            self.data_dir,
            self.cache_dir,
            self.log_dir,
            self.sessions_dir,
            self.rag_index_dir,
            self.embedding_cache_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        return self


def _default_roots(
    env: Mapping[str, str],
    home: Path,
    platform: str,
) -> tuple[Path, Path, Path, Path]:
    if platform == "win32":
        local = Path(env.get("LOCALAPPDATA", home / "AppData" / "Local"))
        roaming = Path(env.get("APPDATA", home / "AppData" / "Roaming"))
        return (
            roaming / APP_NAME,
            local / APP_NAME / "data",
            local / APP_NAME / "cache",
            local / APP_NAME / "logs",
        )

    if platform == "darwin":
        application_support = home / "Library" / "Application Support" / APP_NAME
        return (
            application_support / "config",
            application_support / "data",
            home / "Library" / "Caches" / APP_NAME,
            home / "Library" / "Logs" / APP_NAME,
        )

    config_home = Path(env.get("XDG_CONFIG_HOME", home / ".config"))
    data_home = Path(env.get("XDG_DATA_HOME", home / ".local" / "share"))
    cache_home = Path(env.get("XDG_CACHE_HOME", home / ".cache"))
    state_home = Path(env.get("XDG_STATE_HOME", home / ".local" / "state"))
    return (
        config_home / APP_SLUG,
        data_home / APP_SLUG,
        cache_home / APP_SLUG,
        state_home / APP_SLUG / "logs",
    )


def get_app_paths(
    *,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    platform: str | None = None,
    create: bool = True,
) -> AppPaths:
    """Resolve runtime locations, allowing explicit overrides for tests and users."""

    resolved_env = os.environ if env is None else env
    resolved_home = Path.home() if home is None else Path(home)
    resolved_platform = sys.platform if platform is None else platform
    config_dir, data_dir, cache_dir, log_dir = _default_roots(
        resolved_env,
        resolved_home,
        resolved_platform,
    )

    paths = AppPaths(
        config_dir=Path(resolved_env.get("SAMMYAI_CONFIG_DIR", config_dir)),
        data_dir=Path(resolved_env.get("SAMMYAI_DATA_DIR", data_dir)),
        cache_dir=Path(resolved_env.get("SAMMYAI_CACHE_DIR", cache_dir)),
        log_dir=Path(resolved_env.get("SAMMYAI_LOG_DIR", log_dir)),
    )
    return paths.ensure_created() if create else paths


def _copy_directory_if_destination_empty(source: Path, destination: Path) -> bool:
    if not source.is_dir():
        return False
    if destination.exists() and any(destination.iterdir()):
        return False
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, dirs_exist_ok=True)
    return True


def migrate_legacy_runtime_data(source_root: Path, paths: AppPaths) -> list[str]:
    """Copy legacy source-tree state to the new runtime paths once.

    Source data is intentionally retained so migration is non-destructive.
    """

    root = Path(source_root)
    migrated: list[str] = []
    candidates = (
        (root / "llm" / "chat_sessions", paths.sessions_dir, "chat sessions"),
        (root / "cache" / "index", paths.rag_index_dir, "RAG index"),
        (root / "cache" / "embeddings", paths.embedding_cache_dir, "embedding cache"),
    )
    for source, destination, label in candidates:
        if _copy_directory_if_destination_empty(source, destination):
            migrated.append(label)
    return migrated
