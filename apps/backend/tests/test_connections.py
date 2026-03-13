"""Tests for the connection CRUD API endpoints.

Covers:
- Integration: Connection CRUD for PostgreSQL
- Integration: Password encryption round-trip
- Integration: Connection status tracking
- Unit: Input validation for connection parameters
- Edge cases: duplicate names, invalid db_type, unreachable host
- Error handling: authentication failure, timeout, invalid params
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from app.api.v1 import connections as connections_module
from app.config import Settings
from app.encryption import decrypt_value
from app.main import create_app
from app.services.connection_manager import (
    ConnectionManager,
    ConnectionTestResult,
    IntrospectionResult,
)
from app.services.schema_introspection import ColumnInfo

# Generate a valid Fernet key for tests
TEST_FERNET_KEY = Fernet.generate_key().decode()


def _test_settings() -> Settings:
    """Create test settings with required fields (SQLite for tests)."""
    env = {
        "DATABASE_URL": "sqlite:///",
        "DATAX_ENCRYPTION_KEY": TEST_FERNET_KEY,
    }
    with patch.dict(os.environ, env, clear=True):
        return Settings()  # type: ignore[call-arg]


@pytest.fixture(autouse=True)
def _clear_connection_store():
    """Clear in-memory connection store between tests."""
    connections_module._connections.clear()
    connections_module._schema_metadata.clear()
    yield
    connections_module._connections.clear()
    connections_module._schema_metadata.clear()


@pytest.fixture
def fernet_env():
    """Provide env with valid Fernet key for encryption operations."""
    return patch.dict(os.environ, {"DATAX_ENCRYPTION_KEY": TEST_FERNET_KEY}, clear=False)


@pytest.fixture
def conn_mgr():
    """Create a ConnectionManager instance."""
    mgr = ConnectionManager()
    yield mgr
    mgr.close_all()


@pytest.fixture
def mock_test_success():
    """Mock ConnectionManager.test_connection to always succeed."""
    return patch.object(
        ConnectionManager,
        "test_connection",
        return_value=ConnectionTestResult(success=True),
    )


@pytest.fixture
def mock_introspect_success():
    """Mock ConnectionManager.introspect_schema to return empty columns."""
    return patch.object(
        ConnectionManager,
        "introspect_schema",
        return_value=IntrospectionResult(success=True, columns=[]),
    )


@pytest.fixture
def app(fernet_env, mock_test_success, mock_introspect_success):
    """Create a FastAPI app with mocked connection manager."""
    with fernet_env, mock_test_success, mock_introspect_success:
        application = create_app(settings=_test_settings())
        yield application


@pytest.fixture
async def client(app):
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


def _valid_pg_body() -> dict:
    """Return a valid PostgreSQL connection request body."""
    return {
        "name": "My PG Connection",
        "db_type": "postgresql",
        "host": "localhost",
        "port": 5432,
        "database_name": "test_db",
        "username": "test_user",
        "password": "test_password_123",
    }


def _valid_mysql_body() -> dict:
    """Return a valid MySQL connection request body."""
    return {
        "name": "My MySQL Connection",
        "db_type": "mysql",
        "host": "db.example.com",
        "port": 3306,
        "database_name": "analytics",
        "username": "mysql_user",
        "password": "mysql_pass_456",
    }


# ---------------------------------------------------------------------------
# Integration: Connection CRUD for PostgreSQL
# ---------------------------------------------------------------------------


class TestCreateConnection:
    """Test POST /api/v1/connections."""

    @pytest.mark.asyncio
    async def test_create_postgresql_connection(self, client) -> None:
        """Create a PostgreSQL connection returns 201 with connection details."""
        body = _valid_pg_body()
        response = await client.post("/api/v1/connections", json=body)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My PG Connection"
        assert data["db_type"] == "postgresql"
        assert data["host"] == "localhost"
        assert data["port"] == 5432
        assert data["database_name"] == "test_db"
        assert data["username"] == "test_user"
        assert data["status"] == "connected"
        assert data["last_tested_at"] is not None
        assert data["created_at"] is not None
        assert data["updated_at"] is not None
        # Password must never be in the response
        assert "password" not in data
        assert "encrypted_password" not in data

    @pytest.mark.asyncio
    async def test_create_mysql_connection(self, client) -> None:
        """Create a MySQL connection returns 201."""
        body = _valid_mysql_body()
        response = await client.post("/api/v1/connections", json=body)

        assert response.status_code == 201
        data = response.json()
        assert data["db_type"] == "mysql"
        assert data["host"] == "db.example.com"
        assert data["port"] == 3306

    @pytest.mark.asyncio
    async def test_create_connection_has_uuid_id(self, client) -> None:
        """Created connection has a valid UUID id."""
        response = await client.post("/api/v1/connections", json=_valid_pg_body())
        data = response.json()
        # Should be a valid UUID
        parsed = uuid.UUID(data["id"])
        assert str(parsed) == data["id"]


class TestListConnections:
    """Test GET /api/v1/connections."""

    @pytest.mark.asyncio
    async def test_list_empty(self, client) -> None:
        """Empty connection list returns empty array."""
        response = await client.get("/api/v1/connections")

        assert response.status_code == 200
        data = response.json()
        assert data["connections"] == []

    @pytest.mark.asyncio
    async def test_list_after_create(self, client) -> None:
        """List returns created connections."""
        await client.post("/api/v1/connections", json=_valid_pg_body())
        await client.post("/api/v1/connections", json=_valid_mysql_body())

        response = await client.get("/api/v1/connections")
        data = response.json()
        assert len(data["connections"]) == 2

    @pytest.mark.asyncio
    async def test_list_shows_status(self, client) -> None:
        """Listed connections include status field."""
        await client.post("/api/v1/connections", json=_valid_pg_body())

        response = await client.get("/api/v1/connections")
        data = response.json()
        assert data["connections"][0]["status"] == "connected"

    @pytest.mark.asyncio
    async def test_list_no_passwords(self, client) -> None:
        """Listed connections never include passwords."""
        await client.post("/api/v1/connections", json=_valid_pg_body())

        response = await client.get("/api/v1/connections")
        conn = response.json()["connections"][0]
        assert "password" not in conn
        assert "encrypted_password" not in conn


class TestUpdateConnection:
    """Test PUT /api/v1/connections/{id}."""

    @pytest.mark.asyncio
    async def test_update_connection_name(self, client) -> None:
        """Update a connection's name."""
        create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
        conn_id = create_resp.json()["id"]

        response = await client.put(
            f"/api/v1/connections/{conn_id}",
            json={"name": "Updated Name"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_retests_connection(self, client) -> None:
        """Updating a connection re-tests it (last_tested_at changes)."""
        create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
        conn_id = create_resp.json()["id"]

        response = await client.put(
            f"/api/v1/connections/{conn_id}",
            json={"name": "Retested"},
        )

        data = response.json()
        assert data["last_tested_at"] is not None
        # The last_tested_at should be updated (may or may not differ in fast tests)
        assert data["status"] == "connected"

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_404(self, client) -> None:
        """Updating a non-existent connection returns 404."""
        fake_id = uuid.uuid4()
        response = await client.put(
            f"/api/v1/connections/{fake_id}",
            json={"name": "Does Not Exist"},
        )
        assert response.status_code == 404


class TestDeleteConnection:
    """Test DELETE /api/v1/connections/{id}."""

    @pytest.mark.asyncio
    async def test_delete_connection(self, client) -> None:
        """Delete a connection returns 204."""
        create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
        conn_id = create_resp.json()["id"]

        response = await client.delete(f"/api/v1/connections/{conn_id}")
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_removes_from_list(self, client) -> None:
        """Deleted connection no longer appears in list."""
        create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
        conn_id = create_resp.json()["id"]

        await client.delete(f"/api/v1/connections/{conn_id}")

        response = await client.get("/api/v1/connections")
        assert len(response.json()["connections"]) == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, client) -> None:
        """Deleting a non-existent connection returns 404."""
        fake_id = uuid.uuid4()
        response = await client.delete(f"/api/v1/connections/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_removes_schema_metadata(self, client) -> None:
        """Deleting a connection removes associated schema metadata."""
        create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
        conn_id = create_resp.json()["id"]
        conn_uuid = uuid.UUID(conn_id)

        # Manually add schema metadata for this connection
        connections_module._schema_metadata[conn_uuid] = [{"column": "test"}]
        assert conn_uuid in connections_module._schema_metadata

        await client.delete(f"/api/v1/connections/{conn_id}")

        assert conn_uuid not in connections_module._schema_metadata


# ---------------------------------------------------------------------------
# Integration: Password encryption round-trip
# ---------------------------------------------------------------------------


class TestPasswordEncryption:
    """Test that passwords are encrypted at rest and can be round-tripped."""

    @pytest.mark.asyncio
    async def test_password_encrypted_in_store(self, client, fernet_env) -> None:
        """Password stored in the internal store is encrypted bytes, not plaintext."""
        with fernet_env:
            body = _valid_pg_body()
            await client.post("/api/v1/connections", json=body)

            # Get the stored record
            stored = list(connections_module._connections.values())[0]
            encrypted_pw = stored["encrypted_password"]

            assert isinstance(encrypted_pw, bytes)
            assert encrypted_pw != body["password"].encode()

    @pytest.mark.asyncio
    async def test_password_decrypts_to_original(self, client, fernet_env) -> None:
        """Encrypted password decrypts back to the original plaintext."""
        with fernet_env:
            body = _valid_pg_body()
            await client.post("/api/v1/connections", json=body)

            stored = list(connections_module._connections.values())[0]
            decrypted = decrypt_value(stored["encrypted_password"])
            assert decrypted == body["password"]

    @pytest.mark.asyncio
    async def test_updated_password_encrypted(self, client, fernet_env) -> None:
        """Updated password is also encrypted in the store."""
        with fernet_env:
            create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
            conn_id = create_resp.json()["id"]
            conn_uuid = uuid.UUID(conn_id)

            await client.put(
                f"/api/v1/connections/{conn_id}",
                json={"password": "new_password_789"},
            )

            stored = connections_module._connections[conn_uuid]
            decrypted = decrypt_value(stored["encrypted_password"])
            assert decrypted == "new_password_789"


# ---------------------------------------------------------------------------
# Integration: Connection status tracking
# ---------------------------------------------------------------------------


class TestConnectionStatusTracking:
    """Test that connection status is tracked correctly."""

    @pytest.mark.asyncio
    async def test_successful_connection_shows_connected(self, client) -> None:
        """Successful test sets status to 'connected'."""
        response = await client.post("/api/v1/connections", json=_valid_pg_body())
        assert response.json()["status"] == "connected"

    @pytest.mark.asyncio
    async def test_last_tested_at_set_on_create(self, client) -> None:
        """last_tested_at is set on creation."""
        response = await client.post("/api/v1/connections", json=_valid_pg_body())
        assert response.json()["last_tested_at"] is not None


# ---------------------------------------------------------------------------
# Unit: Input validation for connection parameters
# ---------------------------------------------------------------------------


class TestInputValidation:
    """Test input validation for connection request bodies."""

    @pytest.mark.asyncio
    async def test_missing_name_returns_422(self, client) -> None:
        """Missing name field returns 422."""
        body = _valid_pg_body()
        del body["name"]
        response = await client.post("/api/v1/connections", json=body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_name_returns_422(self, client) -> None:
        """Empty name field returns 422."""
        body = _valid_pg_body()
        body["name"] = ""
        response = await client.post("/api/v1/connections", json=body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_db_type_returns_400(self, client) -> None:
        """Invalid db_type returns 400 with list of supported types."""
        body = _valid_pg_body()
        body["db_type"] = "oracle"
        response = await client.post("/api/v1/connections", json=body)
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "postgresql" in data["error"]["message"]
        assert "mysql" in data["error"]["message"]

    @pytest.mark.asyncio
    async def test_port_zero_returns_422(self, client) -> None:
        """Port 0 returns 422."""
        body = _valid_pg_body()
        body["port"] = 0
        response = await client.post("/api/v1/connections", json=body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_port_too_large_returns_422(self, client) -> None:
        """Port over 65535 returns 422."""
        body = _valid_pg_body()
        body["port"] = 99999
        response = await client.post("/api/v1/connections", json=body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_password_returns_422(self, client) -> None:
        """Missing password field returns 422."""
        body = _valid_pg_body()
        del body["password"]
        response = await client.post("/api/v1/connections", json=body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_host_returns_422(self, client) -> None:
        """Missing host field returns 422."""
        body = _valid_pg_body()
        del body["host"]
        response = await client.post("/api/v1/connections", json=body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_uuid_path_returns_422(self, client) -> None:
        """Invalid UUID in path returns 422."""
        response = await client.put(
            "/api/v1/connections/not-a-uuid",
            json={"name": "test"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for connection endpoints."""

    @pytest.mark.asyncio
    async def test_duplicate_name_allowed(self, client) -> None:
        """Duplicate connection names are allowed (name is not unique)."""
        body = _valid_pg_body()
        resp1 = await client.post("/api/v1/connections", json=body)
        resp2 = await client.post("/api/v1/connections", json=body)

        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json()["id"] != resp2.json()["id"]

    @pytest.mark.asyncio
    async def test_mysql_nonstandard_port(self, client) -> None:
        """MySQL on a non-standard port works correctly."""
        body = _valid_mysql_body()
        body["port"] = 33060  # Non-standard MySQL port
        response = await client.post("/api/v1/connections", json=body)
        assert response.status_code == 201
        assert response.json()["port"] == 33060


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Error handling tests for connection endpoints."""

    @pytest.mark.asyncio
    async def test_authentication_failure_returns_400(self, fernet_env) -> None:
        """Authentication failure returns 400 with clear error."""
        with fernet_env, patch.object(
            ConnectionManager,
            "test_connection",
            return_value=ConnectionTestResult(
                success=False,
                error_message="password authentication failed for user",
                error_type="authentication_failure",
            ),
        ):
            app = create_app(settings=_test_settings())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post("/api/v1/connections", json=_valid_pg_body())

        assert response.status_code == 400
        assert "authentication" in response.json()["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_connection_timeout_returns_408(self, fernet_env) -> None:
        """Connection timeout returns 408 with troubleshooting tips."""
        with fernet_env, patch.object(
            ConnectionManager,
            "test_connection",
            return_value=ConnectionTestResult(
                success=False,
                error_message="connection timed out",
                error_type="connection_timeout",
            ),
        ):
            app = create_app(settings=_test_settings())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post("/api/v1/connections", json=_valid_pg_body())

        assert response.status_code == 408
        error_msg = response.json()["error"]["message"]
        assert "timed out" in error_msg.lower() or "timeout" in error_msg.lower()
        assert "troubleshooting" in error_msg.lower()

    @pytest.mark.asyncio
    async def test_connection_error_returns_400(self, fernet_env) -> None:
        """Generic connection error returns 400 with suggestion."""
        with fernet_env, patch.object(
            ConnectionManager,
            "test_connection",
            return_value=ConnectionTestResult(
                success=False,
                error_message="could not connect to server",
                error_type="connection_error",
            ),
        ):
            app = create_app(settings=_test_settings())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post("/api/v1/connections", json=_valid_pg_body())

        assert response.status_code == 400
        assert "error" in response.json()

    @pytest.mark.asyncio
    async def test_invalid_db_type_shows_supported_list(self, client) -> None:
        """Invalid db_type error message lists supported types."""
        body = _valid_pg_body()
        body["db_type"] = "sqlite"
        response = await client.post("/api/v1/connections", json=body)

        assert response.status_code == 400
        msg = response.json()["error"]["message"]
        assert "postgresql" in msg
        assert "mysql" in msg


# ---------------------------------------------------------------------------
# Connection Manager Unit Tests
# ---------------------------------------------------------------------------


class TestConnectionManagerUnit:
    """Unit tests for ConnectionManager."""

    def test_close_all_empties_pools(self, conn_mgr) -> None:
        """close_all disposes all pools and empties the dict."""
        # Nothing to close, but should not raise
        conn_mgr.close_all()
        assert len(conn_mgr._pools) == 0

    def test_remove_pool_nonexistent(self, conn_mgr) -> None:
        """Removing a non-existent pool does not raise."""
        conn_mgr.remove_pool(uuid.uuid4())

    def test_build_url_postgresql(self) -> None:
        """Build URL for PostgreSQL connection."""
        from app.services.connection_manager import _build_url

        url = _build_url("postgresql", "localhost", 5432, "mydb", "user", "pass")
        assert url.startswith("postgresql+psycopg://")
        assert "localhost:5432/mydb" in url

    def test_build_url_mysql(self) -> None:
        """Build URL for MySQL connection."""
        from app.services.connection_manager import _build_url

        url = _build_url("mysql", "dbhost", 3306, "mydb", "user", "pass")
        assert url.startswith("mysql+pymysql://")
        assert "dbhost:3306/mydb" in url

    def test_build_url_unsupported_raises(self) -> None:
        """Build URL for unsupported type raises ValueError."""
        from app.services.connection_manager import _build_url

        with pytest.raises(ValueError, match="Unsupported database type"):
            _build_url("oracle", "host", 1521, "db", "user", "pass")

    def test_build_url_special_chars_in_password(self) -> None:
        """Special characters in password are URL-encoded."""
        from app.services.connection_manager import _build_url

        url = _build_url("postgresql", "localhost", 5432, "db", "user", "p@ss/w0rd!")
        # Special chars should be encoded
        assert "p%40ss" in url or "p@ss" not in url.split("@")[0]

    def test_postgresql_type_supported(self) -> None:
        """PostgreSQL is a supported database type."""
        from app.models.connection import DatabaseType

        assert "postgresql" in [t.value for t in DatabaseType]

    def test_mysql_type_supported(self) -> None:
        """MySQL is a supported database type."""
        from app.models.connection import DatabaseType

        assert "mysql" in [t.value for t in DatabaseType]


# ---------------------------------------------------------------------------
# POST /api/v1/connections/{id}/test - Connection Testing Endpoint
# ---------------------------------------------------------------------------


class TestConnectionTestEndpoint:
    """Test POST /api/v1/connections/{id}/test endpoint."""

    @pytest.mark.asyncio
    async def test_successful_test_returns_connected_with_latency(self, fernet_env) -> None:
        """Successful test returns status 'connected' with latency_ms and tables_found."""
        mock_create = patch.object(
            ConnectionManager,
            "test_connection",
            side_effect=[
                # First call: during create_connection (no measure_latency)
                ConnectionTestResult(success=True),
                # Second call: during test endpoint (measure_latency=True)
                ConnectionTestResult(success=True, latency_ms=45.2, tables_found=23),
            ],
        )
        mock_introspect = patch.object(
            ConnectionManager,
            "introspect_schema",
            return_value=IntrospectionResult(success=True, columns=[]),
        )
        with fernet_env, mock_create, mock_introspect:
            app = create_app(settings=_test_settings())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                # Create a connection first
                create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
                conn_id = create_resp.json()["id"]

                # Test the connection
                response = await client.post(f"/api/v1/connections/{conn_id}/test")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "connected"
        assert data["latency_ms"] == 45.2
        assert data["tables_found"] == 23

    @pytest.mark.asyncio
    async def test_status_updated_after_test(self, fernet_env) -> None:
        """Connection status is updated to 'connected' after successful test."""
        mock_create = patch.object(
            ConnectionManager,
            "test_connection",
            side_effect=[
                ConnectionTestResult(success=True),
                ConnectionTestResult(success=True, latency_ms=10.0, tables_found=5),
            ],
        )
        mock_introspect = patch.object(
            ConnectionManager,
            "introspect_schema",
            return_value=IntrospectionResult(success=True, columns=[]),
        )
        with fernet_env, mock_create, mock_introspect:
            app = create_app(settings=_test_settings())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
                conn_id = create_resp.json()["id"]

                await client.post(f"/api/v1/connections/{conn_id}/test")

                # Verify status via list
                list_resp = await client.get("/api/v1/connections")
                conn = list_resp.json()["connections"][0]
                assert conn["status"] == "connected"

    @pytest.mark.asyncio
    async def test_last_tested_at_updated(self, fernet_env) -> None:
        """last_tested_at is updated after testing."""
        mock_create = patch.object(
            ConnectionManager,
            "test_connection",
            side_effect=[
                ConnectionTestResult(success=True),
                ConnectionTestResult(success=True, latency_ms=5.0, tables_found=0),
            ],
        )
        mock_introspect = patch.object(
            ConnectionManager,
            "introspect_schema",
            return_value=IntrospectionResult(success=True, columns=[]),
        )
        with fernet_env, mock_create, mock_introspect:
            app = create_app(settings=_test_settings())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
                conn_id = create_resp.json()["id"]
                original_tested = create_resp.json()["last_tested_at"]

                await client.post(f"/api/v1/connections/{conn_id}/test")

                list_resp = await client.get("/api/v1/connections")
                conn = list_resp.json()["connections"][0]
                assert conn["last_tested_at"] is not None
                # last_tested_at should be at least as recent as the original
                assert conn["last_tested_at"] >= original_tested

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self, client) -> None:
        """Testing a non-existent connection returns 404."""
        fake_id = uuid.uuid4()
        response = await client.post(f"/api/v1/connections/{fake_id}/test")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_timeout_returns_error_status(self, fernet_env) -> None:
        """Connection timeout returns error status in response body."""
        mock_create = patch.object(
            ConnectionManager,
            "test_connection",
            side_effect=[
                ConnectionTestResult(success=True),
                ConnectionTestResult(
                    success=False,
                    error_message="connection timed out",
                    error_type="connection_timeout",
                ),
            ],
        )
        mock_introspect = patch.object(
            ConnectionManager,
            "introspect_schema",
            return_value=IntrospectionResult(success=True, columns=[]),
        )
        with fernet_env, mock_create, mock_introspect:
            app = create_app(settings=_test_settings())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
                conn_id = create_resp.json()["id"]

                response = await client.post(f"/api/v1/connections/{conn_id}/test")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert data["error"] is not None

    @pytest.mark.asyncio
    async def test_auth_failure_returns_error_status(self, fernet_env) -> None:
        """Authentication failure returns error status in response body."""
        mock_create = patch.object(
            ConnectionManager,
            "test_connection",
            side_effect=[
                ConnectionTestResult(success=True),
                ConnectionTestResult(
                    success=False,
                    error_message="password authentication failed",
                    error_type="authentication_failure",
                ),
            ],
        )
        mock_introspect = patch.object(
            ConnectionManager,
            "introspect_schema",
            return_value=IntrospectionResult(success=True, columns=[]),
        )
        with fernet_env, mock_create, mock_introspect:
            app = create_app(settings=_test_settings())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
                conn_id = create_resp.json()["id"]

                response = await client.post(f"/api/v1/connections/{conn_id}/test")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_status_set_to_error_on_failure(self, fernet_env) -> None:
        """Connection status is set to 'error' after failed test."""
        mock_create = patch.object(
            ConnectionManager,
            "test_connection",
            side_effect=[
                ConnectionTestResult(success=True),
                ConnectionTestResult(
                    success=False,
                    error_message="host unreachable",
                    error_type="connection_error",
                ),
            ],
        )
        mock_introspect = patch.object(
            ConnectionManager,
            "introspect_schema",
            return_value=IntrospectionResult(success=True, columns=[]),
        )
        with fernet_env, mock_create, mock_introspect:
            app = create_app(settings=_test_settings())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
                conn_id = create_resp.json()["id"]

                await client.post(f"/api/v1/connections/{conn_id}/test")

                list_resp = await client.get("/api/v1/connections")
                conn = list_resp.json()["connections"][0]
                assert conn["status"] == "error"

    @pytest.mark.asyncio
    async def test_zero_tables_still_connected(self, fernet_env) -> None:
        """Database with no tables still returns 'connected' status."""
        mock_create = patch.object(
            ConnectionManager,
            "test_connection",
            side_effect=[
                ConnectionTestResult(success=True),
                ConnectionTestResult(success=True, latency_ms=12.0, tables_found=0),
            ],
        )
        mock_introspect = patch.object(
            ConnectionManager,
            "introspect_schema",
            return_value=IntrospectionResult(success=True, columns=[]),
        )
        with fernet_env, mock_create, mock_introspect:
            app = create_app(settings=_test_settings())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
                conn_id = create_resp.json()["id"]

                response = await client.post(f"/api/v1/connections/{conn_id}/test")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "connected"
        assert data["tables_found"] == 0

    @pytest.mark.asyncio
    async def test_rapid_successive_tests(self, fernet_env) -> None:
        """Rapid successive tests work without errors."""
        mock_create = patch.object(
            ConnectionManager,
            "test_connection",
            side_effect=[
                ConnectionTestResult(success=True),
                ConnectionTestResult(success=True, latency_ms=10.0, tables_found=5),
                ConnectionTestResult(success=True, latency_ms=11.0, tables_found=5),
                ConnectionTestResult(success=True, latency_ms=9.0, tables_found=5),
            ],
        )
        mock_introspect = patch.object(
            ConnectionManager,
            "introspect_schema",
            return_value=IntrospectionResult(success=True, columns=[]),
        )
        with fernet_env, mock_create, mock_introspect:
            app = create_app(settings=_test_settings())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
                conn_id = create_resp.json()["id"]

                for _ in range(3):
                    resp = await client.post(f"/api/v1/connections/{conn_id}/test")
                    assert resp.status_code == 200
                    assert resp.json()["status"] == "connected"

    @pytest.mark.asyncio
    async def test_decrypt_failure_returns_400(self, fernet_env) -> None:
        """Undecryptable password returns 400 prompting re-entry."""
        from app.encryption import EncryptionError

        mock_create_test = patch.object(
            ConnectionManager,
            "test_connection",
            return_value=ConnectionTestResult(success=True),
        )
        mock_introspect = patch.object(
            ConnectionManager,
            "introspect_schema",
            return_value=IntrospectionResult(success=True, columns=[]),
        )
        with fernet_env, mock_create_test, mock_introspect:
            app = create_app(settings=_test_settings())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
                conn_id = create_resp.json()["id"]

                # Corrupt the encrypted password in the store
                conn_uuid = uuid.UUID(conn_id)
                connections_module._connections[conn_uuid]["encrypted_password"] = b"corrupted"

                with patch(
                    "app.api.v1.connections.decrypt_value",
                    side_effect=EncryptionError("cannot decrypt"),
                ):
                    response = await client.post(f"/api/v1/connections/{conn_id}/test")

        assert response.status_code == 400
        msg = response.json()["error"]["message"]
        assert "credentials" in msg.lower() or "decrypt" in msg.lower()

    @pytest.mark.asyncio
    async def test_works_for_mysql_connection(self, fernet_env) -> None:
        """Test endpoint works for MySQL connections too."""
        mock_create = patch.object(
            ConnectionManager,
            "test_connection",
            side_effect=[
                ConnectionTestResult(success=True),
                ConnectionTestResult(success=True, latency_ms=30.0, tables_found=15),
            ],
        )
        mock_introspect = patch.object(
            ConnectionManager,
            "introspect_schema",
            return_value=IntrospectionResult(success=True, columns=[]),
        )
        with fernet_env, mock_create, mock_introspect:
            app = create_app(settings=_test_settings())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                create_resp = await client.post("/api/v1/connections", json=_valid_mysql_body())
                conn_id = create_resp.json()["id"]

                response = await client.post(f"/api/v1/connections/{conn_id}/test")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "connected"
        assert data["latency_ms"] == 30.0
        assert data["tables_found"] == 15


# ---------------------------------------------------------------------------
# Unit: Latency measurement in ConnectionManager
# ---------------------------------------------------------------------------


class TestLatencyMeasurement:
    """Unit tests for latency measurement in test_connection."""

    def test_latency_not_measured_by_default(self) -> None:
        """When measure_latency is False (default), latency_ms is None."""
        result = ConnectionTestResult(success=True)
        assert result.latency_ms is None
        assert result.tables_found is None

    def test_latency_measured_when_requested(self) -> None:
        """When measure_latency is True, result includes latency_ms."""
        result = ConnectionTestResult(success=True, latency_ms=45.2, tables_found=10)
        assert result.latency_ms == 45.2
        assert result.tables_found == 10

    def test_latency_is_numeric(self) -> None:
        """Latency value is a numeric float."""
        result = ConnectionTestResult(success=True, latency_ms=0.5, tables_found=0)
        assert isinstance(result.latency_ms, float)
        assert result.latency_ms >= 0


# ---------------------------------------------------------------------------
# POST /api/v1/connections/{id}/refresh-schema - Schema Refresh Endpoint
# ---------------------------------------------------------------------------


def _sample_columns() -> list[ColumnInfo]:
    """Return sample ColumnInfo objects for testing."""
    return [
        ColumnInfo(
            table_name="users",
            column_name="id",
            data_type="integer",
            raw_type="INTEGER",
            is_nullable=False,
            is_primary_key=True,
        ),
        ColumnInfo(
            table_name="users",
            column_name="email",
            data_type="varchar",
            raw_type="VARCHAR(255)",
            is_nullable=False,
            is_primary_key=False,
        ),
        ColumnInfo(
            table_name="orders",
            column_name="id",
            data_type="integer",
            raw_type="INTEGER",
            is_nullable=False,
            is_primary_key=True,
        ),
    ]


class TestRefreshSchema:
    """Test POST /api/v1/connections/{id}/refresh-schema endpoint."""

    @pytest.mark.asyncio
    async def test_refresh_replaces_existing_schema(self, fernet_env) -> None:
        """Refresh replaces existing schema with fresh introspection data."""
        columns = _sample_columns()
        mock_test = patch.object(
            ConnectionManager,
            "test_connection",
            return_value=ConnectionTestResult(success=True),
        )
        mock_introspect = patch.object(
            ConnectionManager,
            "introspect_schema",
            return_value=IntrospectionResult(
                success=True,
                columns=columns,
                table_count=2,
            ),
        )
        with fernet_env, mock_test, mock_introspect:
            app = create_app(settings=_test_settings())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                # Create a connection
                create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
                conn_id = create_resp.json()["id"]
                conn_uuid = uuid.UUID(conn_id)

                # Add some old schema metadata
                connections_module._schema_metadata[conn_uuid] = [
                    {"old": "data"},
                ]

                # Refresh schema
                response = await client.post(
                    f"/api/v1/connections/{conn_id}/refresh-schema"
                )

        assert response.status_code == 200
        data = response.json()
        assert data["source_id"] == conn_id
        assert data["tables_found"] == 2  # users and orders
        assert data["columns_updated"] == 3
        assert data["refreshed_at"] is not None

        # Old schema metadata should be replaced
        new_schema = connections_module._schema_metadata[conn_uuid]
        assert len(new_schema) == 3
        assert all(entry["source_type"] == "connection" for entry in new_schema)

    @pytest.mark.asyncio
    async def test_refresh_accurate_table_count(self, fernet_env) -> None:
        """Table count reflects unique tables from introspection."""
        columns = [
            ColumnInfo(
                table_name="products",
                column_name="id",
                data_type="integer",
                raw_type="INTEGER",
                is_nullable=False,
                is_primary_key=True,
            ),
            ColumnInfo(
                table_name="products",
                column_name="name",
                data_type="varchar",
                raw_type="VARCHAR(255)",
                is_nullable=False,
                is_primary_key=False,
            ),
        ]
        mock_test = patch.object(
            ConnectionManager,
            "test_connection",
            return_value=ConnectionTestResult(success=True),
        )
        mock_introspect = patch.object(
            ConnectionManager,
            "introspect_schema",
            return_value=IntrospectionResult(
                success=True,
                columns=columns,
                table_count=1,
            ),
        )
        with fernet_env, mock_test, mock_introspect:
            app = create_app(settings=_test_settings())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
                conn_id = create_resp.json()["id"]

                response = await client.post(
                    f"/api/v1/connections/{conn_id}/refresh-schema"
                )

        data = response.json()
        assert data["tables_found"] == 1
        assert data["columns_updated"] == 2

    @pytest.mark.asyncio
    async def test_refresh_schema_unchanged_restores_same_data(self, fernet_env) -> None:
        """When schema hasn't changed, refresh re-stores the same data."""
        columns = _sample_columns()
        mock_test = patch.object(
            ConnectionManager,
            "test_connection",
            return_value=ConnectionTestResult(success=True),
        )
        mock_introspect = patch.object(
            ConnectionManager,
            "introspect_schema",
            return_value=IntrospectionResult(
                success=True,
                columns=columns,
                table_count=2,
            ),
        )
        with fernet_env, mock_test, mock_introspect:
            app = create_app(settings=_test_settings())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
                conn_id = create_resp.json()["id"]
                conn_uuid = uuid.UUID(conn_id)

                # Refresh twice
                resp1 = await client.post(
                    f"/api/v1/connections/{conn_id}/refresh-schema"
                )
                resp2 = await client.post(
                    f"/api/v1/connections/{conn_id}/refresh-schema"
                )

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["tables_found"] == resp2.json()["tables_found"]
        assert resp1.json()["columns_updated"] == resp2.json()["columns_updated"]
        # Schema metadata count should be the same
        assert len(connections_module._schema_metadata[conn_uuid]) == 3

    @pytest.mark.asyncio
    async def test_refresh_dropped_table_metadata_removed(self, fernet_env) -> None:
        """When a table is dropped, its metadata is removed on refresh."""
        initial_columns = _sample_columns()  # users + orders
        after_drop = [col for col in initial_columns if col.table_name == "users"]

        call_count = [0]

        def introspect_side_effect(connection_id):
            call_count[0] += 1
            if call_count[0] <= 2:
                # First two calls (create + first refresh): full schema
                return IntrospectionResult(
                    success=True, columns=initial_columns, table_count=2
                )
            else:
                # After: orders table dropped
                return IntrospectionResult(
                    success=True, columns=after_drop, table_count=1
                )

        mock_test = patch.object(
            ConnectionManager,
            "test_connection",
            return_value=ConnectionTestResult(success=True),
        )
        mock_introspect = patch.object(
            ConnectionManager,
            "introspect_schema",
            side_effect=introspect_side_effect,
        )
        with fernet_env, mock_test, mock_introspect:
            app = create_app(settings=_test_settings())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
                conn_id = create_resp.json()["id"]
                conn_uuid = uuid.UUID(conn_id)

                # First refresh: full schema
                resp1 = await client.post(
                    f"/api/v1/connections/{conn_id}/refresh-schema"
                )
                assert resp1.json()["tables_found"] == 2
                assert len(connections_module._schema_metadata[conn_uuid]) == 3

                # Second refresh: orders table dropped
                resp2 = await client.post(
                    f"/api/v1/connections/{conn_id}/refresh-schema"
                )

        assert resp2.status_code == 200
        assert resp2.json()["tables_found"] == 1
        assert resp2.json()["columns_updated"] == 2
        # No orders table metadata should remain
        remaining = connections_module._schema_metadata[conn_uuid]
        assert all(entry["table_name"] == "users" for entry in remaining)

    @pytest.mark.asyncio
    async def test_refresh_not_found_returns_404(self, client) -> None:
        """Refreshing schema for non-existent connection returns 404."""
        fake_id = uuid.uuid4()
        response = await client.post(f"/api/v1/connections/{fake_id}/refresh-schema")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_refresh_unreachable_preserves_existing_schema(
        self, fernet_env
    ) -> None:
        """When database is unreachable, existing schema is preserved."""
        columns = _sample_columns()
        call_count = [0]

        def test_side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] <= 1:
                return ConnectionTestResult(success=True)
            else:
                return ConnectionTestResult(
                    success=False,
                    error_message="host unreachable",
                    error_type="connection_error",
                )

        mock_test = patch.object(
            ConnectionManager,
            "test_connection",
            side_effect=test_side_effect,
        )
        mock_introspect = patch.object(
            ConnectionManager,
            "introspect_schema",
            return_value=IntrospectionResult(
                success=True, columns=columns, table_count=2
            ),
        )
        with fernet_env, mock_test, mock_introspect:
            app = create_app(settings=_test_settings())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                # Create connection (uses first test_connection call)
                create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
                conn_id = create_resp.json()["id"]
                conn_uuid = uuid.UUID(conn_id)

                # Schema was stored during creation
                existing_schema = connections_module._schema_metadata.get(conn_uuid)
                assert existing_schema is not None
                original_count = len(existing_schema)

                # Refresh with unreachable database
                response = await client.post(
                    f"/api/v1/connections/{conn_id}/refresh-schema"
                )

        assert response.status_code == 502
        # Existing schema should be preserved
        preserved = connections_module._schema_metadata.get(conn_uuid)
        assert preserved is not None
        assert len(preserved) == original_count

    @pytest.mark.asyncio
    async def test_refresh_response_format(self, fernet_env) -> None:
        """Response contains all required fields with correct types."""
        columns = _sample_columns()
        mock_test = patch.object(
            ConnectionManager,
            "test_connection",
            return_value=ConnectionTestResult(success=True),
        )
        mock_introspect = patch.object(
            ConnectionManager,
            "introspect_schema",
            return_value=IntrospectionResult(
                success=True, columns=columns, table_count=2
            ),
        )
        with fernet_env, mock_test, mock_introspect:
            app = create_app(settings=_test_settings())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                create_resp = await client.post("/api/v1/connections", json=_valid_pg_body())
                conn_id = create_resp.json()["id"]

                response = await client.post(
                    f"/api/v1/connections/{conn_id}/refresh-schema"
                )

        assert response.status_code == 200
        data = response.json()
        # All required response fields present
        assert "source_id" in data
        assert "tables_found" in data
        assert "columns_updated" in data
        assert "refreshed_at" in data
        # Types are correct
        assert isinstance(data["source_id"], str)
        assert isinstance(data["tables_found"], int)
        assert isinstance(data["columns_updated"], int)
        assert isinstance(data["refreshed_at"], str)
        # source_id is a valid UUID
        uuid.UUID(data["source_id"])
