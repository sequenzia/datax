"""FastAPI dependency injection for shared application resources."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.services.bookmark_service import BookmarkService
from app.services.connection_manager import ConnectionManager
from app.services.duckdb_manager import DuckDBManager


def get_settings(request: Request) -> Settings:
    """Retrieve application settings from app state.

    Settings are attached to ``app.state.settings`` during app creation.
    """
    return request.app.state.settings


def get_storage_path(request: Request) -> Path:
    """Retrieve the file storage path from app settings."""
    settings: Settings = request.app.state.settings
    return settings.datax_storage_path


def get_session_factory(request: Request) -> sessionmaker[Session]:
    """Retrieve the session factory from application state.

    Used by background tasks that need to create their own sessions
    after the request session is closed.
    """
    return request.app.state.session_factory


def get_duckdb_manager(request: Request) -> DuckDBManager:
    """Retrieve the DuckDB manager from application state.

    The DuckDB manager is initialized during app lifespan startup and
    attached to ``app.state.duckdb_manager``.
    """
    return request.app.state.duckdb_manager


def get_connection_manager(request: Request) -> ConnectionManager:
    """Retrieve the connection manager from application state.

    The connection manager is initialized during app creation and
    attached to ``app.state.connection_manager``.
    """
    return request.app.state.connection_manager


def get_db(request: Request) -> Generator[Session, None, None]:
    """Yield a database session from the app-level session factory.

    The session factory is initialized during app startup and attached
    to ``app.state.session_factory``.
    """
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_bookmark_service(
    db: Session = Depends(get_db),
) -> BookmarkService:
    """Create a BookmarkService instance with the current DB session."""
    return BookmarkService(db)
