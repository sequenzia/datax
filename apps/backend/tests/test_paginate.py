"""Tests for POST /api/v1/queries/paginate endpoint.

Covers:
- Integration: Pagination with various offset/limit combinations
- Integration: Sort ordering produces correct results
- Integration: Read-only SQL validation blocks write queries
- Edge cases: Offset beyond total rows, SQL with existing LIMIT/OFFSET
- Error handling: Invalid SQL, source not found, query timeout
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app

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
    """Create a temporary CSV file with enough rows for pagination testing."""
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w") as f:
        f.write("id,name,value\n")
        for i in range(1, 11):
            f.write(f"{i},Item{i},{i * 100}\n")
    yield Path(path)
    os.unlink(path)


def _test_settings(db_path: Path) -> Settings:
    """Create test settings with required fields."""
    env = {
        "DATABASE_URL": f"sqlite:///{db_path}",
        "DATAX_ENCRYPTION_KEY": "test-encryption-key",
        "DATAX_DUCKDB_PATH": ":memory:",
    }
    with patch.dict(os.environ, env, clear=True):
        return Settings()  # type: ignore[call-arg]


@pytest.fixture
def app(db_path, csv_file):
    """Create a FastAPI app with test DuckDB dataset for pagination tests."""
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker

    from app.models.base import Base

    application = create_app(settings=_test_settings(db_path))

    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    application.state.db_engine = engine
    application.state.session_factory = sf

    # Register a test CSV file in DuckDB so we have a dataset source to query
    duckdb_mgr = application.state.duckdb_manager
    duckdb_mgr.register_file(str(csv_file), "test_table", "csv")

    # Reset query_service if it was cached
    if hasattr(application.state, "query_service"):
        del application.state.query_service

    yield application
    engine.dispose()


@pytest.fixture
async def client(app):
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


# A stable source_id for dataset tests (does not need to exist in DB)
DATASET_SOURCE_ID = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Integration: Pagination with various offset/limit combinations
# ---------------------------------------------------------------------------


class TestPaginationBasic:
    """Test POST /api/v1/queries/paginate with various offset/limit combos."""

    @pytest.mark.asyncio
    async def test_first_page(self, client) -> None:
        """First page with limit=3 returns 3 rows and correct total."""
        response = await client.post(
            "/api/v1/queries/paginate",
            json={
                "sql": "SELECT * FROM test_table",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
                "offset": 0,
                "limit": 3,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["rows"]) == 3
        assert body["total_rows"] == 10
        assert body["offset"] == 0
        assert body["limit"] == 3
        assert body["columns"] == ["id", "name", "value"]
        assert "execution_time_ms" in body

    @pytest.mark.asyncio
    async def test_second_page(self, client) -> None:
        """Second page with offset=3, limit=3 returns next 3 rows."""
        response = await client.post(
            "/api/v1/queries/paginate",
            json={
                "sql": "SELECT * FROM test_table",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
                "offset": 3,
                "limit": 3,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["rows"]) == 3
        assert body["total_rows"] == 10
        assert body["offset"] == 3

    @pytest.mark.asyncio
    async def test_last_partial_page(self, client) -> None:
        """Last page may have fewer rows than limit."""
        response = await client.post(
            "/api/v1/queries/paginate",
            json={
                "sql": "SELECT * FROM test_table",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
                "offset": 8,
                "limit": 5,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["rows"]) == 2  # Only 2 rows remain (rows 9 and 10)
        assert body["total_rows"] == 10

    @pytest.mark.asyncio
    async def test_default_offset_limit(self, client) -> None:
        """Default offset=0 and limit=100 when not specified."""
        response = await client.post(
            "/api/v1/queries/paginate",
            json={
                "sql": "SELECT * FROM test_table",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["rows"]) == 10
        assert body["total_rows"] == 10
        assert body["offset"] == 0
        assert body["limit"] == 100


# ---------------------------------------------------------------------------
# Integration: Sort ordering produces correct results
# ---------------------------------------------------------------------------


class TestPaginationSort:
    """Test that sort_by and sort_order produce correct ordering."""

    @pytest.mark.asyncio
    async def test_sort_by_value_desc(self, client) -> None:
        """Sorting by value DESC returns highest values first."""
        response = await client.post(
            "/api/v1/queries/paginate",
            json={
                "sql": "SELECT * FROM test_table",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
                "offset": 0,
                "limit": 3,
                "sort_by": "value",
                "sort_order": "desc",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["rows"]) == 3
        # value column is index 2; highest values first
        values = [row[2] for row in body["rows"]]
        assert values == sorted(values, reverse=True)
        assert values[0] == 1000  # 10 * 100

    @pytest.mark.asyncio
    async def test_sort_by_value_asc(self, client) -> None:
        """Sorting by value ASC returns lowest values first."""
        response = await client.post(
            "/api/v1/queries/paginate",
            json={
                "sql": "SELECT * FROM test_table",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
                "offset": 0,
                "limit": 3,
                "sort_by": "value",
                "sort_order": "asc",
            },
        )
        assert response.status_code == 200
        body = response.json()
        values = [row[2] for row in body["rows"]]
        assert values == sorted(values)
        assert values[0] == 100  # 1 * 100

    @pytest.mark.asyncio
    async def test_sort_by_name_desc(self, client) -> None:
        """Sorting by name DESC produces alphabetically reversed order."""
        response = await client.post(
            "/api/v1/queries/paginate",
            json={
                "sql": "SELECT * FROM test_table",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
                "offset": 0,
                "limit": 10,
                "sort_by": "name",
                "sort_order": "desc",
            },
        )
        assert response.status_code == 200
        body = response.json()
        names = [row[1] for row in body["rows"]]
        assert names == sorted(names, reverse=True)

    @pytest.mark.asyncio
    async def test_no_sort_returns_results(self, client) -> None:
        """When sort_by is not provided, results are returned without sorting."""
        response = await client.post(
            "/api/v1/queries/paginate",
            json={
                "sql": "SELECT * FROM test_table",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
                "offset": 0,
                "limit": 5,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["rows"]) == 5


# ---------------------------------------------------------------------------
# Integration: Read-only SQL validation blocks write queries
# ---------------------------------------------------------------------------


class TestPaginationReadOnly:
    """Test that write operations are rejected by the paginate endpoint."""

    @pytest.mark.asyncio
    async def test_insert_rejected(self, client) -> None:
        """INSERT statement returns 400 with READ_ONLY_VIOLATION."""
        response = await client.post(
            "/api/v1/queries/paginate",
            json={
                "sql": "INSERT INTO test_table VALUES (11, 'X', 1100)",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )
        assert response.status_code == 400
        assert "READ_ONLY" in response.json()["error"]["code"]

    @pytest.mark.asyncio
    async def test_delete_rejected(self, client) -> None:
        """DELETE statement returns 400."""
        response = await client.post(
            "/api/v1/queries/paginate",
            json={
                "sql": "DELETE FROM test_table WHERE id = 1",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )
        assert response.status_code == 400
        assert "READ_ONLY" in response.json()["error"]["code"]

    @pytest.mark.asyncio
    async def test_drop_rejected(self, client) -> None:
        """DROP statement returns 400."""
        response = await client.post(
            "/api/v1/queries/paginate",
            json={
                "sql": "DROP TABLE test_table",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )
        assert response.status_code == 400
        assert "READ_ONLY" in response.json()["error"]["code"]

    @pytest.mark.asyncio
    async def test_update_rejected(self, client) -> None:
        """UPDATE statement returns 400."""
        response = await client.post(
            "/api/v1/queries/paginate",
            json={
                "sql": "UPDATE test_table SET value = 0",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )
        assert response.status_code == 400
        assert "READ_ONLY" in response.json()["error"]["code"]


# ---------------------------------------------------------------------------
# Edge cases: Offset beyond total rows
# ---------------------------------------------------------------------------


class TestPaginationEdgeCases:
    """Test edge cases for pagination."""

    @pytest.mark.asyncio
    async def test_offset_beyond_total_rows(self, client) -> None:
        """Offset beyond total rows returns empty result with correct total."""
        response = await client.post(
            "/api/v1/queries/paginate",
            json={
                "sql": "SELECT * FROM test_table",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
                "offset": 1000,
                "limit": 100,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["rows"]) == 0
        assert body["total_rows"] == 10

    @pytest.mark.asyncio
    async def test_sql_with_existing_limit(self, client) -> None:
        """SQL with existing LIMIT/OFFSET is wrapped correctly as subquery."""
        response = await client.post(
            "/api/v1/queries/paginate",
            json={
                "sql": "SELECT * FROM test_table LIMIT 5",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
                "offset": 0,
                "limit": 3,
            },
        )
        assert response.status_code == 200
        body = response.json()
        # The subquery yields 5 rows; paginating with limit 3 returns 3 rows
        assert len(body["rows"]) == 3
        # The total_rows should be from the inner query: 5 rows
        assert body["total_rows"] == 5

    @pytest.mark.asyncio
    async def test_sql_with_existing_limit_and_offset(self, client) -> None:
        """SQL with both LIMIT and OFFSET wraps as subquery correctly."""
        response = await client.post(
            "/api/v1/queries/paginate",
            json={
                "sql": "SELECT * FROM test_table LIMIT 4 OFFSET 2",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
                "offset": 1,
                "limit": 2,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["rows"]) == 2
        assert body["total_rows"] == 4


# ---------------------------------------------------------------------------
# Error handling: Invalid SQL
# ---------------------------------------------------------------------------


class TestPaginationErrorHandling:
    """Test error handling for the paginate endpoint."""

    @pytest.mark.asyncio
    async def test_invalid_sql_returns_400(self, client) -> None:
        """Invalid SQL syntax returns 400 with error message."""
        response = await client.post(
            "/api/v1/queries/paginate",
            json={
                "sql": "SELECTT * FROMM invalid_syntax!!!",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )
        assert response.status_code == 400
        body = response.json()
        assert "error" in body

    @pytest.mark.asyncio
    async def test_source_not_found_returns_404(self, client) -> None:
        """Non-existent connection source returns 404."""
        fake_id = str(uuid.uuid4())
        response = await client.post(
            "/api/v1/queries/paginate",
            json={
                "sql": "SELECT 1",
                "source_id": fake_id,
                "source_type": "connection",
            },
        )
        assert response.status_code == 404
        body = response.json()
        assert "error" in body

    @pytest.mark.asyncio
    async def test_invalid_source_type_returns_400(self, client) -> None:
        """Invalid source_type returns 400."""
        response = await client.post(
            "/api/v1/queries/paginate",
            json={
                "sql": "SELECT 1",
                "source_id": str(uuid.uuid4()),
                "source_type": "invalid",
            },
        )
        assert response.status_code == 400
        assert "INVALID_SOURCE_TYPE" in response.json()["error"]["code"]

    @pytest.mark.asyncio
    async def test_empty_sql_returns_422(self, client) -> None:
        """Empty SQL string returns 422 validation error."""
        response = await client.post(
            "/api/v1/queries/paginate",
            json={
                "sql": "",
                "source_id": DATASET_SOURCE_ID,
                "source_type": "dataset",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_timeout_returns_408(self, app) -> None:
        """Simulated timeout returns 408."""
        import duckdb

        with patch.object(
            app.state.duckdb_manager,
            "execute_query",
            side_effect=duckdb.Error("query timeout exceeded"),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    "/api/v1/queries/paginate",
                    json={
                        "sql": "SELECT * FROM test_table",
                        "source_id": DATASET_SOURCE_ID,
                        "source_type": "dataset",
                    },
                )
            assert response.status_code == 408
            assert "QUERY_TIMEOUT" in response.json()["error"]["code"]
