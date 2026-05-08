"""SQLAlchemy session helper for metadata-backed services."""

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
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return

    database_path = url.translate_connect_args().get("database")
    if database_path:
        from pathlib import Path

        Path(database_path).parent.mkdir(parents=True, exist_ok=True)


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
