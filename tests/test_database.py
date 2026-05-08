"""Tests for database settings, session caching, and migration baseline."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, inspect, select

from dgentic import database
from dgentic.database import _connect_args, get_db_session, reset_database_state
from dgentic.memory.models import MemoryMetadata
from dgentic.migrations import (
    BASELINE_MIGRATION_ID,
    initialize_database,
    list_applied_migrations,
    schema_migrations,
)
from dgentic.settings import Settings, get_settings


@pytest.fixture(autouse=True)
def isolated_database_state(monkeypatch):
    """Keep settings and SQLAlchemy module caches from leaking across tests."""

    for env_name in ("DGENTIC_DATABASE_URL", "DGENTIC_ROOT_DIR", "DGENTIC_DATA_DIR"):
        monkeypatch.delenv(env_name, raising=False)

    get_settings.cache_clear()
    reset_database_state()
    yield
    reset_database_state()
    get_settings.cache_clear()


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def test_effective_database_url_prefers_explicit_database_url(tmp_path):
    explicit_url = sqlite_url(tmp_path / "explicit.db")

    settings = Settings(
        root_dir=tmp_path / "root",
        data_dir="ignored-data",
        database_url=explicit_url,
    )

    assert settings.effective_database_url == explicit_url


def test_effective_database_url_resolves_relative_data_dir_under_root_dir(tmp_path):
    settings = Settings(root_dir=tmp_path / "root", data_dir="relative-data")

    assert settings.effective_database_url == sqlite_url(
        tmp_path / "root" / "relative-data" / "dgentic.db"
    )


def test_effective_database_url_uses_absolute_data_dir_directly(tmp_path):
    absolute_data_dir = tmp_path / "absolute-data"
    settings = Settings(root_dir=tmp_path / "root", data_dir=absolute_data_dir)

    assert settings.effective_database_url == sqlite_url(absolute_data_dir / "dgentic.db")


def test_reset_database_state_and_settings_cache_switch_to_new_database_url(
    monkeypatch,
    tmp_path,
):
    first_root = tmp_path / "first-root"
    second_root = tmp_path / "second-root"

    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(first_root))
    get_settings.cache_clear()
    first_session = get_db_session()
    first_session.add(MemoryMetadata(entity_type="memory", entity_id="first-db"))
    first_session.commit()
    first_session.close()

    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(second_root))
    get_settings.cache_clear()
    reset_database_state()
    second_session = get_db_session()

    try:
        assert database._database_url_cache == sqlite_url(second_root / ".dgentic" / "dgentic.db")
        assert (
            second_session.execute(
                select(MemoryMetadata).where(MemoryMetadata.entity_id == "first-db")
            ).scalar_one_or_none()
            is None
        )
    finally:
        second_session.close()


def test_get_db_session_creates_default_sqlite_parent_directory_and_database_file(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv("DGENTIC_DATA_DIR", "nested/data")
    get_settings.cache_clear()

    session = get_db_session()
    session.close()

    database_path = tmp_path / "nested" / "data" / "dgentic.db"
    assert database_path.parent.is_dir()
    assert database_path.is_file()


def test_migration_baseline_creates_expected_tables(tmp_path):
    engine = create_engine(sqlite_url(tmp_path / "baseline.db"))

    initialize_database(engine)

    assert {
        "memory_metadata",
        "vector_embeddings",
        "tool_registry",
        "schema_migrations",
    }.issubset(inspect(engine).get_table_names())


def test_list_applied_migrations_returns_baseline_after_initialization(tmp_path):
    engine = create_engine(sqlite_url(tmp_path / "migrations.db"))
    initialize_database(engine)

    assert list_applied_migrations(engine) == [BASELINE_MIGRATION_ID]


def test_initialize_database_is_idempotent_and_does_not_duplicate_ledger_rows(tmp_path):
    engine = create_engine(sqlite_url(tmp_path / "idempotent.db"))

    initialize_database(engine)
    initialize_database(engine)

    with engine.begin() as connection:
        ledger_count = connection.execute(
            select(func.count()).select_from(schema_migrations)
        ).scalar_one()

    assert ledger_count == 1
    assert list_applied_migrations(engine) == [BASELINE_MIGRATION_ID]


def test_metadata_record_persists_after_session_close_and_database_state_reset(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    get_settings.cache_clear()
    session = get_db_session()
    session.add(
        MemoryMetadata(
            entity_type="memory",
            entity_id="persistent-memory",
            tags=["qa"],
            description="Persists across engine reset",
        )
    )
    session.commit()
    session.close()

    reset_database_state()
    new_session = get_db_session()
    try:
        persisted = new_session.execute(
            select(MemoryMetadata).where(MemoryMetadata.entity_id == "persistent-memory")
        ).scalar_one()
    finally:
        new_session.close()

    assert persisted.description == "Persists across engine reset"
    assert persisted.tags == ["qa"]


def test_sqlite_connect_args_helper_and_explicit_sqlite_url(tmp_path):
    explicit_sqlite_url = sqlite_url(tmp_path / "explicit-helper.db")

    assert Settings(database_url=explicit_sqlite_url).effective_database_url == explicit_sqlite_url
    assert _connect_args(explicit_sqlite_url) == {"check_same_thread": False}
    assert _connect_args("postgresql://user:pass@example.test/dgentic") == {}
