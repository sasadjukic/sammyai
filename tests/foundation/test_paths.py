from pathlib import Path

from sammyai_core.paths import AppPaths, get_app_paths, migrate_legacy_runtime_data


def test_windows_paths_use_standard_application_directories(tmp_path: Path):
    paths = get_app_paths(
        env={
            "APPDATA": str(tmp_path / "roaming"),
            "LOCALAPPDATA": str(tmp_path / "local"),
        },
        home=tmp_path,
        platform="win32",
        create=False,
    )

    assert paths.config_dir == tmp_path / "roaming" / "SammyAI"
    assert paths.data_dir == tmp_path / "local" / "SammyAI" / "data"
    assert paths.cache_dir == tmp_path / "local" / "SammyAI" / "cache"


def test_environment_overrides_are_created(tmp_path: Path):
    paths = get_app_paths(
        env={
            "SAMMYAI_CONFIG_DIR": str(tmp_path / "config"),
            "SAMMYAI_DATA_DIR": str(tmp_path / "data"),
            "SAMMYAI_CACHE_DIR": str(tmp_path / "cache"),
            "SAMMYAI_LOG_DIR": str(tmp_path / "logs"),
        },
        home=tmp_path,
        platform="linux",
    )

    assert paths.sessions_dir.is_dir()
    assert paths.rag_index_dir.is_dir()
    assert paths.embedding_cache_dir.is_dir()
    assert paths.log_dir.is_dir()


def test_legacy_migration_is_non_destructive_and_does_not_overwrite(tmp_path: Path):
    source = tmp_path / "source"
    legacy_session = source / "llm" / "chat_sessions" / "session.json"
    legacy_session.parent.mkdir(parents=True)
    legacy_session.write_text('{"legacy": true}', encoding="utf-8")

    paths = AppPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        log_dir=tmp_path / "logs",
    ).ensure_created()

    assert migrate_legacy_runtime_data(source, paths) == ["chat sessions"]
    assert legacy_session.exists()
    assert (paths.sessions_dir / "session.json").read_text(encoding="utf-8") == (
        '{"legacy": true}'
    )

    legacy_session.write_text('{"legacy": "changed"}', encoding="utf-8")
    assert migrate_legacy_runtime_data(source, paths) == []
    assert (paths.sessions_dir / "session.json").read_text(encoding="utf-8") == (
        '{"legacy": true}'
    )
