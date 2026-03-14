"""Tests for DuckDB view rehydration on startup.

Covers:
- Happy path: ready dataset with file on disk → view registered
- Missing file: ready dataset, no file → status set to error
- Non-ready datasets: uploading/processing/error statuses → skipped
- Registration failure: file exists but DuckDB can't read it → logged, no crash
- Empty database: no datasets → completes without error
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.main import _rehydrate_duckdb_views
from app.models.base import Base
from app.models.dataset import DatasetStatus
from app.models.orm import Dataset
from app.services.duckdb_manager import DuckDBManager


@pytest.fixture
def tmp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def db_engine(tmp_dir):
    """Create a SQLite engine backed by a temp file."""
    url = f"sqlite:///{tmp_dir / 'test.db'}"
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
def session_factory(db_engine) -> sessionmaker[Session]:
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
    mgr = DuckDBManager()
    yield mgr
    mgr.close()


def _insert_dataset(
    db: Session,
    *,
    file_path: str,
    table_name: str | None = None,
    file_format: str = "csv",
    status: str = DatasetStatus.READY,
) -> Dataset:
    """Insert a dataset row into the database."""
    if table_name is None:
        table_name = f"ds_test_{uuid.uuid4().hex[:6]}"
    ds = Dataset(
        name="test.csv",
        file_path=file_path,
        file_format=file_format,
        file_size_bytes=100,
        row_count=2,
        duckdb_table_name=table_name,
        status=status,
    )
    db.add(ds)
    db.commit()
    return ds


class TestRehydration:
    """Tests for _rehydrate_duckdb_views()."""

    def test_ready_dataset_with_file_is_registered(
        self, session_factory, db, duckdb_mgr, tmp_dir
    ) -> None:
        """A ready dataset whose file exists on disk gets its view re-created."""
        csv_path = tmp_dir / "data.csv"
        csv_path.write_text("id,name\n1,Alice\n2,Bob\n")
        table_name = "ds_data_rehydrate"

        _insert_dataset(
            db, file_path=str(csv_path), table_name=table_name
        )

        _rehydrate_duckdb_views(session_factory, duckdb_mgr)

        assert duckdb_mgr.is_table_registered(table_name)
        rows = duckdb_mgr.execute_query(f"SELECT COUNT(*) AS cnt FROM {table_name}")
        assert rows[0]["cnt"] == 2

    def test_missing_file_sets_status_to_error(
        self, session_factory, db, duckdb_mgr, tmp_dir
    ) -> None:
        """A ready dataset whose file is missing gets status set to error."""
        missing_path = str(tmp_dir / "gone.csv")
        table_name = "ds_gone"

        ds = _insert_dataset(
            db, file_path=missing_path, table_name=table_name
        )
        dataset_id = ds.id

        _rehydrate_duckdb_views(session_factory, duckdb_mgr)

        assert not duckdb_mgr.is_table_registered(table_name)

        # Reload from DB to check status was updated
        db.expire_all()
        refreshed = db.get(Dataset, dataset_id)
        assert refreshed is not None
        assert refreshed.status == DatasetStatus.ERROR

    def test_non_ready_datasets_are_skipped(
        self, session_factory, db, duckdb_mgr, tmp_dir
    ) -> None:
        """Datasets with uploading/processing/error status are not registered."""
        csv_path = tmp_dir / "skip.csv"
        csv_path.write_text("x\n1\n")

        for status in [DatasetStatus.UPLOADING, DatasetStatus.PROCESSING, DatasetStatus.ERROR]:
            _insert_dataset(
                db,
                file_path=str(csv_path),
                status=status,
            )

        _rehydrate_duckdb_views(session_factory, duckdb_mgr)

        assert duckdb_mgr.list_tables() == []

    def test_registration_failure_does_not_crash(
        self, session_factory, db, duckdb_mgr, tmp_dir
    ) -> None:
        """If file exists but DuckDB can't read it, rehydration continues."""
        bad_file = tmp_dir / "bad.csv"
        bad_file.write_bytes(b"\x00\x01\x02\x03")  # binary garbage

        # Also create a valid dataset to verify it still gets registered
        good_file = tmp_dir / "good.csv"
        good_file.write_text("a,b\n1,2\n")

        _insert_dataset(
            db,
            file_path=str(bad_file),
            table_name="ds_bad",
            file_format="parquet",  # mismatched format will cause DuckDB error
        )
        _insert_dataset(
            db,
            file_path=str(good_file),
            table_name="ds_good",
            file_format="csv",
        )

        _rehydrate_duckdb_views(session_factory, duckdb_mgr)

        # Good dataset should still be registered despite the bad one failing
        assert duckdb_mgr.is_table_registered("ds_good")

    def test_empty_database_completes(
        self, session_factory, duckdb_mgr
    ) -> None:
        """Rehydration with no datasets completes without error."""
        _rehydrate_duckdb_views(session_factory, duckdb_mgr)

        assert duckdb_mgr.list_tables() == []
