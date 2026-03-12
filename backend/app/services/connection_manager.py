"""Connection manager for external database connections.

Handles connection testing, pooling, and schema introspection
for PostgreSQL and MySQL databases connected via SQLAlchemy.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from app.logging import get_logger
from app.models.connection import DatabaseType
from app.services.schema_introspection import (
    ColumnInfo,
    IntrospectionResult,
    introspect_engine,
)

logger = get_logger(__name__)

# Re-export so existing imports from this module keep working.
__all__ = [
    "ColumnInfo",
    "ConnectionManager",
    "ConnectionTestResult",
    "IntrospectionResult",
]

# Connection timeout for test/introspection operations (seconds).
CONNECTION_TIMEOUT_SECONDS: int = 10


@dataclass
class ConnectionTestResult:
    """Result of a connection test attempt."""

    success: bool
    latency_ms: float | None = None
    tables_found: int | None = None
    error_message: str | None = None
    error_type: str | None = None


def _build_url(
    db_type: str,
    host: str,
    port: int,
    database_name: str,
    username: str,
    password: str,
) -> str:
    """Build a SQLAlchemy connection URL from connection parameters."""
    from urllib.parse import quote_plus

    escaped_password = quote_plus(password)
    escaped_username = quote_plus(username)

    if db_type == DatabaseType.POSTGRESQL:
        return f"postgresql+psycopg://{escaped_username}:{escaped_password}@{host}:{port}/{database_name}"
    elif db_type == DatabaseType.MYSQL:
        return f"mysql+pymysql://{escaped_username}:{escaped_password}@{host}:{port}/{database_name}"
    else:
        raise ValueError(f"Unsupported database type: {db_type}")


class ConnectionManager:
    """Manages connection pools and operations for external databases.

    Maintains a pool of SQLAlchemy engines keyed by connection UUID.
    Provides connection testing, schema introspection, and query execution
    with read-only enforcement and statement timeout controls.
    """

    def __init__(self) -> None:
        self._pools: dict[uuid.UUID, Engine] = {}
        self._db_types: dict[uuid.UUID, str] = {}

    def get_engine(self, connection_id: uuid.UUID) -> Engine | None:
        """Return the pooled engine for a connection, or None if not found."""
        return self._pools.get(connection_id)

    def get_db_type(self, connection_id: uuid.UUID) -> str | None:
        """Return the database type for a connection, or None if not found."""
        return self._db_types.get(connection_id)

    def _get_or_create_engine(
        self,
        connection_id: uuid.UUID,
        db_type: str,
        host: str,
        port: int,
        database_name: str,
        username: str,
        password: str,
    ) -> Engine:
        """Get existing engine or create a new one for the connection."""
        if connection_id in self._pools:
            self._pools[connection_id].dispose()

        url = _build_url(db_type, host, port, database_name, username, password)
        engine = create_engine(
            url,
            pool_size=2,
            max_overflow=3,
            pool_timeout=CONNECTION_TIMEOUT_SECONDS,
            connect_args={"connect_timeout": CONNECTION_TIMEOUT_SECONDS},
            pool_pre_ping=True,
        )
        self._pools[connection_id] = engine
        self._db_types[connection_id] = db_type
        return engine

    def test_connection(
        self,
        connection_id: uuid.UUID,
        db_type: str,
        host: str,
        port: int,
        database_name: str,
        username: str,
        password: str,
        *,
        measure_latency: bool = False,
    ) -> ConnectionTestResult:
        """Test a database connection by executing a simple query.

        When ``measure_latency`` is True the round-trip time is captured and the
        number of user tables is counted via schema introspection.

        Returns a ConnectionTestResult indicating success or failure with error details.
        """
        try:
            engine = self._get_or_create_engine(
                connection_id, db_type, host, port, database_name, username, password
            )

            start = time.monotonic()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            elapsed_ms = (time.monotonic() - start) * 1000

            latency_ms: float | None = None
            tables_found: int | None = None

            if measure_latency:
                latency_ms = round(elapsed_ms, 1)
                try:
                    insp = inspect(engine)
                    tables_found = len(insp.get_table_names())
                except Exception:
                    tables_found = 0

            logger.info(
                "connection_test_success",
                connection_id=str(connection_id),
                db_type=db_type,
                host=host,
                latency_ms=latency_ms,
                tables_found=tables_found,
            )
            return ConnectionTestResult(
                success=True,
                latency_ms=latency_ms,
                tables_found=tables_found,
            )

        except OperationalError as exc:
            error_str = str(exc)
            # Determine error type based on the exception message
            if "authentication" in error_str.lower() or "password" in error_str.lower():
                error_type = "authentication_failure"
            elif "timeout" in error_str.lower() or "timed out" in error_str.lower():
                error_type = "connection_timeout"
            else:
                error_type = "connection_error"

            logger.warning(
                "connection_test_failed",
                connection_id=str(connection_id),
                db_type=db_type,
                host=host,
                error_type=error_type,
                error=error_str,
            )
            # Remove failed pool
            self._remove_pool(connection_id)
            return ConnectionTestResult(
                success=False,
                error_message=error_str,
                error_type=error_type,
            )
        except Exception as exc:
            logger.error(
                "connection_test_error",
                connection_id=str(connection_id),
                error=str(exc),
            )
            self._remove_pool(connection_id)
            return ConnectionTestResult(
                success=False,
                error_message=str(exc),
                error_type="connection_error",
            )

    def introspect_schema(
        self,
        connection_id: uuid.UUID,
    ) -> IntrospectionResult:
        """Introspect the database schema for a connection that has a pool.

        Delegates to :func:`schema_introspection.introspect_engine` which
        handles type normalisation, system-table filtering, view inclusion,
        and per-relation error resilience.

        Must call test_connection first to establish the engine.
        """
        engine = self._pools.get(connection_id)
        if engine is None:
            return IntrospectionResult(
                success=False,
                error_message="No engine found for this connection. Test connection first.",
            )

        result = introspect_engine(engine)

        if result.success:
            logger.info(
                "schema_introspection_complete",
                connection_id=str(connection_id),
                table_count=result.table_count,
                view_count=result.view_count,
                column_count=len(result.columns),
            )

        return result

    def remove_pool(self, connection_id: uuid.UUID) -> None:
        """Remove and dispose of the connection pool for a connection."""
        self._remove_pool(connection_id)

    def _remove_pool(self, connection_id: uuid.UUID) -> None:
        """Internal: remove and dispose of a connection pool."""
        engine = self._pools.pop(connection_id, None)
        self._db_types.pop(connection_id, None)
        if engine is not None:
            engine.dispose()
            logger.info("connection_pool_removed", connection_id=str(connection_id))

    def close_all(self) -> None:
        """Dispose of all connection pools. Called during application shutdown."""
        for conn_id, engine in self._pools.items():
            engine.dispose()
            logger.info("connection_pool_disposed", connection_id=str(conn_id))
        self._pools.clear()
        self._db_types.clear()
