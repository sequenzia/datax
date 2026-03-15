"""Tests for GET /api/v1/datasets/{id}/profile endpoint.

Uses a minimal FastAPI app with only the datasets router to avoid the
circular import issue in the full create_app() chain.

Covers:
- Integration: GET /api/v1/datasets/{id}/profile returns stored profile data
- Integration: On-demand profiling when no stored profile exists
- Edge cases: dataset not found (404), dataset not ready (409)
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.datasets import router as datasets_router
from app.errors import register_exception_handlers
from app.models.base import Base
from app.models.dataset import DatasetStatus
from app.models.orm import DataProfile, Dataset

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def db_path():
    """Create a temporary file for SQLite database."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d) / "test.db"


@pytest.fixture
def db_engine(db_path):
    """Create a file-backed SQLite engine with foreign key support."""
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
def db(session_factory) -> Session:
    """Create a database session for test setup/teardown."""
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def duckdb_mgr():
    """Create a fresh in-memory DuckDB manager."""
    from app.services.duckdb_manager import DuckDBManager
    mgr = DuckDBManager()
    yield mgr
    mgr.close()


@pytest.fixture
def app(db_engine, session_factory, duckdb_mgr):
    """Create a minimal FastAPI app with just the datasets router."""
    application = FastAPI()

    # Attach state expected by dependencies
    import os
    from unittest.mock import patch

    from app.config import Settings

    env = {
        "DATABASE_URL": "sqlite://",
        "DATAX_ENCRYPTION_KEY": "test-key",
    }
    with patch.dict(os.environ, env, clear=True):
        settings = Settings()  # type: ignore[call-arg]

    application.state.settings = settings
    application.state.db_engine = db_engine
    application.state.session_factory = session_factory
    application.state.duckdb_manager = duckdb_mgr

    register_exception_handlers(application)
    application.include_router(datasets_router, prefix="/api/v1")

    return application


@pytest.fixture
async def client(app):
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


def _create_dataset(
    db: Session,
    tmp_dir: Path,
    duckdb_mgr,
    *,
    name: str = "test_data.csv",
    status: str = DatasetStatus.READY.value,
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
        row_count=2,
        duckdb_table_name=table_name,
        status=status,
    )
    db.add(dataset)
    db.flush()

    # Register file in DuckDB
    result = duckdb_mgr.register_file(str(file_path), table_name, "csv")
    assert result.is_success

    db.commit()
    return dataset


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/datasets/{id}/profile
# ---------------------------------------------------------------------------


class TestGetDatasetProfile:
    """Test GET /api/v1/datasets/{id}/profile."""

    @pytest.mark.asyncio
    async def test_profile_returns_stored_data(
        self, client, db, tmp_dir, duckdb_mgr,
    ) -> None:
        """Profile endpoint returns stored profiling data when profile exists."""
        ds = _create_dataset(db, tmp_dir, duckdb_mgr)

        summarize = [
            {
                "column_name": "id",
                "column_type": "BIGINT",
                "min": "1",
                "max": "2",
                "avg": "1.5",
                "std": "0.7071",
                "approx_unique": 2,
                "null_percentage": "0.00%",
                "q25": "1",
                "q50": "1",
                "q75": "2",
                "count": "2",
            }
        ]
        sample = {"id": [1, 2]}

        profile = DataProfile(
            dataset_id=ds.id,
            summarize_results=summarize,
            sample_values=sample,
        )
        db.add(profile)
        db.commit()

        response = await client.get(f"/api/v1/datasets/{ds.id}/profile")
        assert response.status_code == 200
        body = response.json()
        assert body["dataset_id"] == str(ds.id)
        assert len(body["summarize_results"]) == 1
        assert body["summarize_results"][0]["column_name"] == "id"
        assert body["sample_values"]["id"] == [1, 2]
        assert body["profiled_at"] is not None

    @pytest.mark.asyncio
    async def test_profile_triggers_on_demand_when_missing(
        self, client, db, tmp_dir, duckdb_mgr,
    ) -> None:
        """Profile endpoint triggers on-demand profiling when no profile exists."""
        ds = _create_dataset(db, tmp_dir, duckdb_mgr)

        response = await client.get(f"/api/v1/datasets/{ds.id}/profile")
        assert response.status_code == 200
        body = response.json()
        assert body["dataset_id"] == str(ds.id)
        assert isinstance(body["summarize_results"], list)
        assert len(body["summarize_results"]) > 0
        assert isinstance(body["sample_values"], dict)
        assert body["profiled_at"] is not None

        # Verify the profile was persisted for subsequent requests
        db.expire_all()
        stored_profile = db.query(DataProfile).filter(
            DataProfile.dataset_id == ds.id
        ).first()
        assert stored_profile is not None

    @pytest.mark.asyncio
    async def test_profile_not_found_returns_404(self, client) -> None:
        """Profile endpoint returns 404 for non-existent dataset."""
        fake_id = uuid.uuid4()
        response = await client.get(f"/api/v1/datasets/{fake_id}/profile")
        assert response.status_code == 404
        body = response.json()
        assert body["error"]["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_profile_not_ready_returns_409(
        self, client, db, tmp_dir, duckdb_mgr,
    ) -> None:
        """Profile endpoint returns 409 when dataset is not ready and has no stored profile."""
        ds = _create_dataset(
            db, tmp_dir, duckdb_mgr,
            status=DatasetStatus.PROCESSING.value,
        )

        response = await client.get(f"/api/v1/datasets/{ds.id}/profile")
        assert response.status_code == 409
        body = response.json()
        assert body["error"]["code"] == "DATASET_NOT_READY"

    @pytest.mark.asyncio
    async def test_profile_on_demand_stores_data_stats(
        self, client, db, tmp_dir, duckdb_mgr,
    ) -> None:
        """On-demand profiling also updates Dataset.data_stats."""
        ds = _create_dataset(db, tmp_dir, duckdb_mgr)

        response = await client.get(f"/api/v1/datasets/{ds.id}/profile")
        assert response.status_code == 200

        # Check Dataset.data_stats was updated
        db.expire_all()
        updated_ds = db.get(Dataset, ds.id)
        assert updated_ds is not None
        assert updated_ds.data_stats is not None
        assert "summarize" in updated_ds.data_stats
        assert "sample_values" in updated_ds.data_stats

    @pytest.mark.asyncio
    async def test_profile_response_fields(
        self, client, db, tmp_dir, duckdb_mgr,
    ) -> None:
        """Profile response includes all expected fields."""
        ds = _create_dataset(db, tmp_dir, duckdb_mgr)

        response = await client.get(f"/api/v1/datasets/{ds.id}/profile")
        assert response.status_code == 200
        body = response.json()

        expected_fields = ["dataset_id", "summarize_results", "sample_values", "profiled_at"]
        for field in expected_fields:
            assert field in body, f"Missing field: {field}"

        # Check summarize_results has expected column stats
        first_col = body["summarize_results"][0]
        assert "column_name" in first_col
        assert "column_type" in first_col
