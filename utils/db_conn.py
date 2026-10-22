"""資料庫連線。engine 在第一次使用時才建立，測試可以用 set_session_factory 換成 SQLite。"""
import contextlib
from collections.abc import Callable, Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from utils.settings import env

_session_factory: Callable[[], Session] | None = None


def database_url() -> str:
    """優先使用 DATABASE_URL，否則由 POSTGRES_* 組出（同 PTCFormosAI）。"""
    url = env("DATABASE_URL")
    if url:
        return url
    host = env("POSTGRES_HOST", "127.0.0.1")
    port = env("POSTGRES_PORT", "5433")
    db = env("POSTGRES_DB", "llmport")
    user = env("POSTGRES_USER", "llmport")
    password = env("POSTGRES_PASSWORD", "")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


def session_factory() -> Callable[[], Session]:
    global _session_factory
    if _session_factory is None:
        engine = create_engine(database_url(), pool_pre_ping=True, pool_timeout=30, pool_recycle=3600,
                               connect_args={"connect_timeout": 10})
        _session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return _session_factory


def set_session_factory(factory: Callable[[], Session] | None) -> None:
    global _session_factory
    _session_factory = factory


def get_db() -> Generator[Session, None, None]:
    session = session_factory()()
    try:
        yield session
    finally:
        session.close()


@contextlib.contextmanager
def get_db_context() -> Generator[Session, None, None]:
    session = session_factory()()
    try:
        yield session
    finally:
        session.close()
