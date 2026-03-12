"""Tests for the dataset preview API endpoint.

Covers:
- Integration: Pagination returns correct slices
- Integration: Sorting produces correctly ordered results
- Integration: Column types preserved in response
- Edge cases: offset beyond total, limit of 0, non-existent sort column, empty dataset, wide tables
- Error handling: dataset not found, not ready, DuckDB errors
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.datasets import DatasetInfo
from app.config import Settings
from app.main import create_app
from app.models.dataset import DatasetStatus
from app.services.duckdb_manager import DuckDBManager


def _test_settings() -> Settings:
    """Create test settings with required fields."""
    env = {
        "DATABASE_URL": "sqlite:///:memory:",
        "DATAX_ENCRYPTION_KEY": "test-encryption-key",
    }
    with patch.dict(os.environ, env, clear=True):
        return Settings()  # type: ignore[call-arg]


def _write_csv(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


DATASET_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TABLE_NAME = "ds_test_preview"


@pytest.fixture
def tmp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def duckdb_mgr():
    """Create a fresh in-memory DuckDB manager."""
    mgr = DuckDBManager()
    yield mgr
    mgr.close()


@pytest.fixture
def app_with_duckdb(duckdb_mgr):
    """Create a FastAPI app with a real DuckDB manager attached."""
    app = create_app(settings=_test_settings())
    app.state.duckdb_manager = duckdb_mgr
    return app


@pytest.fixture
async def client(app_with_duckdb):
    """Create an async test client."""
    transport = ASGITransport(app=app_with_duckdb)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


def _mock_lookup(
    dataset_id: uuid.UUID = DATASET_ID,
    table_name: str = TABLE_NAME,
    status: str = DatasetStatus.READY.value,
) -> AsyncMock:
    """Create a mock for _lookup_dataset that returns a DatasetInfo."""
    mock = AsyncMock(
        return_value=DatasetInfo(
            id=dataset_id,
            duckdb_table_name=table_name,
            status=status,
        )
    )
    return mock


def _register_csv(duckdb_mgr: DuckDBManager, tmp_dir: Path, content: str) -> None:
    """Register a CSV as the test preview table."""
    csv_path = _write_csv(tmp_dir / "preview_data.csv", content)
    result = duckdb_mgr.register_file(csv_path, TABLE_NAME, "csv")
    assert result.is_success


# ---------------------------------------------------------------------------
# Integration: Pagination
# ---------------------------------------------------------------------------


class TestPagination:
    """Test pagination returns correct slices."""

    @pytest.mark.asyncio
    async def test_default_pagination(self, client, duckdb_mgr, tmp_dir) -> None:
        """Default offset=0, limit=100 returns all rows when fewer than limit."""
        _register_csv(duckdb_mgr, tmp_dir, "id,name\n1,Alice\n2,Bob\n3,Carol\n")

        with patch("app.api.v1.datasets._lookup_dataset", _mock_lookup()):
            response = await client.get(f"/api/v1/datasets/{DATASET_ID}/preview")

        assert response.status_code == 200
        body = response.json()
        assert body["offset"] == 0
        assert body["limit"] == 100
        assert body["total_rows"] == 3
        assert len(body["rows"]) == 3

    @pytest.mark.asyncio
    async def test_custom_offset_and_limit(self, client, duckdb_mgr, tmp_dir) -> None:
        """Custom offset and limit return correct slice."""
        rows = "id,name\n" + "\n".join(f"{i},Name{i}" for i in range(10)) + "\n"
        _register_csv(duckdb_mgr, tmp_dir, rows)

        with patch("app.api.v1.datasets._lookup_dataset", _mock_lookup()):
            response = await client.get(
                f"/api/v1/datasets/{DATASET_ID}/preview?offset=3&limit=4"
            )

        assert response.status_code == 200
        body = response.json()
        assert body["offset"] == 3
        assert body["limit"] == 4
        assert body["total_rows"] == 10
        assert len(body["rows"]) == 4

    @pytest.mark.asyncio
    async def test_offset_clips_to_remaining(self, client, duckdb_mgr, tmp_dir) -> None:
        """Offset near end returns only remaining rows."""
        rows = "id\n" + "\n".join(str(i) for i in range(5)) + "\n"
        _register_csv(duckdb_mgr, tmp_dir, rows)

        with patch("app.api.v1.datasets._lookup_dataset", _mock_lookup()):
            response = await client.get(
                f"/api/v1/datasets/{DATASET_ID}/preview?offset=3&limit=100"
            )

        assert response.status_code == 200
        body = response.json()
        assert body["total_rows"] == 5
        assert len(body["rows"]) == 2

    @pytest.mark.asyncio
    async def test_columns_match_table_schema(self, client, duckdb_mgr, tmp_dir) -> None:
        """Columns array matches the actual table schema."""
        _register_csv(duckdb_mgr, tmp_dir, "id,name,age,score\n1,Alice,30,95.5\n")

        with patch("app.api.v1.datasets._lookup_dataset", _mock_lookup()):
            response = await client.get(f"/api/v1/datasets/{DATASET_ID}/preview")

        assert response.status_code == 200
        body = response.json()
        assert body["columns"] == ["id", "name", "age", "score"]

    @pytest.mark.asyncio
    async def test_rows_in_correct_column_order(self, client, duckdb_mgr, tmp_dir) -> None:
        """Row values are in the same order as the columns array."""
        _register_csv(duckdb_mgr, tmp_dir, "id,name,age\n1,Alice,30\n")

        with patch("app.api.v1.datasets._lookup_dataset", _mock_lookup()):
            response = await client.get(f"/api/v1/datasets/{DATASET_ID}/preview")

        body = response.json()
        columns = body["columns"]
        row = body["rows"][0]
        # id=1, name=Alice, age=30
        id_idx = columns.index("id")
        name_idx = columns.index("name")
        age_idx = columns.index("age")
        assert row[id_idx] == 1
        assert row[name_idx] == "Alice"
        assert row[age_idx] == 30

    @pytest.mark.asyncio
    async def test_total_rows_reflects_actual_count(self, client, duckdb_mgr, tmp_dir) -> None:
        """total_rows reflects the full table row count regardless of pagination."""
        rows = "v\n" + "\n".join(str(i) for i in range(50)) + "\n"
        _register_csv(duckdb_mgr, tmp_dir, rows)

        with patch("app.api.v1.datasets._lookup_dataset", _mock_lookup()):
            response = await client.get(
                f"/api/v1/datasets/{DATASET_ID}/preview?offset=0&limit=5"
            )

        body = response.json()
        assert body["total_rows"] == 50
        assert len(body["rows"]) == 5


# ---------------------------------------------------------------------------
# Integration: Sorting
# ---------------------------------------------------------------------------


class TestSorting:
    """Test sorting produces correctly ordered results."""

    @pytest.mark.asyncio
    async def test_sort_ascending(self, client, duckdb_mgr, tmp_dir) -> None:
        """Sorting by a column in ascending order."""
        _register_csv(duckdb_mgr, tmp_dir, "name,score\nCharlie,70\nAlice,90\nBob,80\n")

        with patch("app.api.v1.datasets._lookup_dataset", _mock_lookup()):
            response = await client.get(
                f"/api/v1/datasets/{DATASET_ID}/preview?sort_by=name&sort_order=asc"
            )

        body = response.json()
        names = [row[body["columns"].index("name")] for row in body["rows"]]
        assert names == ["Alice", "Bob", "Charlie"]

    @pytest.mark.asyncio
    async def test_sort_descending(self, client, duckdb_mgr, tmp_dir) -> None:
        """Sorting by a column in descending order."""
        _register_csv(duckdb_mgr, tmp_dir, "name,score\nCharlie,70\nAlice,90\nBob,80\n")

        with patch("app.api.v1.datasets._lookup_dataset", _mock_lookup()):
            response = await client.get(
                f"/api/v1/datasets/{DATASET_ID}/preview?sort_by=score&sort_order=desc"
            )

        body = response.json()
        scores = [row[body["columns"].index("score")] for row in body["rows"]]
        assert scores == [90, 80, 70]

    @pytest.mark.asyncio
    async def test_sort_with_pagination(self, client, duckdb_mgr, tmp_dir) -> None:
        """Sorting combined with pagination returns correct slice."""
        content = "id,val\n" + "\n".join(f"{i},{100-i}" for i in range(10)) + "\n"
        _register_csv(duckdb_mgr, tmp_dir, content)

        with patch("app.api.v1.datasets._lookup_dataset", _mock_lookup()):
            response = await client.get(
                f"/api/v1/datasets/{DATASET_ID}/preview"
                "?sort_by=val&sort_order=asc&offset=0&limit=3"
            )

        body = response.json()
        vals = [row[body["columns"].index("val")] for row in body["rows"]]
        # val column: 100-0=100, 100-1=99, ..., 100-9=91
        # sorted ascending: 91, 92, 93, ...
        assert vals == [91, 92, 93]


# ---------------------------------------------------------------------------
# Integration: Column types preserved
# ---------------------------------------------------------------------------


class TestColumnTypes:
    """Test that column types are preserved in the response."""

    @pytest.mark.asyncio
    async def test_integer_types_preserved(self, client, duckdb_mgr, tmp_dir) -> None:
        """Integer values are returned as integers, not strings."""
        _register_csv(duckdb_mgr, tmp_dir, "id,count\n1,100\n2,200\n")

        with patch("app.api.v1.datasets._lookup_dataset", _mock_lookup()):
            response = await client.get(f"/api/v1/datasets/{DATASET_ID}/preview")

        body = response.json()
        for row in body["rows"]:
            assert isinstance(row[0], int)
            assert isinstance(row[1], int)

    @pytest.mark.asyncio
    async def test_float_types_preserved(self, client, duckdb_mgr, tmp_dir) -> None:
        """Float values are returned as floats."""
        _register_csv(duckdb_mgr, tmp_dir, "val\n3.14\n2.71\n")

        with patch("app.api.v1.datasets._lookup_dataset", _mock_lookup()):
            response = await client.get(f"/api/v1/datasets/{DATASET_ID}/preview")

        body = response.json()
        for row in body["rows"]:
            assert isinstance(row[0], float)

    @pytest.mark.asyncio
    async def test_string_types_preserved(self, client, duckdb_mgr, tmp_dir) -> None:
        """String values are returned as strings."""
        _register_csv(duckdb_mgr, tmp_dir, "name\nAlice\nBob\n")

        with patch("app.api.v1.datasets._lookup_dataset", _mock_lookup()):
            response = await client.get(f"/api/v1/datasets/{DATASET_ID}/preview")

        body = response.json()
        for row in body["rows"]:
            assert isinstance(row[0], str)

    @pytest.mark.asyncio
    async def test_null_values_preserved(self, client, duckdb_mgr, tmp_dir) -> None:
        """NULL values are returned as null/None."""
        # DuckDB treats empty CSV fields as NULL for numeric types
        _register_csv(duckdb_mgr, tmp_dir, "id,value\n1,100\n2,\n")

        with patch("app.api.v1.datasets._lookup_dataset", _mock_lookup()):
            response = await client.get(f"/api/v1/datasets/{DATASET_ID}/preview")

        body = response.json()
        # Second row should have None for the value column
        val_idx = body["columns"].index("value")
        assert body["rows"][1][val_idx] is None


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for the preview endpoint."""

    @pytest.mark.asyncio
    async def test_offset_beyond_total_returns_empty(
        self, client, duckdb_mgr, tmp_dir
    ) -> None:
        """Offset beyond total rows returns empty rows array."""
        _register_csv(duckdb_mgr, tmp_dir, "id\n1\n2\n3\n")

        with patch("app.api.v1.datasets._lookup_dataset", _mock_lookup()):
            response = await client.get(
                f"/api/v1/datasets/{DATASET_ID}/preview?offset=100"
            )

        assert response.status_code == 200
        body = response.json()
        assert body["rows"] == []
        assert body["total_rows"] == 3

    @pytest.mark.asyncio
    async def test_limit_zero_returns_no_rows(self, client, duckdb_mgr, tmp_dir) -> None:
        """Limit of 0 returns no rows but includes total_rows."""
        _register_csv(duckdb_mgr, tmp_dir, "id\n1\n2\n3\n")

        with patch("app.api.v1.datasets._lookup_dataset", _mock_lookup()):
            response = await client.get(
                f"/api/v1/datasets/{DATASET_ID}/preview?limit=0"
            )

        assert response.status_code == 200
        body = response.json()
        assert body["rows"] == []
        assert body["total_rows"] == 3
        assert len(body["columns"]) > 0

    @pytest.mark.asyncio
    async def test_nonexistent_sort_column_returns_400(
        self, client, duckdb_mgr, tmp_dir
    ) -> None:
        """sort_by with non-existent column returns 400."""
        _register_csv(duckdb_mgr, tmp_dir, "id,name\n1,Alice\n")

        with patch("app.api.v1.datasets._lookup_dataset", _mock_lookup()):
            response = await client.get(
                f"/api/v1/datasets/{DATASET_ID}/preview?sort_by=nonexistent"
            )

        assert response.status_code == 400
        body = response.json()
        assert "error" in body
        assert "nonexistent" in body["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_empty_dataset_returns_empty_rows(
        self, client, duckdb_mgr, tmp_dir
    ) -> None:
        """Dataset with 0 rows returns empty rows array."""
        _register_csv(duckdb_mgr, tmp_dir, "id,name,value\n")

        with patch("app.api.v1.datasets._lookup_dataset", _mock_lookup()):
            response = await client.get(f"/api/v1/datasets/{DATASET_ID}/preview")

        assert response.status_code == 200
        body = response.json()
        assert body["rows"] == []
        assert body["total_rows"] == 0
        assert body["columns"] == ["id", "name", "value"]

    @pytest.mark.asyncio
    async def test_wide_table_returns_all_columns(
        self, client, duckdb_mgr, tmp_dir
    ) -> None:
        """Very wide table (500+ columns) returns all columns."""
        num_cols = 501
        headers = ",".join(f"col{i}" for i in range(num_cols))
        values = ",".join(str(i) for i in range(num_cols))
        _register_csv(duckdb_mgr, tmp_dir, f"{headers}\n{values}\n")

        with patch("app.api.v1.datasets._lookup_dataset", _mock_lookup()):
            response = await client.get(f"/api/v1/datasets/{DATASET_ID}/preview")

        assert response.status_code == 200
        body = response.json()
        assert len(body["columns"]) == num_cols
        assert len(body["rows"]) == 1
        assert len(body["rows"][0]) == num_cols


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Error handling tests for the preview endpoint."""

    @pytest.mark.asyncio
    async def test_dataset_not_found_returns_404(self, client) -> None:
        """Non-existent dataset returns 404."""
        missing_id = uuid.uuid4()

        # Default _lookup_dataset raises 404
        response = await client.get(f"/api/v1/datasets/{missing_id}/preview")

        assert response.status_code == 404
        body = response.json()
        assert "error" in body

    @pytest.mark.asyncio
    async def test_dataset_not_ready_returns_409(
        self, client, duckdb_mgr, tmp_dir
    ) -> None:
        """Dataset not in 'ready' status returns 409 with status info."""
        mock = _mock_lookup(status=DatasetStatus.PROCESSING.value)

        with patch("app.api.v1.datasets._lookup_dataset", mock):
            response = await client.get(f"/api/v1/datasets/{DATASET_ID}/preview")

        assert response.status_code == 409
        body = response.json()
        assert "error" in body
        assert "processing" in body["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_dataset_error_status_returns_409(
        self, client, duckdb_mgr, tmp_dir
    ) -> None:
        """Dataset in 'error' status returns 409."""
        mock = _mock_lookup(status=DatasetStatus.ERROR.value)

        with patch("app.api.v1.datasets._lookup_dataset", mock):
            response = await client.get(f"/api/v1/datasets/{DATASET_ID}/preview")

        assert response.status_code == 409
        body = response.json()
        assert "error" in body

    @pytest.mark.asyncio
    async def test_unregistered_table_returns_500(self, client) -> None:
        """DuckDB table not registered returns 500."""
        mock = _mock_lookup(table_name="ds_nonexistent_table")

        with patch("app.api.v1.datasets._lookup_dataset", mock):
            response = await client.get(f"/api/v1/datasets/{DATASET_ID}/preview")

        assert response.status_code == 500
        body = response.json()
        assert "error" in body

    @pytest.mark.asyncio
    async def test_invalid_sort_order_returns_422(self, client, duckdb_mgr, tmp_dir) -> None:
        """Invalid sort_order value returns 422 validation error."""
        _register_csv(duckdb_mgr, tmp_dir, "id\n1\n")

        with patch("app.api.v1.datasets._lookup_dataset", _mock_lookup()):
            response = await client.get(
                f"/api/v1/datasets/{DATASET_ID}/preview?sort_order=invalid"
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_negative_offset_returns_422(self, client) -> None:
        """Negative offset returns 422 validation error."""
        response = await client.get(
            f"/api/v1/datasets/{DATASET_ID}/preview?offset=-1"
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_422(self, client) -> None:
        """Invalid UUID format returns 422 validation error."""
        response = await client.get("/api/v1/datasets/not-a-uuid/preview")
        assert response.status_code == 422
