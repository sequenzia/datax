"""Tests for query execution, history, and saved queries API endpoints.

Covers:
- Integration: Execute for DuckDB and SQLAlchemy sources
- Integration: EXPLAIN plan, save/retrieve, history recording
- Unit: Read-only SQL validation, timeout error detection, statement timeout
- Edge cases: non-existent source 404, SQL syntax error, empty results,
  duplicate names allowed, empty history, connection drop
- Error handling: timeout 408, connection error 503, invalid SQL 400
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.main import create_app
from app.models.base import Base
from app.services.query_service import QueryService, is_read_only_sql

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path():
    """Create a temporary file for SQLite database."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d) / "test.db"


@pytest.fixture
def csv_file():
    """Create a temporary CSV file for DuckDB testing."""
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w") as f:
        f.write("id,name,value\n")
        f.write("1,Alice,100\n")
        f.write("2,Bob,200\n")
        f.write("3,Charlie,300\n")
    yield Path(path)
    os.unlink(path)


def _test_settings(db_path: Path) -> Settings:
    """Create test settings with required fields."""
    env = {
        "DATABASE_URL": f"sqlite:///{db_path}",
        "DATAX_ENCRYPTION_KEY": "test-encryption-key",
    }
    with patch.dict(os.environ, env, clear=True):
        return Settings()  # type: ignore[call-arg]


@pytest.fixture
def db_engine(db_path):
    """Create a SQLite engine with foreign key support."""
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    """Create a sessionmaker bound to the test engine."""
    return sessionmaker(bind=db_engine, autocommit=False, autoflush=False)


@pytest.fixture
def app(db_path, db_engine, session_factory, csv_file):
    """Create a FastAPI app with a test SQLite database and DuckDB dataset."""
    application = create_app(settings=_test_settings(db_path))
    application.state.db_engine = db_engine
    application.state.session_factory = session_factory

    # Register a test CSV file in DuckDB so we have a dataset source to query
    duckdb_mgr = application.state.duckdb_manager
    duckdb_mgr.register_file(str(csv_file), "test_table", "csv")

    # Reset query_service if it was cached
    if hasattr(application.state, "query_service"):
        del application.state.query_service

    return application


@pytest.fixture
async def client(app):
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


# A stable source_id to use in tests (does not need to exist in DB for dataset queries)
DATASET_SOURCE_ID = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Unit: Read-only SQL validation
# ---------------------------------------------------------------------------


class TestReadOnlySqlValidation:
    """Unit tests for is_read_only_sql helper."""

    def test_select_is_read_only(self) -> None:
        assert is_read_only_sql("SELECT * FROM t") is True

    def test_select_with_leading_whitespace(self) -> None:
        assert is_read_only_sql("  SELECT 1") is True

    def test_with_cte_is_read_only(self) -> None:
        assert is_read_only_sql("WITH cte AS (SELECT 1) SELECT * FROM cte") is True

    def test_insert_is_not_read_only(self) -> None:
        assert is_read_only_sql("INSERT INTO t VALUES (1)") is False

    def test_update_is_not_read_only(self) -> None:
        assert is_read_only_sql("UPDATE t SET x = 1") is False

    def test_delete_is_not_read_only(self) -> None:
        assert is_read_only_sql("DELETE FROM t") is False

    def test_drop_is_not_read_only(self) -> None:
        assert is_read_only_sql("DROP TABLE t") is False

    def test_alter_is_not_read_only(self) -> None:
        assert is_read_only_sql("ALTER TABLE t ADD COLUMN x INT") is False

    def test_create_is_not_read_only(self) -> None:
        assert is_read_only_sql("CREATE TABLE t (id INT)") is False

    def test_truncate_is_not_read_only(self) -> None:
        assert is_read_only_sql("TRUNCATE TABLE t") is False

    def test_case_insensitive(self) -> None:
        assert is_read_only_sql("insert into t values (1)") is False
        assert is_read_only_sql("DELETE from t") is False

    def test_empty_string_is_not_read_only(self) -> None:
        assert is_read_only_sql("") is False
        assert is_read_only_sql("   ") is False


# ---------------------------------------------------------------------------
# Integration: Execute for DuckDB source
# ---------------------------------------------------------------------------


class TestExecuteDuckDB:
    """Test POST /api/v1/queries/execute for DuckDB (dataset) sources."""

    @pytest.mark.asyncio
    async def test_execute_select_returns_200(self, client) -> None:
        """Execute a SELECT query returns 200 with results."""
        response = await client.post(
            "/api/v1/queries/execute",
            json={
                "sql": "SELECT * FROM test_table",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["columns"] == ["id", "name", "value"]
        assert body["row_count"] == 3
        assert len(body["rows"]) == 3
        assert "execution_time_ms" in body

    @pytest.mark.asyncio
    async def test_execute_with_where_clause(self, client) -> None:
        """Execute query with WHERE returns filtered results."""
        response = await client.post(
            "/api/v1/queries/execute",
            json={
                "sql": "SELECT name FROM test_table WHERE value > 150",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["row_count"] == 2
        names = [row[0] for row in body["rows"]]
        assert "Bob" in names
        assert "Charlie" in names

    @pytest.mark.asyncio
    async def test_execute_with_limit(self, client) -> None:
        """Execute query with LIMIT returns correct number of rows."""
        response = await client.post(
            "/api/v1/queries/execute",
            json={
                "sql": "SELECT * FROM test_table LIMIT 1",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["row_count"] == 1


# ---------------------------------------------------------------------------
# Integration: Execute read-only enforcement
# ---------------------------------------------------------------------------


class TestReadOnlyEnforcement:
    """Test that write operations are rejected."""

    @pytest.mark.asyncio
    async def test_insert_rejected_400(self, client) -> None:
        """INSERT statement returns 400."""
        response = await client.post(
            "/api/v1/queries/execute",
            json={
                "sql": "INSERT INTO test_table VALUES (4, 'Dave', 400)",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )
        assert response.status_code == 400
        assert "READ_ONLY" in response.json()["error"]["code"]

    @pytest.mark.asyncio
    async def test_delete_rejected_400(self, client) -> None:
        """DELETE statement returns 400."""
        response = await client.post(
            "/api/v1/queries/execute",
            json={
                "sql": "DELETE FROM test_table WHERE id = 1",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_drop_rejected_400(self, client) -> None:
        """DROP statement returns 400."""
        response = await client.post(
            "/api/v1/queries/execute",
            json={
                "sql": "DROP TABLE test_table",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Edge case: SQL syntax error returns 400
# ---------------------------------------------------------------------------


class TestSqlSyntaxError:
    """Test that SQL syntax errors return 400."""

    @pytest.mark.asyncio
    async def test_invalid_sql_returns_400(self, client) -> None:
        """Invalid SQL syntax returns 400 with error message."""
        response = await client.post(
            "/api/v1/queries/execute",
            json={
                "sql": "SELECTT * FROMM invalid_syntax!!!",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )
        assert response.status_code == 400
        body = response.json()
        assert "error" in body


# ---------------------------------------------------------------------------
# Edge case: Empty results
# ---------------------------------------------------------------------------


class TestEmptyResults:
    """Test that queries returning no rows work correctly."""

    @pytest.mark.asyncio
    async def test_empty_result_set(self, client) -> None:
        """Query returning zero rows returns 200 with empty rows."""
        response = await client.post(
            "/api/v1/queries/execute",
            json={
                "sql": "SELECT * FROM test_table WHERE value > 99999",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["row_count"] == 0
        assert body["rows"] == []


# ---------------------------------------------------------------------------
# Edge case: Non-existent source 404
# ---------------------------------------------------------------------------


class TestNonExistentSource:
    """Test that querying a non-existent connection source returns 404."""

    @pytest.mark.asyncio
    async def test_nonexistent_connection_returns_404(self, client) -> None:
        """Execute against non-existent connection returns 404."""
        fake_id = str(uuid.uuid4())
        response = await client.post(
            "/api/v1/queries/execute",
            json={
                "sql": "SELECT 1",
                "source_id": fake_id,
                "source_type": "connection",
            },
        )
        assert response.status_code == 404
        body = response.json()
        assert "error" in body


# ---------------------------------------------------------------------------
# Error handling: Invalid source_type returns 400
# ---------------------------------------------------------------------------


class TestInvalidSourceType:
    """Test that invalid source_type returns 400."""

    @pytest.mark.asyncio
    async def test_invalid_source_type_returns_400(self, client) -> None:
        """Invalid source_type returns 400."""
        response = await client.post(
            "/api/v1/queries/execute",
            json={
                "sql": "SELECT 1",
                "source_id": str(uuid.uuid4()),
                "source_type": "invalid",
            },
        )
        assert response.status_code == 400
        assert "INVALID_SOURCE_TYPE" in response.json()["error"]["code"]


# ---------------------------------------------------------------------------
# Integration: EXPLAIN plan
# ---------------------------------------------------------------------------


class TestExplainPlan:
    """Test POST /api/v1/queries/explain."""

    @pytest.mark.asyncio
    async def test_explain_returns_plan(self, client) -> None:
        """EXPLAIN returns a plan string."""
        response = await client.post(
            "/api/v1/queries/explain",
            json={
                "sql": "SELECT * FROM test_table",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "plan" in body
        assert len(body["plan"]) > 0

    @pytest.mark.asyncio
    async def test_explain_invalid_source_type_returns_400(self, client) -> None:
        """EXPLAIN with invalid source_type returns 400."""
        response = await client.post(
            "/api/v1/queries/explain",
            json={
                "sql": "SELECT 1",
                "source_id": str(uuid.uuid4()),
                "source_type": "invalid",
            },
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_explain_nonexistent_connection_returns_404(self, client) -> None:
        """EXPLAIN against non-existent connection returns 404."""
        fake_id = str(uuid.uuid4())
        response = await client.post(
            "/api/v1/queries/explain",
            json={
                "sql": "SELECT 1",
                "source_id": fake_id,
                "source_type": "connection",
            },
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Integration: Save and retrieve queries
# ---------------------------------------------------------------------------


class TestSaveQuery:
    """Test POST /api/v1/queries/save and GET /api/v1/queries/saved."""

    @pytest.mark.asyncio
    async def test_save_query_returns_201(self, client) -> None:
        """Saving a query returns 201 with query details."""
        response = await client.post(
            "/api/v1/queries/save",
            json={
                "name": "Top Products",
                "sql_content": "SELECT * FROM test_table ORDER BY value DESC",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Top Products"
        assert body["sql_content"] == "SELECT * FROM test_table ORDER BY value DESC"
        assert "id" in body
        assert body["created_at"] is not None

    @pytest.mark.asyncio
    async def test_list_saved_queries_returns_saved(self, client) -> None:
        """Listing saved queries returns previously saved queries."""
        # Save two queries
        await client.post(
            "/api/v1/queries/save",
            json={
                "name": "Query 1",
                "sql_content": "SELECT 1",
            },
        )
        await client.post(
            "/api/v1/queries/save",
            json={
                "name": "Query 2",
                "sql_content": "SELECT 2",
            },
        )

        response = await client.get("/api/v1/queries/saved")
        assert response.status_code == 200
        body = response.json()
        assert len(body["queries"]) == 2

    @pytest.mark.asyncio
    async def test_save_without_source_id(self, client) -> None:
        """Saving a query without source_id succeeds."""
        response = await client.post(
            "/api/v1/queries/save",
            json={
                "name": "No Source Query",
                "sql_content": "SELECT 1",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["source_id"] is None
        assert body["source_type"] is None

    @pytest.mark.asyncio
    async def test_duplicate_names_allowed(self, client) -> None:
        """Duplicate query names are allowed."""
        resp1 = await client.post(
            "/api/v1/queries/save",
            json={"name": "Same Name", "sql_content": "SELECT 1"},
        )
        resp2 = await client.post(
            "/api/v1/queries/save",
            json={"name": "Same Name", "sql_content": "SELECT 2"},
        )
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json()["id"] != resp2.json()["id"]


# ---------------------------------------------------------------------------
# Edge case: Empty saved queries list
# ---------------------------------------------------------------------------


class TestEmptySavedQueries:
    """Test listing saved queries when none exist."""

    @pytest.mark.asyncio
    async def test_empty_saved_queries_list(self, client) -> None:
        """Empty saved queries returns empty array."""
        response = await client.get("/api/v1/queries/saved")
        assert response.status_code == 200
        body = response.json()
        assert body["queries"] == []


# ---------------------------------------------------------------------------
# Integration: History recording
# ---------------------------------------------------------------------------


class TestQueryHistory:
    """Test GET /api/v1/queries/history."""

    @pytest.mark.asyncio
    async def test_empty_history(self, client) -> None:
        """Empty history returns empty array."""
        response = await client.get("/api/v1/queries/history")
        assert response.status_code == 200
        body = response.json()
        assert body["history"] == []
        assert body["total"] == 0

    @pytest.mark.asyncio
    async def test_history_records_successful_query(self, client) -> None:
        """Executing a query records it in history."""
        # Execute a query
        await client.post(
            "/api/v1/queries/execute",
            json={
                "sql": "SELECT * FROM test_table",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )

        # Check history
        response = await client.get("/api/v1/queries/history")
        body = response.json()
        assert body["total"] >= 1
        assert body["history"][0]["sql"] == "SELECT * FROM test_table"
        assert body["history"][0]["status"] == "success"
        assert body["history"][0]["row_count"] == 3

    @pytest.mark.asyncio
    async def test_history_records_failed_query(self, client) -> None:
        """Failed query execution is also recorded in history."""
        # Execute an invalid query
        await client.post(
            "/api/v1/queries/execute",
            json={
                "sql": "SELECTT invalid_syntax",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )

        # Check history
        response = await client.get("/api/v1/queries/history")
        body = response.json()
        assert body["total"] >= 1
        # Find the error entry (it should be the first one since history is newest-first)
        error_entries = [e for e in body["history"] if e["status"] == "error"]
        assert len(error_entries) >= 1

    @pytest.mark.asyncio
    async def test_history_pagination(self, client) -> None:
        """History supports pagination with limit and offset."""
        # Execute 3 queries
        for i in range(3):
            await client.post(
                "/api/v1/queries/execute",
                json={
                    "sql": f"SELECT {i + 1}",
                    "source_id": DATASET_SOURCE_ID,
                    "source_type": "dataset",
                },
            )

        # Get first page
        response = await client.get("/api/v1/queries/history?limit=2&offset=0")
        body = response.json()
        assert len(body["history"]) == 2
        assert body["total"] == 3
        assert body["limit"] == 2
        assert body["offset"] == 0

        # Get second page
        response2 = await client.get("/api/v1/queries/history?limit=2&offset=2")
        body2 = response2.json()
        assert len(body2["history"]) == 1
        assert body2["offset"] == 2

    @pytest.mark.asyncio
    async def test_history_has_executed_at(self, client) -> None:
        """History entries include executed_at timestamp."""
        await client.post(
            "/api/v1/queries/execute",
            json={
                "sql": "SELECT 1",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )

        response = await client.get("/api/v1/queries/history")
        body = response.json()
        assert body["history"][0]["executed_at"] is not None
        assert len(body["history"][0]["executed_at"]) > 0


# ---------------------------------------------------------------------------
# Error handling: Timeout 408
# ---------------------------------------------------------------------------


class TestTimeoutHandling:
    """Test that query timeout returns 408."""

    @pytest.mark.asyncio
    async def test_timeout_returns_408(self, app) -> None:
        """Simulated timeout returns 408."""
        import duckdb

        # Patch DuckDB execute_query to raise a timeout-like error
        with patch.object(
            app.state.duckdb_manager,
            "execute_query",
            side_effect=duckdb.Error("query timeout exceeded"),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    "/api/v1/queries/execute",
                    json={
                        "sql": "SELECT * FROM test_table",
                        "source_id": DATASET_SOURCE_ID,
                        "source_type": "dataset",
                    },
                )
            assert response.status_code == 408
            assert "QUERY_TIMEOUT" in response.json()["error"]["code"]


# ---------------------------------------------------------------------------
# Error handling: Connection error 503
# ---------------------------------------------------------------------------


class TestConnectionError:
    """Test that connection errors return 503."""

    @pytest.mark.asyncio
    async def test_connection_error_returns_503(self, app) -> None:
        """Connection-level error for external DB returns 503."""
        from sqlalchemy.exc import OperationalError

        conn_id = uuid.uuid4()
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.side_effect = OperationalError(
            "database connection error", None, None
        )
        mock_engine.connect.return_value = mock_conn

        # Inject the mock engine into the connection manager's pools and db_types
        app.state.connection_manager._pools[conn_id] = mock_engine
        app.state.connection_manager._db_types[conn_id] = "postgresql"

        # Reset query_service to pick up the connection manager
        if hasattr(app.state, "query_service"):
            del app.state.query_service

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/queries/execute",
                json={
                    "sql": "SELECT 1",
                    "source_id": str(conn_id),
                    "source_type": "connection",
                },
            )
        assert response.status_code == 503
        assert "CONNECTION_ERROR" in response.json()["error"]["code"]


# ---------------------------------------------------------------------------
# Validation: Empty SQL rejected
# ---------------------------------------------------------------------------


class TestEmptySqlValidation:
    """Test that empty SQL is rejected."""

    @pytest.mark.asyncio
    async def test_empty_sql_returns_422(self, client) -> None:
        """Empty SQL string returns 422 validation error."""
        response = await client.post(
            "/api/v1/queries/execute",
            json={
                "sql": "",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Unit: Timeout error detection
# ---------------------------------------------------------------------------


class TestIsTimeoutError:
    """Unit tests for QueryService._is_timeout_error."""

    def test_timeout_keyword(self) -> None:
        assert QueryService._is_timeout_error("query timeout exceeded") is True

    def test_timed_out_keyword(self) -> None:
        assert QueryService._is_timeout_error("connection timed out") is True

    def test_canceling_statement(self) -> None:
        assert QueryService._is_timeout_error(
            "canceling statement due to statement timeout"
        ) is True

    def test_statement_timeout_keyword(self) -> None:
        assert QueryService._is_timeout_error(
            "ERROR: statement_timeout reached"
        ) is True

    def test_max_execution_time_keyword(self) -> None:
        assert QueryService._is_timeout_error(
            "Query exceeded max_execution_time limit"
        ) is True

    def test_regular_error_not_timeout(self) -> None:
        assert QueryService._is_timeout_error("syntax error at position 5") is False

    def test_case_insensitive(self) -> None:
        assert QueryService._is_timeout_error("QUERY TIMEOUT EXCEEDED") is True


# ---------------------------------------------------------------------------
# Unit: Statement timeout setting
# ---------------------------------------------------------------------------


class TestSetStatementTimeout:
    """Unit tests for QueryService._set_statement_timeout."""

    def test_postgresql_sets_local_statement_timeout(self) -> None:
        """PostgreSQL uses SET LOCAL statement_timeout."""
        mock_conn = MagicMock()
        QueryService._set_statement_timeout(mock_conn, "postgresql", 30000)
        mock_conn.execute.assert_called_once()
        # Extract the TextClause's text attribute
        text_clause = mock_conn.execute.call_args[0][0]
        assert "statement_timeout" in text_clause.text
        assert "30000" in text_clause.text

    def test_mysql_sets_max_execution_time(self) -> None:
        """MySQL uses SET SESSION max_execution_time."""
        mock_conn = MagicMock()
        QueryService._set_statement_timeout(mock_conn, "mysql", 30000)
        mock_conn.execute.assert_called_once()
        text_clause = mock_conn.execute.call_args[0][0]
        assert "max_execution_time" in text_clause.text
        assert "30000" in text_clause.text

    def test_unknown_db_type_does_nothing(self) -> None:
        """Unknown db_type does not execute any timeout statement."""
        mock_conn = MagicMock()
        QueryService._set_statement_timeout(mock_conn, "sqlite", 30000)
        mock_conn.execute.assert_not_called()

    def test_none_db_type_does_nothing(self) -> None:
        """None db_type does not execute any timeout statement."""
        mock_conn = MagicMock()
        QueryService._set_statement_timeout(mock_conn, None, 30000)
        mock_conn.execute.assert_not_called()

    def test_exception_is_suppressed(self) -> None:
        """Timeout set failure is logged but does not raise."""
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("permission denied")
        # Should not raise
        QueryService._set_statement_timeout(mock_conn, "postgresql", 30000)


# ---------------------------------------------------------------------------
# Integration: Connection drop detection
# ---------------------------------------------------------------------------


class TestConnectionDropDetected:
    """Test that connection drops are reported as 503."""

    @pytest.mark.asyncio
    async def test_disconnection_error_returns_503(self, app) -> None:
        """DisconnectionError during query execution returns 503."""
        from sqlalchemy.exc import DisconnectionError

        conn_id = uuid.uuid4()
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.side_effect = DisconnectionError(
            "server closed the connection unexpectedly"
        )
        mock_engine.connect.return_value = mock_conn

        app.state.connection_manager._pools[conn_id] = mock_engine
        app.state.connection_manager._db_types[conn_id] = "postgresql"

        if hasattr(app.state, "query_service"):
            del app.state.query_service

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/queries/execute",
                json={
                    "sql": "SELECT 1",
                    "source_id": str(conn_id),
                    "source_type": "connection",
                },
            )
        assert response.status_code == 503
        body = response.json()
        assert "CONNECTION_ERROR" in body["error"]["code"]
        assert "connection was lost" in body["error"]["message"].lower()


# ---------------------------------------------------------------------------
# Integration: Connection query timeout via mock
# ---------------------------------------------------------------------------


class TestConnectionQueryTimeout:
    """Test that connection query timeout (canceling statement) returns 408."""

    @pytest.mark.asyncio
    async def test_statement_timeout_returns_408(self, app) -> None:
        """OperationalError with 'canceling statement' message returns 408."""
        from sqlalchemy.exc import OperationalError

        conn_id = uuid.uuid4()
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        call_count = 0

        def execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # First call is the SET statement_timeout, let it pass
            if call_count == 1:
                return MagicMock()
            # Second call is the user query, simulate timeout
            raise OperationalError(
                "canceling statement due to statement timeout", None, None
            )

        mock_conn.execute.side_effect = execute_side_effect
        mock_engine.connect.return_value = mock_conn

        app.state.connection_manager._pools[conn_id] = mock_engine
        app.state.connection_manager._db_types[conn_id] = "postgresql"

        if hasattr(app.state, "query_service"):
            del app.state.query_service

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/queries/execute",
                json={
                    "sql": "SELECT * FROM huge_table",
                    "source_id": str(conn_id),
                    "source_type": "connection",
                },
            )
        assert response.status_code == 408
        assert "QUERY_TIMEOUT" in response.json()["error"]["code"]


# ---------------------------------------------------------------------------
# Unit: Connection manager get_engine / get_db_type
# ---------------------------------------------------------------------------


class TestConnectionManagerAccessors:
    """Test ConnectionManager.get_engine and get_db_type."""

    def test_get_engine_returns_none_for_unknown_id(self) -> None:
        from app.services.connection_manager import ConnectionManager

        mgr = ConnectionManager()
        assert mgr.get_engine(uuid.uuid4()) is None

    def test_get_db_type_returns_none_for_unknown_id(self) -> None:
        from app.services.connection_manager import ConnectionManager

        mgr = ConnectionManager()
        assert mgr.get_db_type(uuid.uuid4()) is None

    def test_get_engine_returns_injected_engine(self) -> None:
        from app.services.connection_manager import ConnectionManager

        mgr = ConnectionManager()
        conn_id = uuid.uuid4()
        mock_engine = MagicMock()
        mgr._pools[conn_id] = mock_engine
        assert mgr.get_engine(conn_id) is mock_engine

    def test_get_db_type_returns_injected_type(self) -> None:
        from app.services.connection_manager import ConnectionManager

        mgr = ConnectionManager()
        conn_id = uuid.uuid4()
        mgr._db_types[conn_id] = "postgresql"
        assert mgr.get_db_type(conn_id) == "postgresql"

    def test_close_all_clears_db_types(self) -> None:
        from app.services.connection_manager import ConnectionManager

        mgr = ConnectionManager()
        conn_id = uuid.uuid4()
        mgr._pools[conn_id] = MagicMock()
        mgr._db_types[conn_id] = "mysql"
        mgr.close_all()
        assert mgr.get_engine(conn_id) is None
        assert mgr.get_db_type(conn_id) is None

    def test_remove_pool_clears_db_type(self) -> None:
        from app.services.connection_manager import ConnectionManager

        mgr = ConnectionManager()
        conn_id = uuid.uuid4()
        mgr._pools[conn_id] = MagicMock()
        mgr._db_types[conn_id] = "postgresql"
        mgr.remove_pool(conn_id)
        assert mgr.get_engine(conn_id) is None
        assert mgr.get_db_type(conn_id) is None


# ---------------------------------------------------------------------------
# Integration: Standardized result format for connections
# ---------------------------------------------------------------------------


class TestStandardizedResultFormat:
    """Test that connection query results follow the standard format."""

    @pytest.mark.asyncio
    async def test_connection_result_has_standard_fields(self, app) -> None:
        """Successful connection query returns columns, rows, row_count, execution_time_ms."""
        conn_id = uuid.uuid4()
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        mock_result = MagicMock()
        mock_result.keys.return_value = ["id", "name"]
        mock_result.fetchall.return_value = [(1, "Alice"), (2, "Bob")]

        call_count = 0

        def execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock()  # timeout SET
            return mock_result

        mock_conn.execute.side_effect = execute_side_effect
        mock_engine.connect.return_value = mock_conn

        app.state.connection_manager._pools[conn_id] = mock_engine
        app.state.connection_manager._db_types[conn_id] = "postgresql"

        if hasattr(app.state, "query_service"):
            del app.state.query_service

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/queries/execute",
                json={
                    "sql": "SELECT id, name FROM users",
                    "source_id": str(conn_id),
                    "source_type": "connection",
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["columns"] == ["id", "name"]
        assert body["row_count"] == 2
        assert len(body["rows"]) == 2
        assert "execution_time_ms" in body
        assert isinstance(body["execution_time_ms"], int)


# ---------------------------------------------------------------------------
# Integration: Write ops blocked for connection source type
# ---------------------------------------------------------------------------


class TestWriteOpsBlockedForConnection:
    """Test that write operations are blocked for connection source type."""

    @pytest.mark.asyncio
    async def test_insert_on_connection_rejected(self, client) -> None:
        """INSERT against a connection source returns 400."""
        conn_id = str(uuid.uuid4())
        response = await client.post(
            "/api/v1/queries/execute",
            json={
                "sql": "INSERT INTO users VALUES (1, 'test')",
                "source_id": conn_id,
                "source_type": "connection",
            },
        )
        assert response.status_code == 400
        assert "READ_ONLY" in response.json()["error"]["code"]

    @pytest.mark.asyncio
    async def test_update_on_connection_rejected(self, client) -> None:
        """UPDATE against a connection source returns 400."""
        conn_id = str(uuid.uuid4())
        response = await client.post(
            "/api/v1/queries/execute",
            json={
                "sql": "UPDATE users SET name = 'test'",
                "source_id": conn_id,
                "source_type": "connection",
            },
        )
        assert response.status_code == 400
        assert "READ_ONLY" in response.json()["error"]["code"]

    @pytest.mark.asyncio
    async def test_truncate_on_connection_rejected(self, client) -> None:
        """TRUNCATE against a connection source returns 400."""
        conn_id = str(uuid.uuid4())
        response = await client.post(
            "/api/v1/queries/execute",
            json={
                "sql": "TRUNCATE TABLE users",
                "source_id": conn_id,
                "source_type": "connection",
            },
        )
        assert response.status_code == 400
        assert "READ_ONLY" in response.json()["error"]["code"]

    @pytest.mark.asyncio
    async def test_alter_on_connection_rejected(self, client) -> None:
        """ALTER against a connection source returns 400."""
        conn_id = str(uuid.uuid4())
        response = await client.post(
            "/api/v1/queries/execute",
            json={
                "sql": "ALTER TABLE users ADD COLUMN age INT",
                "source_id": conn_id,
                "source_type": "connection",
            },
        )
        assert response.status_code == 400
        assert "READ_ONLY" in response.json()["error"]["code"]


# ---------------------------------------------------------------------------
# Integration: SQL syntax error passthrough for connection
# ---------------------------------------------------------------------------


class TestConnectionSqlSyntaxError:
    """Test that SQL syntax errors from connections are passed through."""

    @pytest.mark.asyncio
    async def test_sql_syntax_error_passthrough(self, app) -> None:
        """SQL syntax error from a connection returns 400 with error details."""
        conn_id = uuid.uuid4()
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        call_count = 0

        def execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock()  # timeout SET
            raise Exception("syntax error at or near 'FROMM'")

        mock_conn.execute.side_effect = execute_side_effect
        mock_engine.connect.return_value = mock_conn

        app.state.connection_manager._pools[conn_id] = mock_engine
        app.state.connection_manager._db_types[conn_id] = "postgresql"

        if hasattr(app.state, "query_service"):
            del app.state.query_service

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/queries/execute",
                json={
                    "sql": "SELECT * FROMM users",
                    "source_id": str(conn_id),
                    "source_type": "connection",
                },
            )
        assert response.status_code == 400
        body = response.json()
        assert "error" in body
        assert "syntax error" in body["error"]["message"].lower()
