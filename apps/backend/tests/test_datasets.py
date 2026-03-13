"""Tests for the dataset CRUD API endpoints.

Covers:
- Integration: CRUD operations (list, get, delete)
- Integration: Schema info in detail response
- Integration: Delete cascades (file + DuckDB + DB records)
- Edge cases: empty list, non-existent ID 404, delete while processing
- Error handling: invalid UUID 400, not found 404, file deletion failure still cleans DB
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.main import create_app
from app.models.base import Base
from app.models.dataset import DatasetStatus
from app.models.orm import Dataset, SchemaMetadata
from app.services.duckdb_manager import DuckDBManager


@pytest.fixture
def db_path():
    """Create a temporary file for SQLite database."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d) / "test.db"


@pytest.fixture
def tmp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


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
    """Create a SQLite engine backed by a temp file with foreign key support."""
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
def duckdb_mgr():
    """Create a fresh in-memory DuckDB manager."""
    mgr = DuckDBManager()
    yield mgr
    mgr.close()


@pytest.fixture
def app(db_path, db_engine, session_factory, duckdb_mgr):
    """Create a FastAPI app with a test SQLite database and DuckDB manager."""
    application = create_app(settings=_test_settings(db_path))
    application.state.db_engine = db_engine
    application.state.session_factory = session_factory
    application.state.duckdb_manager = duckdb_mgr
    return application


@pytest.fixture
async def client(app):
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.fixture
def db(session_factory) -> Session:
    """Create a database session for test setup/teardown."""
    session = session_factory()
    yield session
    session.close()


def _create_dataset(
    db: Session,
    tmp_dir: Path,
    duckdb_mgr: DuckDBManager,
    *,
    name: str = "test_data.csv",
    status: str = DatasetStatus.READY.value,
    with_schema: bool = False,
    file_content: str = "id,name,value\n1,Alice,100\n2,Bob,200\n",
) -> Dataset:
    """Helper to create a dataset with file and DuckDB registration."""
    file_path = tmp_dir / name
    file_path.write_text(file_content, encoding="utf-8")

    table_name = f"ds_{name.replace('.', '_')}_{uuid.uuid4().hex[:6]}"

    dataset = Dataset(
        name=name,
        file_path=str(file_path),
        file_format="csv",
        file_size_bytes=file_path.stat().st_size,
        row_count=2,
        duckdb_table_name=table_name,
        status=status,
    )
    db.add(dataset)
    db.flush()

    # Register file in DuckDB
    result = duckdb_mgr.register_file(str(file_path), table_name, "csv")
    assert result.is_success

    if with_schema:
        for col_info in result.columns:
            schema = SchemaMetadata(
                source_id=dataset.id,
                source_type="dataset",
                table_name=table_name,
                column_name=col_info.column_name,
                data_type=col_info.data_type,
                is_nullable=col_info.is_nullable,
                is_primary_key=col_info.is_primary_key,
            )
            db.add(schema)
        db.flush()

    db.commit()
    return dataset


# ---------------------------------------------------------------------------
# Integration: List Datasets
# ---------------------------------------------------------------------------


class TestListDatasets:
    """Test GET /api/v1/datasets."""

    @pytest.mark.asyncio
    async def test_list_empty_returns_empty_array(self, client) -> None:
        """Listing datasets when none exist returns empty array."""
        response = await client.get("/api/v1/datasets")
        assert response.status_code == 200
        body = response.json()
        assert body["datasets"] == []

    @pytest.mark.asyncio
    async def test_list_returns_datasets(self, client, db, tmp_dir, duckdb_mgr) -> None:
        """Listing datasets returns created datasets."""
        _create_dataset(db, tmp_dir, duckdb_mgr, name="data1.csv")
        _create_dataset(db, tmp_dir, duckdb_mgr, name="data2.csv")

        response = await client.get("/api/v1/datasets")
        body = response.json()
        assert len(body["datasets"]) == 2

    @pytest.mark.asyncio
    async def test_list_sorted_by_created_at_desc(self, client, db, tmp_dir, duckdb_mgr) -> None:
        """Datasets are sorted by created_at descending (most recent first)."""
        from datetime import UTC, datetime, timedelta

        ds1 = _create_dataset(db, tmp_dir, duckdb_mgr, name="first.csv")
        ds2 = _create_dataset(db, tmp_dir, duckdb_mgr, name="second.csv")

        # Manually set timestamps to ensure ordering
        now = datetime.now(tz=UTC)
        ds1.created_at = now - timedelta(minutes=10)
        ds2.created_at = now
        db.commit()

        response = await client.get("/api/v1/datasets")
        body = response.json()
        ids = [d["id"] for d in body["datasets"]]

        # Most recent first
        assert ids[0] == str(ds2.id)
        assert ids[1] == str(ds1.id)

    @pytest.mark.asyncio
    async def test_list_dataset_fields(self, client, db, tmp_dir, duckdb_mgr) -> None:
        """Each dataset in the list has required fields."""
        _create_dataset(db, tmp_dir, duckdb_mgr)

        response = await client.get("/api/v1/datasets")
        body = response.json()
        ds = body["datasets"][0]
        assert "id" in ds
        assert "name" in ds
        assert "file_format" in ds
        assert "file_size_bytes" in ds
        assert "row_count" in ds
        assert "status" in ds
        assert "created_at" in ds
        assert "updated_at" in ds

    @pytest.mark.asyncio
    async def test_list_returns_all_statuses(self, client, db, tmp_dir, duckdb_mgr) -> None:
        """List returns datasets regardless of status."""
        _create_dataset(
            db, tmp_dir, duckdb_mgr,
            name="ready.csv", status=DatasetStatus.READY.value,
        )
        _create_dataset(
            db, tmp_dir, duckdb_mgr,
            name="processing.csv", status=DatasetStatus.PROCESSING.value,
        )

        response = await client.get("/api/v1/datasets")
        body = response.json()
        assert len(body["datasets"]) == 2


# ---------------------------------------------------------------------------
# Integration: Get Dataset with Schema
# ---------------------------------------------------------------------------


class TestGetDataset:
    """Test GET /api/v1/datasets/{id}."""

    @pytest.mark.asyncio
    async def test_get_returns_dataset(self, client, db, tmp_dir, duckdb_mgr) -> None:
        """Getting a dataset returns its details."""
        ds = _create_dataset(db, tmp_dir, duckdb_mgr)

        response = await client.get(f"/api/v1/datasets/{ds.id}")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(ds.id)
        assert body["name"] == "test_data.csv"
        assert body["file_format"] == "csv"
        assert body["status"] == "ready"

    @pytest.mark.asyncio
    async def test_get_returns_schema_info(self, client, db, tmp_dir, duckdb_mgr) -> None:
        """Getting a dataset with schema returns column metadata."""
        ds = _create_dataset(db, tmp_dir, duckdb_mgr, with_schema=True)

        response = await client.get(f"/api/v1/datasets/{ds.id}")
        body = response.json()

        assert "schema" in body
        assert len(body["schema"]) == 3  # id, name, value columns

        col_names = [s["column_name"] for s in body["schema"]]
        assert "id" in col_names
        assert "name" in col_names
        assert "value" in col_names

        for col in body["schema"]:
            assert "data_type" in col
            assert "is_nullable" in col
            assert "is_primary_key" in col

    @pytest.mark.asyncio
    async def test_get_returns_empty_schema_when_none(
        self, client, db, tmp_dir, duckdb_mgr,
    ) -> None:
        """Getting a dataset without schema returns empty schema array."""
        ds = _create_dataset(db, tmp_dir, duckdb_mgr, with_schema=False)

        response = await client.get(f"/api/v1/datasets/{ds.id}")
        body = response.json()
        assert body["schema"] == []

    @pytest.mark.asyncio
    async def test_get_returns_duckdb_table_name(self, client, db, tmp_dir, duckdb_mgr) -> None:
        """Detail response includes the DuckDB table name."""
        ds = _create_dataset(db, tmp_dir, duckdb_mgr)

        response = await client.get(f"/api/v1/datasets/{ds.id}")
        body = response.json()
        assert "duckdb_table_name" in body
        assert body["duckdb_table_name"] == ds.duckdb_table_name

    @pytest.mark.asyncio
    async def test_get_not_found_returns_404(self, client) -> None:
        """Getting a non-existent dataset returns 404."""
        fake_id = uuid.uuid4()
        response = await client.get(f"/api/v1/datasets/{fake_id}")
        assert response.status_code == 404
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_get_invalid_uuid_returns_422(self, client) -> None:
        """Getting with invalid UUID format returns 422."""
        response = await client.get("/api/v1/datasets/not-a-uuid")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_all_detail_fields(self, client, db, tmp_dir, duckdb_mgr) -> None:
        """Detail response includes all expected fields."""
        ds = _create_dataset(db, tmp_dir, duckdb_mgr)

        response = await client.get(f"/api/v1/datasets/{ds.id}")
        body = response.json()
        expected_fields = [
            "id", "name", "file_format", "file_size_bytes",
            "row_count", "duckdb_table_name", "status",
            "created_at", "updated_at", "schema",
        ]
        for field in expected_fields:
            assert field in body, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# Integration: Delete Dataset
# ---------------------------------------------------------------------------


class TestDeleteDataset:
    """Test DELETE /api/v1/datasets/{id}."""

    @pytest.mark.asyncio
    async def test_delete_returns_204(self, client, db, tmp_dir, duckdb_mgr) -> None:
        """Deleting a dataset returns 204 No Content."""
        ds = _create_dataset(db, tmp_dir, duckdb_mgr)

        response = await client.delete(f"/api/v1/datasets/{ds.id}")
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_removes_from_list(self, client, db, tmp_dir, duckdb_mgr) -> None:
        """Deleted dataset is no longer in list."""
        ds = _create_dataset(db, tmp_dir, duckdb_mgr)

        await client.delete(f"/api/v1/datasets/{ds.id}")

        response = await client.get("/api/v1/datasets")
        body = response.json()
        assert len(body["datasets"]) == 0

    @pytest.mark.asyncio
    async def test_delete_removes_db_record(self, client, db, tmp_dir, duckdb_mgr) -> None:
        """Deleting removes the dataset from the database."""
        ds = _create_dataset(db, tmp_dir, duckdb_mgr)
        dataset_id = ds.id

        await client.delete(f"/api/v1/datasets/{dataset_id}")

        # Verify dataset is gone from DB
        db.expire_all()
        result = db.get(Dataset, dataset_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_removes_file(self, client, db, tmp_dir, duckdb_mgr) -> None:
        """Deleting removes the file from disk."""
        ds = _create_dataset(db, tmp_dir, duckdb_mgr)
        file_path = Path(ds.file_path)
        assert file_path.exists()

        await client.delete(f"/api/v1/datasets/{ds.id}")

        assert not file_path.exists()

    @pytest.mark.asyncio
    async def test_delete_unregisters_duckdb_table(self, client, db, tmp_dir, duckdb_mgr) -> None:
        """Deleting unregisters the DuckDB table."""
        ds = _create_dataset(db, tmp_dir, duckdb_mgr)
        table_name = ds.duckdb_table_name
        assert duckdb_mgr.is_table_registered(table_name)

        await client.delete(f"/api/v1/datasets/{ds.id}")

        assert not duckdb_mgr.is_table_registered(table_name)

    @pytest.mark.asyncio
    async def test_delete_removes_schema_metadata(self, client, db, tmp_dir, duckdb_mgr) -> None:
        """Deleting removes associated schema metadata."""
        ds = _create_dataset(db, tmp_dir, duckdb_mgr, with_schema=True)
        dataset_id = ds.id

        # Verify schema exists
        schema_count = len(
            db.execute(
                select(SchemaMetadata).where(SchemaMetadata.source_id == dataset_id)
            ).scalars().all()
        )
        assert schema_count > 0

        await client.delete(f"/api/v1/datasets/{dataset_id}")

        # Verify schema is gone
        db.expire_all()
        remaining = db.execute(
            select(SchemaMetadata).where(SchemaMetadata.source_id == dataset_id)
        ).scalars().all()
        assert len(remaining) == 0

    @pytest.mark.asyncio
    async def test_delete_not_found_returns_404(self, client) -> None:
        """Deleting a non-existent dataset returns 404."""
        fake_id = uuid.uuid4()
        response = await client.delete(f"/api/v1/datasets/{fake_id}")
        assert response.status_code == 404
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_delete_does_not_affect_other_datasets(
        self, client, db, tmp_dir, duckdb_mgr,
    ) -> None:
        """Deleting one dataset does not affect others."""
        ds1 = _create_dataset(db, tmp_dir, duckdb_mgr, name="data1.csv")
        ds2 = _create_dataset(db, tmp_dir, duckdb_mgr, name="data2.csv")

        await client.delete(f"/api/v1/datasets/{ds1.id}")

        # Second dataset should still exist
        response = await client.get(f"/api/v1/datasets/{ds2.id}")
        assert response.status_code == 200

        # List should show only one dataset
        list_resp = await client.get("/api/v1/datasets")
        assert len(list_resp.json()["datasets"]) == 1


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for dataset CRUD."""

    @pytest.mark.asyncio
    async def test_delete_while_processing_returns_409(
        self, client, db, tmp_dir, duckdb_mgr,
    ) -> None:
        """Deleting a dataset with 'processing' status returns 409."""
        ds = _create_dataset(
            db, tmp_dir, duckdb_mgr,
            status=DatasetStatus.PROCESSING.value,
        )

        response = await client.delete(f"/api/v1/datasets/{ds.id}")
        assert response.status_code == 409
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] == "DATASET_PROCESSING"

    @pytest.mark.asyncio
    async def test_get_detail_then_delete(self, client, db, tmp_dir, duckdb_mgr) -> None:
        """Can get detail and then delete a dataset."""
        ds = _create_dataset(db, tmp_dir, duckdb_mgr)

        # Get detail
        resp = await client.get(f"/api/v1/datasets/{ds.id}")
        assert resp.status_code == 200

        # Delete
        resp = await client.delete(f"/api/v1/datasets/{ds.id}")
        assert resp.status_code == 204

        # Gone
        resp = await client.get(f"/api/v1/datasets/{ds.id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Error handling tests for dataset CRUD."""

    @pytest.mark.asyncio
    async def test_file_deletion_failure_still_cleans_db(
        self, client, db, tmp_dir, duckdb_mgr
    ) -> None:
        """If file deletion fails, DB records are still cleaned up."""
        ds = _create_dataset(db, tmp_dir, duckdb_mgr, with_schema=True)
        dataset_id = ds.id

        # Make file undeletable by removing it before the endpoint tries
        file_path = Path(ds.file_path)
        file_path.unlink()

        response = await client.delete(f"/api/v1/datasets/{dataset_id}")
        assert response.status_code == 204

        # DB records should still be cleaned up
        db.expire_all()
        assert db.get(Dataset, dataset_id) is None
        remaining = db.execute(
            select(SchemaMetadata).where(SchemaMetadata.source_id == dataset_id)
        ).scalars().all()
        assert len(remaining) == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_dataset_returns_404_with_error_format(
        self, client
    ) -> None:
        """404 for non-existent dataset uses structured error format."""
        fake_id = uuid.uuid4()
        response = await client.delete(f"/api/v1/datasets/{fake_id}")
        assert response.status_code == 404
        body = response.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_dataset_returns_404_with_error_format(
        self, client
    ) -> None:
        """404 for non-existent dataset uses structured error format."""
        fake_id = uuid.uuid4()
        response = await client.get(f"/api/v1/datasets/{fake_id}")
        assert response.status_code == 404
        body = response.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]
