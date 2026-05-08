"""SQLAlchemy session helper for metadata-backed services."""

from pathlib import Path
from shutil import copy2

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from dgentic.migrations import initialize_database
from dgentic.settings import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_database_url_cache: str | None = None


def _database_url() -> str:
    return get_settings().effective_database_url


def _connect_args(database_url: str) -> dict[str, bool]:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        return {"check_same_thread": False}
    return {}


def _prepare_local_sqlite_path(database_url: str) -> None:
    database_path = _sqlite_database_path(database_url)
    if database_path:
        database_path.parent.mkdir(parents=True, exist_ok=True)


def _sqlite_database_path(database_url: str) -> Path | None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None

    database_path = url.translate_connect_args().get("database")
    if not database_path:
        return None

    return Path(database_path)


def sqlite_database_path() -> Path | None:
    """Return the configured file-backed SQLite database path, when applicable."""

    return _sqlite_database_path(_database_url())


def backup_sqlite_database(destination: str | Path) -> Path:
    """Create a copy of the configured file-backed SQLite database."""

    database_path = sqlite_database_path()
    if database_path is None:
        raise ValueError("SQLite backup is only supported for file-backed SQLite databases.")

    _get_session_factory()
    if not database_path.is_file():
        raise FileNotFoundError(f"Configured SQLite database does not exist: {database_path}")

    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    copy2(database_path, destination_path)
    return destination_path


def restore_sqlite_database(source: str | Path) -> Path:
    """Restore the configured file-backed SQLite database from a backup copy."""

    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite backup does not exist: {source_path}")

    database_path = sqlite_database_path()
    if database_path is None:
        raise ValueError("SQLite restore is only supported for file-backed SQLite databases.")

    reset_database_state()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    copy2(source_path, database_path)
    reset_database_state()
    return database_path


def _get_session_factory() -> sessionmaker[Session]:
    global _database_url_cache, _engine, _session_factory

    database_url = _database_url()
    if _session_factory is None or _database_url_cache != database_url:
        _database_url_cache = database_url
        _prepare_local_sqlite_path(database_url)
        _engine = create_engine(database_url, connect_args=_connect_args(database_url))
        initialize_database(_engine)
        _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _session_factory


def get_db_session() -> Session:
    return _get_session_factory()()


def reset_database_state() -> None:
    """Reset cached engine/session state so tests can rebuild from changed settings."""

    global _database_url_cache, _engine, _session_factory

    if _engine is not None:
        _engine.dispose()

    _engine = None
    _session_factory = None
    _database_url_cache = None
