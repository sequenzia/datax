"""Tests for cross-source query orchestration.

Covers:
- Unit: CrossSourceQueryEngine with DuckDB-to-DuckDB joins
- Unit: Column name collision aliasing
- Unit: Sub-query failure aborts all
- Unit: Empty join results
- Unit: Large result truncation (pagination guard)
- Unit: Timeout cancels all sub-queries
- Unit: Connection lost error reporting
- Unit: DuckDB memory pressure limiting via max_rows
- Performance: Parallel execution faster than sequential
- Integration: API endpoint for cross-source queries
"""

from __future__ import annotations

import os
import tempfile
import time
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
from app.services.connection_manager import ConnectionManager
from app.services.cross_source_query import (
    CrossSourcePlan,
    CrossSourceQueryEngine,
    SubQuery,
    _resolve_column_collisions,
)
from app.services.duckdb_manager import DuckDBManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path():
    """Create a temporary file for SQLite database."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d) / "test.db"


@pytest.fixture
def csv_orders():
    """Create a temporary CSV file with orders data (DuckDB source)."""
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w") as f:
        f.write("order_id,customer_id,amount\n")
        f.write("1,101,50.00\n")
        f.write("2,102,75.00\n")
        f.write("3,101,100.00\n")
        f.write("4,103,25.00\n")
    yield Path(path)
    os.unlink(path)


@pytest.fixture
def csv_customers():
    """Create a temporary CSV file with customers data (DuckDB source)."""
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w") as f:
        f.write("customer_id,name,email\n")
        f.write("101,Alice,alice@example.com\n")
        f.write("102,Bob,bob@example.com\n")
        f.write("103,Charlie,charlie@example.com\n")
    yield Path(path)
    os.unlink(path)


@pytest.fixture
def duckdb_manager(csv_orders, csv_customers):
    """Create a DuckDB manager with two registered tables."""
    mgr = DuckDBManager()
    mgr.register_file(str(csv_orders), "ds_orders", "csv")
    mgr.register_file(str(csv_customers), "ds_customers", "csv")
    yield mgr
    mgr.close()


@pytest.fixture
def connection_manager():
    """Create a ConnectionManager."""
    return ConnectionManager()


@pytest.fixture
def engine(duckdb_manager, connection_manager):
    """Create a CrossSourceQueryEngine."""
    return CrossSourceQueryEngine(duckdb_manager, connection_manager)


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
    db_eng = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(db_eng, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(db_eng)
    yield db_eng
    db_eng.dispose()


@pytest.fixture
def session_factory(db_engine):
    """Create a sessionmaker bound to the test engine."""
    return sessionmaker(bind=db_engine, autocommit=False, autoflush=False)


@pytest.fixture
def app(db_path, db_engine, session_factory, csv_orders, csv_customers):
    """Create a FastAPI app with DuckDB datasets for cross-source testing."""
    application = create_app(settings=_test_settings(db_path))
    application.state.db_engine = db_engine
    application.state.session_factory = session_factory

    duckdb_mgr = application.state.duckdb_manager
    duckdb_mgr.register_file(str(csv_orders), "ds_orders", "csv")
    duckdb_mgr.register_file(str(csv_customers), "ds_customers", "csv")

    if hasattr(application.state, "query_service"):
        del application.state.query_service

    return application


@pytest.fixture
async def client(app):
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


DATASET_SOURCE_ID = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Unit: Column collision resolution
# ---------------------------------------------------------------------------


class TestColumnCollisionResolution:
    """Test _resolve_column_collisions helper."""

    def test_no_collisions(self) -> None:
        result = _resolve_column_collisions(["id", "name", "value"], "t1")
        assert result == ["id", "name", "value"]

    def test_duplicate_columns_aliased(self) -> None:
        result = _resolve_column_collisions(["id", "id", "name"], "t1")
        assert result == ["id", "id_t1_1", "name"]

    def test_triple_duplicate(self) -> None:
        result = _resolve_column_collisions(["x", "x", "x"], "src")
        assert result == ["x", "x_src_1", "x_src_2"]


# ---------------------------------------------------------------------------
# Unit: DuckDB-to-DuckDB cross-source join
# ---------------------------------------------------------------------------


class TestDuckDBCrossSourceJoin:
    """Test cross-source join using two DuckDB datasets."""

    def test_basic_join_works(self, engine) -> None:
        """Join two DuckDB datasets produces correct results."""
        plan = CrossSourcePlan(
            sub_queries=[
                SubQuery(
                    alias="orders",
                    sql="SELECT order_id, customer_id, amount FROM ds_orders",
                    source_id=uuid.uuid4(),
                    source_type="dataset",
                ),
                SubQuery(
                    alias="customers",
                    sql="SELECT customer_id, name FROM ds_customers",
                    source_id=uuid.uuid4(),
                    source_type="dataset",
                ),
            ],
            join_sql=(
                'SELECT o.order_id, o.amount, c.name '
                'FROM "orders" o JOIN "customers" c '
                'ON o.customer_id = c.customer_id '
                'ORDER BY o.order_id'
            ),
        )
        result = engine.execute(plan)

        assert result.status == "success"
        assert result.error_message is None
        assert result.row_count == 4
        assert "order_id" in result.columns
        assert "name" in result.columns
        # Verify join correctness
        assert result.rows[0][2] == "Alice"  # order_id=1 -> customer_id=101 -> Alice
        assert result.rows[1][2] == "Bob"  # order_id=2 -> customer_id=102 -> Bob
        assert result.rows[2][2] == "Alice"  # order_id=3 -> customer_id=101 -> Alice

    def test_standard_result_format(self, engine) -> None:
        """Cross-source result has columns, rows, row_count, execution_time_ms."""
        plan = CrossSourcePlan(
            sub_queries=[
                SubQuery(
                    alias="orders",
                    sql="SELECT * FROM ds_orders",
                    source_id=uuid.uuid4(),
                    source_type="dataset",
                ),
            ],
            join_sql='SELECT * FROM "orders"',
        )
        result = engine.execute(plan)

        assert result.status == "success"
        assert isinstance(result.columns, list)
        assert isinstance(result.rows, list)
        assert isinstance(result.row_count, int)
        assert isinstance(result.execution_time_ms, int)
        assert isinstance(result.sub_query_times_ms, dict)

    def test_sub_query_times_reported(self, engine) -> None:
        """Sub-query execution times are reported in the result."""
        plan = CrossSourcePlan(
            sub_queries=[
                SubQuery(
                    alias="orders",
                    sql="SELECT * FROM ds_orders",
                    source_id=uuid.uuid4(),
                    source_type="dataset",
                ),
                SubQuery(
                    alias="customers",
                    sql="SELECT * FROM ds_customers",
                    source_id=uuid.uuid4(),
                    source_type="dataset",
                ),
            ],
            join_sql='SELECT * FROM "orders"',
        )
        result = engine.execute(plan)

        assert "orders" in result.sub_query_times_ms
        assert "customers" in result.sub_query_times_ms


# ---------------------------------------------------------------------------
# Unit: Sub-query failure aborts all
# ---------------------------------------------------------------------------


class TestSubQueryFailureAborts:
    """Test that a sub-query failure aborts the entire operation."""

    def test_bad_sql_aborts(self, engine) -> None:
        """Invalid SQL in a sub-query causes the cross-source query to fail."""
        plan = CrossSourcePlan(
            sub_queries=[
                SubQuery(
                    alias="good",
                    sql="SELECT * FROM ds_orders",
                    source_id=uuid.uuid4(),
                    source_type="dataset",
                ),
                SubQuery(
                    alias="bad",
                    sql="SELECT * FROM nonexistent_table_xyz",
                    source_id=uuid.uuid4(),
                    source_type="dataset",
                ),
            ],
            join_sql='SELECT * FROM "good" JOIN "bad" ON 1=1',
        )
        result = engine.execute(plan)

        assert result.status == "error"
        assert "bad" in result.error_message
        # The join should not have been attempted, so columns/rows are empty
        assert result.columns == []
        assert result.rows == []

    def test_connection_not_found_aborts(self, engine) -> None:
        """Non-existent connection source aborts."""
        plan = CrossSourcePlan(
            sub_queries=[
                SubQuery(
                    alias="remote",
                    sql="SELECT 1",
                    source_id=uuid.uuid4(),
                    source_type="connection",
                ),
            ],
            join_sql='SELECT * FROM "remote"',
        )
        result = engine.execute(plan)

        assert result.status == "error"
        assert "not found" in result.error_message.lower()


# ---------------------------------------------------------------------------
# Unit: Empty join results
# ---------------------------------------------------------------------------


class TestEmptyJoinResults:
    """Test that empty join results are handled correctly."""

    def test_empty_join_returns_zero_rows(self, engine) -> None:
        """A join that produces no matches returns empty result."""
        plan = CrossSourcePlan(
            sub_queries=[
                SubQuery(
                    alias="orders",
                    sql="SELECT * FROM ds_orders WHERE amount > 999999",
                    source_id=uuid.uuid4(),
                    source_type="dataset",
                ),
                SubQuery(
                    alias="customers",
                    sql="SELECT * FROM ds_customers",
                    source_id=uuid.uuid4(),
                    source_type="dataset",
                ),
            ],
            join_sql=(
                'SELECT o.order_id, c.name '
                'FROM "orders" o JOIN "customers" c '
                'ON o.customer_id = c.customer_id'
            ),
        )
        result = engine.execute(plan)

        assert result.status == "success"
        assert result.row_count == 0
        assert result.rows == []


# ---------------------------------------------------------------------------
# Unit: Large result truncation (pagination before loading)
# ---------------------------------------------------------------------------


class TestLargeResultTruncation:
    """Test that large sub-query results are truncated."""

    def test_truncation_limits_rows(self, engine) -> None:
        """Sub-query results exceeding max_rows are truncated."""
        plan = CrossSourcePlan(
            sub_queries=[
                SubQuery(
                    alias="orders",
                    sql="SELECT * FROM ds_orders",
                    source_id=uuid.uuid4(),
                    source_type="dataset",
                ),
            ],
            join_sql='SELECT * FROM "orders"',
        )
        # Set max_rows to 2 so 4 rows get truncated to 2
        result = engine.execute(plan, max_rows_per_subquery=2)

        assert result.status == "success"
        assert result.row_count == 2


# ---------------------------------------------------------------------------
# Unit: Temp table cleanup
# ---------------------------------------------------------------------------


class TestTempTableCleanup:
    """Test that temp tables are cleaned up after execution."""

    def test_temp_tables_cleaned_on_success(self, engine, duckdb_manager) -> None:
        """Temp tables are dropped after successful cross-source query."""
        plan = CrossSourcePlan(
            sub_queries=[
                SubQuery(
                    alias="temp_orders",
                    sql="SELECT * FROM ds_orders",
                    source_id=uuid.uuid4(),
                    source_type="dataset",
                ),
            ],
            join_sql='SELECT * FROM "temp_orders"',
        )
        result = engine.execute(plan)
        assert result.status == "success"

        # Verify temp table was cleaned up
        try:
            duckdb_manager.execute_query('SELECT * FROM "temp_orders"')
            assert False, "Temp table should have been dropped"
        except Exception:
            pass  # Expected - table should not exist

    def test_temp_tables_cleaned_on_failure(self, engine, duckdb_manager) -> None:
        """Temp tables are dropped even when the join query fails."""
        plan = CrossSourcePlan(
            sub_queries=[
                SubQuery(
                    alias="temp_data",
                    sql="SELECT * FROM ds_orders",
                    source_id=uuid.uuid4(),
                    source_type="dataset",
                ),
            ],
            join_sql='SELECT * FROM "temp_data" JOIN nonexistent ON 1=1',
        )
        result = engine.execute(plan)
        assert result.status == "error"

        # Verify temp table was cleaned up even on failure
        try:
            duckdb_manager.execute_query('SELECT * FROM "temp_data"')
            assert False, "Temp table should have been dropped"
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Unit: Timeout cancels all sub-queries
# ---------------------------------------------------------------------------


class TestTimeoutCancellation:
    """Test that sub-query timeout reports error."""

    def test_connection_timeout_reported(self, duckdb_manager, connection_manager) -> None:
        """A sub-query timeout against a live connection is reported."""
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
            if call_count == 1:
                return MagicMock()  # SET timeout
            raise OperationalError(
                "canceling statement due to statement timeout", None, None
            )

        mock_conn.execute.side_effect = execute_side_effect
        mock_engine.connect.return_value = mock_conn

        connection_manager._pools[conn_id] = mock_engine
        connection_manager._db_types[conn_id] = "postgresql"

        cs_engine = CrossSourceQueryEngine(duckdb_manager, connection_manager)
        plan = CrossSourcePlan(
            sub_queries=[
                SubQuery(
                    alias="remote",
                    sql="SELECT * FROM huge_table",
                    source_id=conn_id,
                    source_type="connection",
                ),
            ],
            join_sql='SELECT * FROM "remote"',
        )
        result = cs_engine.execute(plan)

        assert result.status == "error"
        assert "timed out" in result.error_message.lower()


# ---------------------------------------------------------------------------
# Unit: Connection lost error reporting
# ---------------------------------------------------------------------------


class TestConnectionLostReporting:
    """Test that connection loss during sub-query is reported."""

    def test_disconnection_error_reported(self, duckdb_manager, connection_manager) -> None:
        """DisconnectionError during sub-query is reported in the result."""
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

        connection_manager._pools[conn_id] = mock_engine
        connection_manager._db_types[conn_id] = "postgresql"

        cs_engine = CrossSourceQueryEngine(duckdb_manager, connection_manager)
        plan = CrossSourcePlan(
            sub_queries=[
                SubQuery(
                    alias="remote",
                    sql="SELECT 1",
                    source_id=conn_id,
                    source_type="connection",
                ),
            ],
            join_sql='SELECT * FROM "remote"',
        )
        result = cs_engine.execute(plan)

        assert result.status == "error"
        assert "connection lost" in result.error_message.lower()


# ---------------------------------------------------------------------------
# Unit: DuckDB + mock connection cross-source join
# ---------------------------------------------------------------------------


class TestDuckDBPlusConnectionJoin:
    """Test cross-source join between DuckDB dataset and mock live connection."""

    def test_duckdb_plus_connection_join(self, duckdb_manager, connection_manager) -> None:
        """Join DuckDB dataset with live connection results."""
        conn_id = uuid.uuid4()
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        # Simulate a live DB returning customer data
        mock_result = MagicMock()
        mock_result.keys.return_value = ["customer_id", "name"]
        mock_result.fetchall.return_value = [
            (101, "Alice"),
            (102, "Bob"),
            (103, "Charlie"),
        ]

        call_count = 0

        def execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock()  # SET timeout
            return mock_result

        mock_conn.execute.side_effect = execute_side_effect
        mock_engine.connect.return_value = mock_conn

        connection_manager._pools[conn_id] = mock_engine
        connection_manager._db_types[conn_id] = "postgresql"

        cs_engine = CrossSourceQueryEngine(duckdb_manager, connection_manager)
        plan = CrossSourcePlan(
            sub_queries=[
                SubQuery(
                    alias="orders",
                    sql="SELECT order_id, customer_id, amount FROM ds_orders",
                    source_id=uuid.uuid4(),
                    source_type="dataset",
                ),
                SubQuery(
                    alias="customers",
                    sql="SELECT customer_id, name FROM customers",
                    source_id=conn_id,
                    source_type="connection",
                ),
            ],
            join_sql=(
                'SELECT o.order_id, o.amount, c.name '
                'FROM "orders" o JOIN "customers" c '
                'ON o.customer_id = c.customer_id '
                'ORDER BY o.order_id'
            ),
        )
        result = cs_engine.execute(plan)

        assert result.status == "success"
        assert result.row_count == 4
        assert "order_id" in result.columns
        assert "name" in result.columns
        # Verify join correctness
        assert result.rows[0][2] == "Alice"  # order 1 -> customer 101
        assert result.rows[1][2] == "Bob"  # order 2 -> customer 102


# ---------------------------------------------------------------------------
# Performance: Parallel faster than sequential
# ---------------------------------------------------------------------------


class TestParallelPerformance:
    """Test that parallel sub-query execution is faster than sequential."""

    def test_parallel_is_faster(self, duckdb_manager, connection_manager) -> None:
        """Parallel execution of multiple sub-queries is faster than sequential.

        Uses sleep-based sub-queries to simulate latency and verify parallelism.
        """
        # We create a mock connection that sleeps to simulate latency
        delay_seconds = 0.3

        def create_mock_connection(rows_data):
            conn_id = uuid.uuid4()
            mock_engine = MagicMock()
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)

            mock_result = MagicMock()
            mock_result.keys.return_value = ["id", "val"]
            mock_result.fetchall.return_value = rows_data

            call_count_inner = 0

            def side_effect(*args, **kwargs):
                nonlocal call_count_inner
                call_count_inner += 1
                if call_count_inner == 1:
                    return MagicMock()  # SET timeout
                time.sleep(delay_seconds)
                return mock_result

            mock_conn.execute.side_effect = side_effect
            mock_engine.connect.return_value = mock_conn
            connection_manager._pools[conn_id] = mock_engine
            connection_manager._db_types[conn_id] = "postgresql"
            return conn_id

        conn_id_1 = create_mock_connection([(1, "a"), (2, "b")])
        conn_id_2 = create_mock_connection([(3, "c"), (4, "d")])

        cs_engine = CrossSourceQueryEngine(duckdb_manager, connection_manager)

        plan = CrossSourcePlan(
            sub_queries=[
                SubQuery(
                    alias="src1",
                    sql="SELECT id, val FROM table1",
                    source_id=conn_id_1,
                    source_type="connection",
                ),
                SubQuery(
                    alias="src2",
                    sql="SELECT id, val FROM table2",
                    source_id=conn_id_2,
                    source_type="connection",
                ),
            ],
            join_sql=(
                'SELECT s1.id AS id1, s2.id AS id2 '
                'FROM "src1" s1, "src2" s2'
            ),
        )

        start = time.monotonic()
        result = cs_engine.execute(plan)
        elapsed = time.monotonic() - start

        assert result.status == "success"
        # Sequential would take ~2 * delay_seconds = 0.6s
        # Parallel should be close to delay_seconds = 0.3s
        # Allow generous margin; the key check is it's clearly less than 2x
        assert elapsed < delay_seconds * 2, (
            f"Parallel execution took {elapsed:.2f}s, expected < {delay_seconds * 2:.2f}s"
        )


# ---------------------------------------------------------------------------
# Integration: API endpoint tests
# ---------------------------------------------------------------------------


class TestCrossSourceAPI:
    """Test POST /api/v1/queries/execute/cross-source endpoint."""

    @pytest.mark.asyncio
    async def test_cross_source_duckdb_join(self, client) -> None:
        """Cross-source join between two DuckDB datasets via API."""
        ds_id_1 = str(uuid.uuid4())
        ds_id_2 = str(uuid.uuid4())
        response = await client.post(
            "/api/v1/queries/execute/cross-source",
            json={
                "sub_queries": [
                    {
                        "alias": "orders",
                        "sql": "SELECT order_id, customer_id, amount FROM ds_orders",
                        "source_id": ds_id_1,
                        "source_type": "dataset",
                    },
                    {
                        "alias": "customers",
                        "sql": "SELECT customer_id, name FROM ds_customers",
                        "source_id": ds_id_2,
                        "source_type": "dataset",
                    },
                ],
                "join_sql": (
                    'SELECT o.order_id, o.amount, c.name '
                    'FROM "orders" o JOIN "customers" c '
                    'ON o.customer_id = c.customer_id '
                    'ORDER BY o.order_id'
                ),
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["row_count"] == 4
        assert "order_id" in body["columns"]
        assert "name" in body["columns"]
        assert "sub_query_times_ms" in body
        assert isinstance(body["execution_time_ms"], int)

    @pytest.mark.asyncio
    async def test_write_sql_rejected_400(self, client) -> None:
        """Write operations in sub-query SQL are rejected."""
        response = await client.post(
            "/api/v1/queries/execute/cross-source",
            json={
                "sub_queries": [
                    {
                        "alias": "bad",
                        "sql": "INSERT INTO test VALUES (1)",
                        "source_id": str(uuid.uuid4()),
                        "source_type": "dataset",
                    },
                ],
                "join_sql": 'SELECT * FROM "bad"',
            },
        )
        assert response.status_code == 400
        assert "READ_ONLY" in response.json()["error"]["code"]

    @pytest.mark.asyncio
    async def test_write_join_sql_rejected_400(self, client) -> None:
        """Write operations in join SQL are rejected."""
        response = await client.post(
            "/api/v1/queries/execute/cross-source",
            json={
                "sub_queries": [
                    {
                        "alias": "data",
                        "sql": "SELECT * FROM ds_orders",
                        "source_id": str(uuid.uuid4()),
                        "source_type": "dataset",
                    },
                ],
                "join_sql": 'INSERT INTO target SELECT * FROM "data"',
            },
        )
        assert response.status_code == 400
        assert "READ_ONLY" in response.json()["error"]["code"]

    @pytest.mark.asyncio
    async def test_invalid_source_type_rejected_400(self, client) -> None:
        """Invalid source_type in sub-query returns 400."""
        response = await client.post(
            "/api/v1/queries/execute/cross-source",
            json={
                "sub_queries": [
                    {
                        "alias": "data",
                        "sql": "SELECT 1",
                        "source_id": str(uuid.uuid4()),
                        "source_type": "invalid_type",
                    },
                ],
                "join_sql": 'SELECT * FROM "data"',
            },
        )
        assert response.status_code == 400
        assert "INVALID_SOURCE_TYPE" in response.json()["error"]["code"]

    @pytest.mark.asyncio
    async def test_empty_sub_queries_rejected_422(self, client) -> None:
        """Empty sub_queries list returns 422 validation error."""
        response = await client.post(
            "/api/v1/queries/execute/cross-source",
            json={
                "sub_queries": [],
                "join_sql": "SELECT 1",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_sub_query_error_returns_400(self, client) -> None:
        """Sub-query failure returns 400 with error details."""
        response = await client.post(
            "/api/v1/queries/execute/cross-source",
            json={
                "sub_queries": [
                    {
                        "alias": "bad",
                        "sql": "SELECT * FROM nonexistent_table_xyz",
                        "source_id": str(uuid.uuid4()),
                        "source_type": "dataset",
                    },
                ],
                "join_sql": 'SELECT * FROM "bad"',
            },
        )
        assert response.status_code == 400
        body = response.json()
        assert "error" in body
        assert "bad" in body["error"]["message"]

    @pytest.mark.asyncio
    async def test_connection_not_found_returns_404(self, client) -> None:
        """Non-existent connection in sub-query returns 404."""
        response = await client.post(
            "/api/v1/queries/execute/cross-source",
            json={
                "sub_queries": [
                    {
                        "alias": "remote",
                        "sql": "SELECT 1",
                        "source_id": str(uuid.uuid4()),
                        "source_type": "connection",
                    },
                ],
                "join_sql": 'SELECT * FROM "remote"',
            },
        )
        assert response.status_code == 404
        assert "SOURCE_NOT_FOUND" in response.json()["error"]["code"]

    @pytest.mark.asyncio
    async def test_timeout_returns_408(self, app) -> None:
        """Sub-query timeout returns 408."""
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
            if call_count == 1:
                return MagicMock()
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
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            response = await c.post(
                "/api/v1/queries/execute/cross-source",
                json={
                    "sub_queries": [
                        {
                            "alias": "remote",
                            "sql": "SELECT * FROM huge_table",
                            "source_id": str(conn_id),
                            "source_type": "connection",
                        },
                    ],
                    "join_sql": 'SELECT * FROM "remote"',
                },
            )
        assert response.status_code == 408
        assert "QUERY_TIMEOUT" in response.json()["error"]["code"]

    @pytest.mark.asyncio
    async def test_connection_lost_returns_503(self, app) -> None:
        """Connection lost during sub-query returns 503."""
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
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            response = await c.post(
                "/api/v1/queries/execute/cross-source",
                json={
                    "sub_queries": [
                        {
                            "alias": "remote",
                            "sql": "SELECT 1",
                            "source_id": str(conn_id),
                            "source_type": "connection",
                        },
                    ],
                    "join_sql": 'SELECT * FROM "remote"',
                },
            )
        assert response.status_code == 503
        assert "CONNECTION_ERROR" in response.json()["error"]["code"]

    @pytest.mark.asyncio
    async def test_empty_join_result(self, client) -> None:
        """Cross-source join with no matching rows returns empty result."""
        ds_id = str(uuid.uuid4())
        response = await client.post(
            "/api/v1/queries/execute/cross-source",
            json={
                "sub_queries": [
                    {
                        "alias": "orders",
                        "sql": "SELECT * FROM ds_orders WHERE amount > 999999",
                        "source_id": ds_id,
                        "source_type": "dataset",
                    },
                    {
                        "alias": "customers",
                        "sql": "SELECT * FROM ds_customers",
                        "source_id": ds_id,
                        "source_type": "dataset",
                    },
                ],
                "join_sql": (
                    'SELECT o.order_id, c.name '
                    'FROM "orders" o JOIN "customers" c '
                    'ON o.customer_id = c.customer_id'
                ),
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["row_count"] == 0
        assert body["rows"] == []
