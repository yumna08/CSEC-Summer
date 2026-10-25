import logging
import os
from contextlib import contextmanager
from typing import Generator, Optional
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from app.core.config import (
    DATABASE_URL,
    DB_MAX_OVERFLOW,
    DB_POOL_PRE_PING,
    DB_POOL_SIZE,
)

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""
    pass


def normalize_database_url(raw_url: str) -> str:
    """
    Ensure PostgreSQL URLs use the Psycopg 3 driver explicitly (postgresql+psycopg://).
    Handles legacy 'postgres://' prefixes safely.
    """
    url = (raw_url or "").strip()
    if not url:
        return ""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and not url.startswith("postgresql+psycopg://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker[Session]] = None


def get_engine() -> Engine:
    """Get or create the global SQLAlchemy Engine."""
    global _engine
    if _engine is not None:
        return _engine

    raw_url = os.getenv("DATABASE_URL", DATABASE_URL)
    url = normalize_database_url(raw_url)

    if not url:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set DATABASE_URL in backend/.env or your environment."
        )

    is_sqlite = url.startswith("sqlite")

    engine_kwargs = {"pool_pre_ping": DB_POOL_PRE_PING}
    if not is_sqlite:
        engine_kwargs["pool_size"] = DB_POOL_SIZE
        engine_kwargs["max_overflow"] = DB_MAX_OVERFLOW
    else:
        engine_kwargs["connect_args"] = {"check_same_thread": False}

    _engine = create_engine(url, **engine_kwargs)
    logger.info(
        "SQLAlchemy engine initialized (dialect: %s, driver: %s)",
        _engine.dialect.name,
        _engine.dialect.driver,
    )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Get or create the sessionmaker factory."""
    global _session_factory
    if _session_factory is not None:
        return _session_factory

    engine = get_engine()
    _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _session_factory


def SessionLocal() -> Session:
    """Convenience callable matching standard FastAPI convention."""
    factory = get_session_factory()
    return factory()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """Context manager for standalone scripts or service calls outside requests."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def reset_engine_for_testing(custom_engine: Optional[Engine] = None) -> None:
    """Helper for test suites to inject mock or in-memory engines."""
    global _engine, _session_factory
    _engine = custom_engine
    if custom_engine is not None:
        _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=custom_engine)
    else:
        _session_factory = None
