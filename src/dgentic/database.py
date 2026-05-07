"""SQLAlchemy session helper for metadata-backed services."""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from dgentic.memory.models import Base
from dgentic.settings import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_database_url_cache: str | None = None


def _database_url() -> str:
    data_dir = get_settings().data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{data_dir / 'dgentic.db'}"


def _get_session_factory() -> sessionmaker[Session]:
    global _database_url_cache, _engine, _session_factory

    database_url = _database_url()
    if _session_factory is None or _database_url_cache != database_url:
        _database_url_cache = database_url
        _engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=_engine)
        _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _session_factory


def get_db_session() -> Session:
    return _get_session_factory()()
