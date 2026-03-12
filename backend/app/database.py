"""Database session management for SQLAlchemy.

Provides a sessionmaker factory attached to app.state and a FastAPI dependency
that yields per-request sessions with automatic commit/rollback.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_db_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine from a database URL.

    For PostgreSQL (production), uses psycopg as the driver.
    For SQLite (testing), uses the built-in driver.
    """
    connect_args: dict = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(database_url, connect_args=connect_args)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a sessionmaker bound to the given engine."""
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db_session(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    """Yield a database session and handle commit/rollback.

    This is a generator used as a FastAPI dependency via a closure
    that captures the session factory from app.state.
    """
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
