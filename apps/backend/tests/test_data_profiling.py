"""Tests for data profiling via DuckDB SUMMARIZE and sample value extraction.

Covers:
- Unit: SUMMARIZE output parsing for various column types
- Unit: Sample value extraction per column
- Unit: Wide table truncation at WIDE_TABLE_AI_LIMIT
- Unit: Empty table handling (zero rows)
- Unit: Columns with all NULL values
- Integration: Profile generation on CSV upload
- Integration: Profile storage in DataProfile model
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base
from app.models.orm import DataProfile, Dataset
from app.services.duckdb_manager import (
    WIDE_TABLE_AI_LIMIT,
    DuckDBManager,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def manager() -> DuckDBManager:
    """Create a fresh in-memory DuckDB manager for each test."""
    mgr = DuckDBManager()
    yield mgr
    mgr.close()


@pytest.fixture
def tmp_dir() -> Path:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def db_engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

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


def _write_csv(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _write_json(path: Path, data: list[dict]) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Unit Tests: SUMMARIZE output parsing
# ---------------------------------------------------------------------------


class TestSummarizeTable:
    """Test summarize_table() method for various column types."""

    def test_basic_csv_summarize(self, manager: DuckDBManager, tmp_dir: Path) -> None:
        """SUMMARIZE returns structured stats for a basic CSV."""
        csv_path = _write_csv(
            tmp_dir / "basic.csv",
            "id,name,score\n1,Alice,95.5\n2,Bob,87.3\n3,Carol,92.1\n",
        )
        result = manager.register_file(csv_path, "ds_basic", "csv")
        assert result.is_success

        stats = manager.summarize_table("ds_basic")

        assert len(stats) == 3
        col_names = [s["column_name"] for s in stats]
        assert "id" in col_names
        assert "name" in col_names
        assert "score" in col_names

    def test_summarize_includes_expected_fields(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """Each stat dict includes expected SUMMARIZE fields."""
        csv_path = _write_csv(
            tmp_dir / "fields.csv",
            "value\n10\n20\n30\n40\n50\n",
        )
        manager.register_file(csv_path, "ds_fields", "csv")
        stats = manager.summarize_table("ds_fields")

        assert len(stats) == 1
        stat = stats[0]
        assert stat["column_name"] == "value"

        # Check for expected SUMMARIZE output fields
        expected_keys = {
            "column_name",
            "column_type",
            "min",
            "max",
            "approx_unique",
            "avg",
            "std",
            "q25",
            "q50",
            "q75",
            "count",
            "null_percentage",
        }
        assert expected_keys.issubset(set(stat.keys()))

    def test_summarize_numeric_types(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """SUMMARIZE correctly reports stats for integer and float columns."""
        csv_path = _write_csv(
            tmp_dir / "numeric.csv",
            "int_col,float_col\n1,1.5\n2,2.5\n3,3.5\n4,4.5\n5,5.5\n",
        )
        manager.register_file(csv_path, "ds_numeric", "csv")
        stats = manager.summarize_table("ds_numeric")

        int_stat = next(s for s in stats if s["column_name"] == "int_col")
        float_stat = next(s for s in stats if s["column_name"] == "float_col")

        # min/max are strings from SUMMARIZE output
        assert int_stat["min"] is not None
        assert int_stat["max"] is not None
        assert float_stat["min"] is not None
        assert float_stat["max"] is not None
        assert int_stat["count"] is not None

    def test_summarize_varchar_type(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """SUMMARIZE handles VARCHAR columns (no avg/std for strings)."""
        csv_path = _write_csv(
            tmp_dir / "strings.csv",
            "city\nNew York\nLos Angeles\nChicago\n",
        )
        manager.register_file(csv_path, "ds_strings", "csv")
        stats = manager.summarize_table("ds_strings")

        assert len(stats) == 1
        stat = stats[0]
        assert stat["column_name"] == "city"
        assert stat["column_type"] is not None

    def test_summarize_nonexistent_table(self, manager: DuckDBManager) -> None:
        """SUMMARIZE on a non-existent table returns empty list."""
        stats = manager.summarize_table("ds_nonexistent")
        assert stats == []

    def test_summarize_returns_serializable_values(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """All values in SUMMARIZE results are JSON-serializable."""
        csv_path = _write_csv(
            tmp_dir / "serialize.csv",
            "a,b,c\n1,hello,3.14\n2,world,2.71\n",
        )
        manager.register_file(csv_path, "ds_serialize", "csv")
        stats = manager.summarize_table("ds_serialize")

        # Verify all values are JSON-serializable
        json_str = json.dumps(stats)
        assert json_str  # No serialization error


# ---------------------------------------------------------------------------
# Unit Tests: Sample value extraction
# ---------------------------------------------------------------------------


class TestGetSampleValues:
    """Test get_sample_values() method."""

    def test_basic_sample_values(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """Returns distinct sample values for each column."""
        csv_path = _write_csv(
            tmp_dir / "samples.csv",
            "city,revenue\nNYC,100\nLA,200\nNYC,150\nChicago,300\nLA,250\n",
        )
        manager.register_file(csv_path, "ds_samples", "csv")

        samples = manager.get_sample_values("ds_samples")

        assert "city" in samples
        assert "revenue" in samples
        # DISTINCT values, up to 5
        assert len(samples["city"]) <= 5
        assert len(samples["city"]) >= 1

    def test_respects_limit(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """Returns at most `limit` values per column."""
        rows = "\n".join(f"val{i}" for i in range(20))
        csv_path = _write_csv(
            tmp_dir / "many.csv",
            f"col\n{rows}\n",
        )
        manager.register_file(csv_path, "ds_many", "csv")

        samples = manager.get_sample_values("ds_many", limit=3)

        assert len(samples["col"]) <= 3

    def test_default_limit_is_5(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """Default limit returns at most 5 values."""
        rows = "\n".join(f"val{i}" for i in range(20))
        csv_path = _write_csv(
            tmp_dir / "default.csv",
            f"col\n{rows}\n",
        )
        manager.register_file(csv_path, "ds_default", "csv")

        samples = manager.get_sample_values("ds_default")

        assert len(samples["col"]) <= 5

    def test_nonexistent_table(self, manager: DuckDBManager) -> None:
        """Non-existent table returns empty dict."""
        samples = manager.get_sample_values("ds_nonexistent")
        assert samples == {}

    def test_sample_values_serializable(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """All sample values are JSON-serializable."""
        csv_path = _write_csv(
            tmp_dir / "serial.csv",
            "a,b\n1,hello\n2,world\n",
        )
        manager.register_file(csv_path, "ds_serial", "csv")

        samples = manager.get_sample_values("ds_serial")

        json_str = json.dumps(samples)
        assert json_str


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestProfilingEdgeCases:
    """Edge case tests for profiling methods."""

    def test_empty_table_summarize(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """SUMMARIZE on an empty table (headers only) returns stats with zero counts."""
        csv_path = _write_csv(
            tmp_dir / "empty.csv",
            "a,b,c\n",
        )
        result = manager.register_file(csv_path, "ds_empty", "csv")
        assert result.is_success
        assert result.row_count == 0

        stats = manager.summarize_table("ds_empty")

        # SUMMARIZE should still return column entries, but with zero or null stats
        assert len(stats) == 3
        for stat in stats:
            assert stat["column_name"] in {"a", "b", "c"}

    def test_empty_table_sample_values(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """Sample values on an empty table returns empty lists per column."""
        csv_path = _write_csv(
            tmp_dir / "empty_sv.csv",
            "x,y\n",
        )
        manager.register_file(csv_path, "ds_empty_sv", "csv")

        samples = manager.get_sample_values("ds_empty_sv")

        assert "x" in samples
        assert "y" in samples
        assert samples["x"] == []
        assert samples["y"] == []

    def test_all_null_column_summarize(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """SUMMARIZE handles columns where all values are NULL."""
        csv_path = _write_csv(
            tmp_dir / "nulls.csv",
            "id,nullable_col\n1,\n2,\n3,\n",
        )
        manager.register_file(csv_path, "ds_nulls", "csv")

        stats = manager.summarize_table("ds_nulls")

        # Should still have stats for both columns
        assert len(stats) == 2
        null_col = next(
            (s for s in stats if s["column_name"] == "nullable_col"), None
        )
        assert null_col is not None

    def test_all_null_column_sample_values(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """Sample values for an all-NULL column returns empty list."""
        csv_path = _write_csv(
            tmp_dir / "null_sv.csv",
            "id,nullable_col\n1,\n2,\n3,\n",
        )
        manager.register_file(csv_path, "ds_null_sv", "csv")

        samples = manager.get_sample_values("ds_null_sv")

        assert "nullable_col" in samples
        assert samples["nullable_col"] == []

    def test_wide_table_summarize_truncation(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """Tables with >WIDE_TABLE_AI_LIMIT columns are truncated in SUMMARIZE results."""
        # Create a CSV with more than WIDE_TABLE_AI_LIMIT columns
        num_cols = WIDE_TABLE_AI_LIMIT + 10
        headers = ",".join(f"col{i}" for i in range(num_cols))
        values = ",".join(str(i) for i in range(num_cols))
        csv_path = _write_csv(
            tmp_dir / "wide.csv",
            f"{headers}\n{values}\n",
        )
        manager.register_file(csv_path, "ds_wide_sum", "csv")

        stats = manager.summarize_table("ds_wide_sum")

        # Should be truncated to WIDE_TABLE_AI_LIMIT
        assert len(stats) == WIDE_TABLE_AI_LIMIT

    def test_wide_table_sample_values_truncation(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """Tables with >WIDE_TABLE_AI_LIMIT columns are truncated in sample values."""
        num_cols = WIDE_TABLE_AI_LIMIT + 5
        headers = ",".join(f"col{i}" for i in range(num_cols))
        values = ",".join(str(i) for i in range(num_cols))
        csv_path = _write_csv(
            tmp_dir / "wide_sv.csv",
            f"{headers}\n{values}\n",
        )
        manager.register_file(csv_path, "ds_wide_sv", "csv")

        samples = manager.get_sample_values("ds_wide_sv")

        assert len(samples) == WIDE_TABLE_AI_LIMIT


# ---------------------------------------------------------------------------
# Integration: Profile generation on CSV upload
# ---------------------------------------------------------------------------


class TestProfileOnUpload:
    """Integration test: profile generation triggered during DuckDB registration."""

    def test_summarize_after_register(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """After registering a CSV, SUMMARIZE returns valid stats."""
        csv_path = _write_csv(
            tmp_dir / "upload.csv",
            "product,price,qty\nWidget,9.99,100\nGadget,19.99,50\nDoohickey,4.99,200\n",
        )
        result = manager.register_file(csv_path, "ds_upload", "csv")
        assert result.is_success

        stats = manager.summarize_table("ds_upload")
        samples = manager.get_sample_values("ds_upload")

        # Stats for 3 columns
        assert len(stats) == 3
        col_names = {s["column_name"] for s in stats}
        assert col_names == {"product", "price", "qty"}

        # Sample values for 3 columns
        assert len(samples) == 3
        assert "product" in samples
        assert "Widget" in samples["product"] or len(samples["product"]) > 0

    def test_json_file_profiling(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """Profiling works for JSON files too."""
        json_path = _write_json(
            tmp_dir / "data.json",
            [
                {"city": "NYC", "pop": 8000000},
                {"city": "LA", "pop": 4000000},
                {"city": "Chicago", "pop": 2700000},
            ],
        )
        result = manager.register_file(json_path, "ds_json_prof", "json")
        assert result.is_success

        stats = manager.summarize_table("ds_json_prof")
        samples = manager.get_sample_values("ds_json_prof")

        assert len(stats) == 2
        assert "city" in samples
        assert "pop" in samples


# ---------------------------------------------------------------------------
# Integration: Profile storage in DataProfile model
# ---------------------------------------------------------------------------


class TestProfileStorage:
    """Integration: DataProfile model stores SUMMARIZE results and sample values."""

    def test_data_profile_creation(
        self, db: Session, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """DataProfile record stores SUMMARIZE results and sample values."""
        csv_path = _write_csv(
            tmp_dir / "store.csv",
            "x,y\n1,a\n2,b\n3,c\n",
        )
        result = manager.register_file(csv_path, "ds_store", "csv")
        assert result.is_success

        summarize_results = manager.summarize_table("ds_store")
        sample_values = manager.get_sample_values("ds_store")

        # Create dataset first (FK requirement)
        dataset = Dataset(
            name="store.csv",
            file_path=str(csv_path),
            file_format="csv",
            duckdb_table_name="ds_store",
            status="ready",
            row_count=3,
        )
        db.add(dataset)
        db.flush()

        # Create DataProfile
        profile = DataProfile(
            dataset_id=dataset.id,
            summarize_results=summarize_results,
            sample_values=sample_values,
        )
        db.add(profile)
        db.commit()

        # Verify storage
        loaded = db.execute(
            select(DataProfile).where(DataProfile.dataset_id == dataset.id)
        ).scalar_one()

        assert loaded.summarize_results is not None
        assert len(loaded.summarize_results) == 2
        assert loaded.sample_values is not None
        assert "x" in loaded.sample_values
        assert "y" in loaded.sample_values

    def test_dataset_data_stats_storage(
        self, db: Session, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """Dataset.data_stats JSONB stores combined profile data."""
        csv_path = _write_csv(
            tmp_dir / "stats.csv",
            "a,b\n10,hello\n20,world\n",
        )
        result = manager.register_file(csv_path, "ds_stats", "csv")
        assert result.is_success

        summarize_results = manager.summarize_table("ds_stats")
        sample_values = manager.get_sample_values("ds_stats")

        dataset = Dataset(
            name="stats.csv",
            file_path=str(csv_path),
            file_format="csv",
            duckdb_table_name="ds_stats",
            status="ready",
            row_count=2,
            data_stats={
                "summarize": summarize_results,
                "sample_values": sample_values,
            },
        )
        db.add(dataset)
        db.commit()

        loaded = db.execute(
            select(Dataset).where(Dataset.id == dataset.id)
        ).scalar_one()

        assert loaded.data_stats is not None
        assert "summarize" in loaded.data_stats
        assert "sample_values" in loaded.data_stats
        assert len(loaded.data_stats["summarize"]) == 2
        assert "a" in loaded.data_stats["sample_values"]

    def test_profile_relationship(
        self, db: Session, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """Dataset.profile relationship returns the associated DataProfile."""
        csv_path = _write_csv(
            tmp_dir / "rel.csv",
            "col1\n42\n",
        )
        result = manager.register_file(csv_path, "ds_rel", "csv")
        assert result.is_success

        dataset = Dataset(
            name="rel.csv",
            file_path=str(csv_path),
            file_format="csv",
            duckdb_table_name="ds_rel",
            status="ready",
            row_count=1,
        )
        db.add(dataset)
        db.flush()

        profile = DataProfile(
            dataset_id=dataset.id,
            summarize_results=manager.summarize_table("ds_rel"),
            sample_values=manager.get_sample_values("ds_rel"),
        )
        db.add(profile)
        db.commit()

        # Refresh and check relationship
        db.refresh(dataset)
        assert dataset.profile is not None
        assert dataset.profile.summarize_results is not None
        assert dataset.profile.sample_values is not None
