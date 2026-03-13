"""Connection-related enums and constants.

The SQLAlchemy ORM model for Connection lives in ``app.models.orm``.
This module provides enums and constants used by both the ORM layer
and the connection management services.
"""

from __future__ import annotations

from enum import StrEnum


class ConnectionStatus(StrEnum):
    """Status for a database connection."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class DatabaseType(StrEnum):
    """Supported database types for external connections."""

    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
