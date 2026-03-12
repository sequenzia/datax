"""Connection CRUD API endpoints.

Provides endpoints for managing external database connections with
encrypted credential storage, connection testing, and schema introspection.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.dependencies import get_connection_manager
from app.encryption import EncryptionError, decrypt_value, encrypt_value
from app.logging import get_logger
from app.models.connection import ConnectionStatus, DatabaseType
from app.services.connection_manager import ConnectionManager

logger = get_logger(__name__)

router = APIRouter(prefix="/connections", tags=["connections"])

SUPPORTED_DB_TYPES = [t.value for t in DatabaseType]


# ---------------------------------------------------------------------------
# Pydantic request/response schemas
# ---------------------------------------------------------------------------


class ConnectionCreateRequest(BaseModel):
    """Request body for creating a new database connection."""

    name: str = Field(..., min_length=1, max_length=255, description="Connection display name")
    db_type: str = Field(..., description="Database type (postgresql, mysql)")
    host: str = Field(..., min_length=1, max_length=255, description="Database host")
    port: int = Field(..., gt=0, le=65535, description="Database port")
    database_name: str = Field(
        ..., min_length=1, max_length=255, description="Database name"
    )
    username: str = Field(..., min_length=1, max_length=255, description="Database username")
    password: str = Field(..., min_length=1, description="Database password")


class ConnectionUpdateRequest(BaseModel):
    """Request body for updating an existing database connection."""

    name: str | None = Field(None, min_length=1, max_length=255)
    db_type: str | None = Field(None)
    host: str | None = Field(None, min_length=1, max_length=255)
    port: int | None = Field(None, gt=0, le=65535)
    database_name: str | None = Field(None, min_length=1, max_length=255)
    username: str | None = Field(None, min_length=1, max_length=255)
    password: str | None = Field(None, min_length=1)


class ConnectionResponse(BaseModel):
    """Response schema for a single connection (password never included)."""

    id: str
    name: str
    db_type: str
    host: str
    port: int
    database_name: str
    username: str
    status: str
    last_tested_at: str | None
    created_at: str
    updated_at: str


class ConnectionListResponse(BaseModel):
    """Response schema for listing connections."""

    connections: list[ConnectionResponse]


class ConnectionTestResponse(BaseModel):
    """Response schema for testing an existing connection."""

    status: str
    latency_ms: float | None = None
    tables_found: int | None = None
    error: str | None = None


class SchemaRefreshResponse(BaseModel):
    """Response schema for schema refresh endpoint."""

    source_id: str
    tables_found: int
    columns_updated: int
    refreshed_at: str


# ---------------------------------------------------------------------------
# In-memory storage (temporary until PostgreSQL session is wired up)
# ---------------------------------------------------------------------------

# Stores connection records keyed by UUID.
# Each record is a dict with all fields except the raw password.
_connections: dict[uuid.UUID, dict[str, Any]] = {}


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(UTC).isoformat()


def _connection_to_response(record: dict[str, Any]) -> ConnectionResponse:
    """Convert an internal connection record to a response schema."""
    return ConnectionResponse(
        id=str(record["id"]),
        name=record["name"],
        db_type=record["db_type"],
        host=record["host"],
        port=record["port"],
        database_name=record["database_name"],
        username=record["username"],
        status=record["status"],
        last_tested_at=record.get("last_tested_at"),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


def _get_connection_or_404(connection_id: uuid.UUID) -> dict[str, Any]:
    """Retrieve a connection record or raise 404."""
    record = _connections.get(connection_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Connection {connection_id} not found")
    return record


# ---------------------------------------------------------------------------
# Schema metadata storage (temporary until PostgreSQL session is wired up)
# ---------------------------------------------------------------------------

# Stores schema metadata keyed by source_id (connection UUID).
_schema_metadata: dict[uuid.UUID, list[dict[str, Any]]] = {}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_connection(
    body: ConnectionCreateRequest,
    conn_mgr: ConnectionManager = Depends(get_connection_manager),
) -> ConnectionResponse:
    """Create a new database connection.

    Validates the database type, encrypts the password, tests the connection,
    and auto-introspects the schema on success.
    """
    # Validate db_type
    if body.db_type not in SUPPORTED_DB_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid db_type '{body.db_type}'. Supported types: {SUPPORTED_DB_TYPES}",
        )

    connection_id = uuid.uuid4()
    now = _now_iso()

    # Encrypt the password
    encrypted_password = encrypt_value(body.password)

    # Test the connection
    test_result = conn_mgr.test_connection(
        connection_id=connection_id,
        db_type=body.db_type,
        host=body.host,
        port=body.port,
        database_name=body.database_name,
        username=body.username,
        password=body.password,
    )

    if not test_result.success:
        # Determine appropriate status code based on error type
        if test_result.error_type == "authentication_failure":
            raise HTTPException(
                status_code=400,
                detail=f"Authentication failed: {test_result.error_message}",
            )
        elif test_result.error_type == "connection_timeout":
            raise HTTPException(
                status_code=408,
                detail=(
                    f"Connection timed out after {10}s. "
                    "Troubleshooting tips: "
                    "1) Verify the host and port are correct. "
                    "2) Check that the database server is running. "
                    "3) Ensure firewall rules allow the connection."
                ),
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Connection failed: {test_result.error_message}. "
                "Please verify your connection parameters and try again.",
            )

    # Connection succeeded - store it
    status = ConnectionStatus.CONNECTED.value

    record: dict[str, Any] = {
        "id": connection_id,
        "name": body.name,
        "db_type": body.db_type,
        "host": body.host,
        "port": body.port,
        "database_name": body.database_name,
        "username": body.username,
        "encrypted_password": encrypted_password,
        "status": status,
        "last_tested_at": now,
        "created_at": now,
        "updated_at": now,
    }
    _connections[connection_id] = record

    # Auto-introspect schema
    intro_result = conn_mgr.introspect_schema(connection_id)
    if intro_result.success:
        _schema_metadata[connection_id] = [
            {
                "id": uuid.uuid4(),
                "source_id": connection_id,
                "source_type": "connection",
                "table_name": col.table_name,
                "column_name": col.column_name,
                "data_type": col.data_type,
                "is_nullable": col.is_nullable,
                "is_primary_key": col.is_primary_key,
                "foreign_key_ref": col.foreign_key_ref,
            }
            for col in intro_result.columns
        ]
        logger.info(
            "connection_schema_introspected",
            connection_id=str(connection_id),
            column_count=len(intro_result.columns),
        )

    logger.info(
        "connection_created",
        connection_id=str(connection_id),
        name=body.name,
        db_type=body.db_type,
    )

    return _connection_to_response(record)


@router.get("")
async def list_connections() -> ConnectionListResponse:
    """List all database connections.

    Returns connection metadata with status for each connection.
    Passwords are never included in the response.
    """
    connections = [_connection_to_response(r) for r in _connections.values()]
    return ConnectionListResponse(connections=connections)


@router.put("/{connection_id}")
async def update_connection(
    connection_id: uuid.UUID,
    body: ConnectionUpdateRequest,
    conn_mgr: ConnectionManager = Depends(get_connection_manager),
) -> ConnectionResponse:
    """Update an existing database connection.

    Re-tests the connection and re-introspects the schema after update.
    Encrypts new password if provided.
    """
    record = _get_connection_or_404(connection_id)

    # Apply updates
    if body.name is not None:
        record["name"] = body.name
    if body.db_type is not None:
        if body.db_type not in SUPPORTED_DB_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid db_type '{body.db_type}'. Supported types: {SUPPORTED_DB_TYPES}",
            )
        record["db_type"] = body.db_type
    if body.host is not None:
        record["host"] = body.host
    if body.port is not None:
        record["port"] = body.port
    if body.database_name is not None:
        record["database_name"] = body.database_name
    if body.username is not None:
        record["username"] = body.username
    if body.password is not None:
        record["encrypted_password"] = encrypt_value(body.password)

    # Decrypt password for connection test
    password = (
        body.password
        if body.password is not None
        else decrypt_value(record["encrypted_password"])
    )

    # Re-test connection
    test_result = conn_mgr.test_connection(
        connection_id=connection_id,
        db_type=record["db_type"],
        host=record["host"],
        port=record["port"],
        database_name=record["database_name"],
        username=record["username"],
        password=password,
    )

    now = _now_iso()
    record["last_tested_at"] = now
    record["updated_at"] = now

    if test_result.success:
        record["status"] = ConnectionStatus.CONNECTED.value

        # Re-introspect schema
        intro_result = conn_mgr.introspect_schema(connection_id)
        if intro_result.success:
            _schema_metadata[connection_id] = [
                {
                    "id": uuid.uuid4(),
                    "source_id": connection_id,
                    "source_type": "connection",
                    "table_name": col.table_name,
                    "column_name": col.column_name,
                    "data_type": col.data_type,
                    "is_nullable": col.is_nullable,
                    "is_primary_key": col.is_primary_key,
                    "foreign_key_ref": col.foreign_key_ref,
                }
                for col in intro_result.columns
            ]
    else:
        record["status"] = ConnectionStatus.ERROR.value

        if test_result.error_type == "authentication_failure":
            raise HTTPException(
                status_code=400,
                detail=f"Authentication failed: {test_result.error_message}",
            )
        elif test_result.error_type == "connection_timeout":
            raise HTTPException(
                status_code=408,
                detail=(
                    f"Connection timed out after {10}s. "
                    "Troubleshooting tips: "
                    "1) Verify the host and port are correct. "
                    "2) Check that the database server is running. "
                    "3) Ensure firewall rules allow the connection."
                ),
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Connection failed: {test_result.error_message}. "
                "Please verify your connection parameters and try again.",
            )

    logger.info(
        "connection_updated",
        connection_id=str(connection_id),
        status=record["status"],
    )

    return _connection_to_response(record)


@router.delete("/{connection_id}", status_code=204)
async def delete_connection(
    connection_id: uuid.UUID,
    conn_mgr: ConnectionManager = Depends(get_connection_manager),
) -> Response:
    """Delete a database connection.

    Removes associated schema metadata and closes the connection pool.
    """
    _get_connection_or_404(connection_id)

    # Remove schema metadata
    _schema_metadata.pop(connection_id, None)

    # Close connection pool
    conn_mgr.remove_pool(connection_id)

    # Remove connection record
    del _connections[connection_id]

    logger.info("connection_deleted", connection_id=str(connection_id))

    return Response(status_code=204)


class ConnectionTestParamsRequest(BaseModel):
    """Request body for testing connection parameters without saving."""

    db_type: str = Field(..., description="Database type (postgresql, mysql)")
    host: str = Field(..., min_length=1, max_length=255, description="Database host")
    port: int = Field(..., gt=0, le=65535, description="Database port")
    database_name: str = Field(
        ..., min_length=1, max_length=255, description="Database name"
    )
    username: str = Field(..., min_length=1, max_length=255, description="Database username")
    password: str = Field(..., min_length=1, description="Database password")


@router.post("/test-params")
async def test_connection_params(
    body: ConnectionTestParamsRequest,
    conn_mgr: ConnectionManager = Depends(get_connection_manager),
) -> ConnectionTestResponse:
    """Test connection parameters without saving.

    Validates connectivity, measures latency, and counts tables for
    the given connection parameters. No data is persisted.
    """
    if body.db_type not in SUPPORTED_DB_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid db_type '{body.db_type}'. Supported types: {SUPPORTED_DB_TYPES}",
        )

    test_result = conn_mgr.test_connection(
        connection_id=uuid.uuid4(),
        db_type=body.db_type,
        host=body.host,
        port=body.port,
        database_name=body.database_name,
        username=body.username,
        password=body.password,
        measure_latency=True,
    )

    if test_result.success:
        logger.info(
            "connection_test_params_passed",
            db_type=body.db_type,
            host=body.host,
        )
        return ConnectionTestResponse(
            status="connected",
            latency_ms=test_result.latency_ms,
            tables_found=test_result.tables_found,
        )

    logger.warning(
        "connection_test_params_failed",
        db_type=body.db_type,
        host=body.host,
        error_type=test_result.error_type,
    )
    return ConnectionTestResponse(
        status="error",
        error=test_result.error_message,
    )


@router.post("/{connection_id}/test")
async def test_connection(
    connection_id: uuid.UUID,
    conn_mgr: ConnectionManager = Depends(get_connection_manager),
) -> ConnectionTestResponse:
    """Test an existing database connection.

    Decrypts stored credentials, connects to the database, measures
    round-trip latency, counts tables, and updates the connection's
    status and last_tested_at timestamp.
    """
    record = _get_connection_or_404(connection_id)

    # Decrypt stored password
    try:
        password = decrypt_value(record["encrypted_password"])
    except EncryptionError:
        now = _now_iso()
        record["status"] = ConnectionStatus.ERROR.value
        record["updated_at"] = now
        record["last_tested_at"] = now

        logger.warning(
            "connection_test_decrypt_failed",
            connection_id=str(connection_id),
        )
        raise HTTPException(
            status_code=400,
            detail="Cannot decrypt stored credentials. "
            "Please update the connection with new credentials.",
        )

    # Run the connection test with latency measurement
    test_result = conn_mgr.test_connection(
        connection_id=connection_id,
        db_type=record["db_type"],
        host=record["host"],
        port=record["port"],
        database_name=record["database_name"],
        username=record["username"],
        password=password,
        measure_latency=True,
    )

    now = _now_iso()
    record["last_tested_at"] = now
    record["updated_at"] = now

    if test_result.success:
        record["status"] = ConnectionStatus.CONNECTED.value

        logger.info(
            "connection_test_passed",
            connection_id=str(connection_id),
            latency_ms=test_result.latency_ms,
            tables_found=test_result.tables_found,
        )

        return ConnectionTestResponse(
            status="connected",
            latency_ms=test_result.latency_ms,
            tables_found=test_result.tables_found,
        )

    # Connection failed
    record["status"] = ConnectionStatus.ERROR.value

    logger.warning(
        "connection_test_endpoint_failed",
        connection_id=str(connection_id),
        error_type=test_result.error_type,
    )

    return ConnectionTestResponse(
        status="error",
        error=test_result.error_message,
    )


@router.post("/{connection_id}/refresh-schema")
async def refresh_schema(
    connection_id: uuid.UUID,
    conn_mgr: ConnectionManager = Depends(get_connection_manager),
) -> SchemaRefreshResponse:
    """Refresh schema metadata for an existing connection.

    Deletes existing SchemaMetadata and re-introspects the database.
    If the database is unreachable, the existing schema is preserved.
    """
    record = _get_connection_or_404(connection_id)

    # Decrypt stored password
    try:
        password = decrypt_value(record["encrypted_password"])
    except EncryptionError:
        raise HTTPException(
            status_code=400,
            detail="Cannot decrypt stored credentials. "
            "Please update the connection with new credentials.",
        )

    # Ensure the engine is available by testing the connection
    test_result = conn_mgr.test_connection(
        connection_id=connection_id,
        db_type=record["db_type"],
        host=record["host"],
        port=record["port"],
        database_name=record["database_name"],
        username=record["username"],
        password=password,
    )

    if not test_result.success:
        # Preserve existing schema metadata on failure
        logger.warning(
            "schema_refresh_connection_failed",
            connection_id=str(connection_id),
            error_type=test_result.error_type,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Cannot reach database: {test_result.error_message}. "
            "Existing schema has been preserved.",
        )

    # Introspect the schema
    intro_result = conn_mgr.introspect_schema(connection_id)

    if not intro_result.success:
        logger.warning(
            "schema_refresh_introspection_failed",
            connection_id=str(connection_id),
            error_message=intro_result.error_message,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Schema introspection failed: {intro_result.error_message}. "
            "Existing schema has been preserved.",
        )

    # Replace existing schema metadata with fresh introspection
    now = _now_iso()
    tables_found = len({col.table_name for col in intro_result.columns})
    columns_updated = len(intro_result.columns)

    _schema_metadata[connection_id] = [
        {
            "id": uuid.uuid4(),
            "source_id": connection_id,
            "source_type": "connection",
            "table_name": col.table_name,
            "column_name": col.column_name,
            "data_type": col.data_type,
            "is_nullable": col.is_nullable,
            "is_primary_key": col.is_primary_key,
            "foreign_key_ref": col.foreign_key_ref,
        }
        for col in intro_result.columns
    ]

    logger.info(
        "schema_refreshed",
        connection_id=str(connection_id),
        tables_found=tables_found,
        columns_updated=columns_updated,
    )

    return SchemaRefreshResponse(
        source_id=str(connection_id),
        tables_found=tables_found,
        columns_updated=columns_updated,
        refreshed_at=now,
    )
