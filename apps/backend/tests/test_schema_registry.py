"""Tests for the unified schema registry API endpoint.

Covers:
- Functional: Returns all datasets with schemas, all connections with schemas,
  columns include name/type/nullable/PK/FK, sources ordered by name,
  empty sources included
- Edge Cases: No sources returns empty array, mixed sources all included,
  error state connections show cached schema
- Performance: Efficient response for many tables
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.encryption import encrypt_value
from app.main import create_app
from app.models.base import Base
from app.models.connection import ConnectionStatus
from app.models.dataset import DatasetStatus
from app.models.orm import Connection, Dataset, SchemaMetadata
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
        "DATAX_DUCKDB_PATH": ":memory:",
    }
    with patch.dict(os.environ, env, clear=True):
        return Settings()  # type: ignore[call-arg]


@pytest.fixture
def fernet_env():
    """Provide env with valid encryption key for encrypt_value calls."""
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    return patch.dict(os.environ, {"DATAX_ENCRYPTION_KEY": key}, clear=False)


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_dataset(
    db: Session,
    *,
    name: str = "Test Dataset",
    status: str = DatasetStatus.READY.value,
    table_name: str | None = None,
) -> Dataset:
    """Create a dataset record in the database."""
    tname = table_name or f"ds_{uuid.uuid4().hex[:8]}"
    dataset = Dataset(
        name=name,
        file_path="/tmp/fake.csv",
        file_format="csv",
        row_count=100,
        duckdb_table_name=tname,
        status=status,
    )
    db.add(dataset)
    db.flush()
    return dataset


def _add_schema_metadata(
    db: Session,
    source_id: uuid.UUID,
    source_type: str,
    table_name: str,
    columns: list[dict],
) -> None:
    """Add SchemaMetadata rows for a source."""
    for col in columns:
        row = SchemaMetadata(
            source_id=source_id,
            source_type=source_type,
            table_name=table_name,
            column_name=col["name"],
            data_type=col["type"],
            is_nullable=col.get("nullable", True),
            is_primary_key=col.get("is_primary_key", False),
            foreign_key_ref=col.get("foreign_key_ref"),
        )
        db.add(row)
    db.flush()


def _add_connection(
    db: Session,
    fernet_env,
    conn_id: uuid.UUID | None = None,
    name: str = "Test Connection",
    status: str = ConnectionStatus.CONNECTED.value,
) -> uuid.UUID:
    """Add a connection to the database."""
    cid = conn_id or uuid.uuid4()
    with fernet_env:
        encrypted_pw = encrypt_value("test_password")
    conn = Connection(
        id=cid,
        name=name,
        db_type="postgresql",
        host="localhost",
        port=5432,
        database_name="testdb",
        username="user",
        encrypted_password=encrypted_pw,
        status=status,
    )
    db.add(conn)
    db.flush()
    return cid


def _add_connection_schema(
    db: Session,
    conn_id: uuid.UUID,
    table_name: str,
    columns: list[dict],
) -> None:
    """Add schema metadata for a connection to the database."""
    _add_schema_metadata(db, conn_id, "connection", table_name, columns)


# ---------------------------------------------------------------------------
# Functional: Returns all datasets with schemas
# ---------------------------------------------------------------------------


class TestSchemaRegistryDatasets:
    """Test schema registry returns dataset sources correctly."""

    @pytest.mark.asyncio
    async def test_returns_dataset_with_schema(self, client, db) -> None:
        """Dataset with schema metadata appears in the response."""
        ds = _create_dataset(db, name="Sales Data", table_name="sales_q4")
        _add_schema_metadata(
            db,
            source_id=ds.id,
            source_type="dataset",
            table_name="sales_q4",
            columns=[
                {"name": "date", "type": "DATE", "nullable": False, "is_primary_key": True},
                {"name": "revenue", "type": "DOUBLE", "nullable": True},
            ],
        )
        db.commit()

        response = await client.get("/api/v1/schema")

        assert response.status_code == 200
        data = response.json()
        assert len(data["sources"]) == 1

        source = data["sources"][0]
        assert source["source_type"] == "dataset"
        assert source["source_name"] == "Sales Data"
        assert source["source_id"] == str(ds.id)
        assert len(source["tables"]) == 1

        table = source["tables"][0]
        assert table["table_name"] == "sales_q4"
        assert len(table["columns"]) == 2

    @pytest.mark.asyncio
    async def test_columns_include_all_fields(self, client, db) -> None:
        """Column entries include name, type, nullable, is_primary_key, and FK ref."""
        ds = _create_dataset(db, name="Orders", table_name="orders")
        _add_schema_metadata(
            db,
            source_id=ds.id,
            source_type="dataset",
            table_name="orders",
            columns=[
                {
                    "name": "id",
                    "type": "integer",
                    "nullable": False,
                    "is_primary_key": True,
                },
                {
                    "name": "customer_id",
                    "type": "integer",
                    "nullable": False,
                    "is_primary_key": False,
                    "foreign_key_ref": "customers.id",
                },
            ],
        )
        db.commit()

        response = await client.get("/api/v1/schema")
        data = response.json()
        cols = data["sources"][0]["tables"][0]["columns"]

        # Find the PK column
        pk_col = next(c for c in cols if c["name"] == "id")
        assert pk_col["type"] == "integer"
        assert pk_col["nullable"] is False
        assert pk_col["is_primary_key"] is True

        # Find the FK column
        fk_col = next(c for c in cols if c["name"] == "customer_id")
        assert fk_col["foreign_key_ref"] == "customers.id"
        assert fk_col["is_primary_key"] is False

    @pytest.mark.asyncio
    async def test_multiple_datasets_all_included(self, client, db) -> None:
        """Multiple datasets each appear as separate sources."""
        ds1 = _create_dataset(db, name="Alpha Dataset", table_name="alpha")
        ds2 = _create_dataset(db, name="Beta Dataset", table_name="beta")
        _add_schema_metadata(
            db,
            source_id=ds1.id,
            source_type="dataset",
            table_name="alpha",
            columns=[{"name": "col1", "type": "varchar"}],
        )
        _add_schema_metadata(
            db,
            source_id=ds2.id,
            source_type="dataset",
            table_name="beta",
            columns=[{"name": "col2", "type": "integer"}],
        )
        db.commit()

        response = await client.get("/api/v1/schema")
        data = response.json()
        assert len(data["sources"]) == 2

        names = [s["source_name"] for s in data["sources"]]
        assert "Alpha Dataset" in names
        assert "Beta Dataset" in names


# ---------------------------------------------------------------------------
# Functional: Returns all connections with schemas
# ---------------------------------------------------------------------------


class TestSchemaRegistryConnections:
    """Test schema registry returns connection sources correctly."""

    @pytest.mark.asyncio
    async def test_returns_connection_with_schema(self, client, db, fernet_env) -> None:
        """Connection with schema metadata appears in the response."""
        conn_id = _add_connection(db, fernet_env, name="Production DB")
        _add_connection_schema(
            db,
            conn_id,
            "users",
            [
                {"name": "id", "type": "integer", "nullable": False, "is_primary_key": True},
                {"name": "email", "type": "varchar", "nullable": False},
            ],
        )
        db.commit()

        response = await client.get("/api/v1/schema")

        assert response.status_code == 200
        data = response.json()
        assert len(data["sources"]) == 1

        source = data["sources"][0]
        assert source["source_type"] == "connection"
        assert source["source_name"] == "Production DB"
        assert len(source["tables"]) == 1

        table = source["tables"][0]
        assert table["table_name"] == "users"
        assert len(table["columns"]) == 2

    @pytest.mark.asyncio
    async def test_connection_with_multiple_tables(self, client, db, fernet_env) -> None:
        """Connection with multiple tables returns all tables grouped."""
        conn_id = _add_connection(db, fernet_env, name="Analytics DB")
        _add_connection_schema(
            db,
            conn_id,
            "events",
            [{"name": "id", "type": "bigint"}],
        )
        _add_connection_schema(
            db,
            conn_id,
            "sessions",
            [{"name": "session_id", "type": "uuid"}],
        )
        db.commit()

        response = await client.get("/api/v1/schema")
        data = response.json()

        source = data["sources"][0]
        assert len(source["tables"]) == 2
        table_names = [t["table_name"] for t in source["tables"]]
        assert "events" in table_names
        assert "sessions" in table_names


# ---------------------------------------------------------------------------
# Functional: Sources ordered by name
# ---------------------------------------------------------------------------


class TestSchemaRegistryOrdering:
    """Test sources are ordered by name."""

    @pytest.mark.asyncio
    async def test_sources_ordered_by_name(self, client, db, fernet_env) -> None:
        """Sources are returned sorted alphabetically by name."""
        _create_dataset(db, name="Zebra Data", table_name="zebra")
        _create_dataset(db, name="Alpha Data", table_name="alpha")
        _add_connection(db, fernet_env, name="Middle Connection")
        db.commit()

        response = await client.get("/api/v1/schema")
        data = response.json()

        names = [s["source_name"] for s in data["sources"]]
        assert names == sorted(names, key=str.lower)

    @pytest.mark.asyncio
    async def test_tables_sorted_by_name(self, client, db, fernet_env) -> None:
        """Tables within a source are sorted alphabetically."""
        conn_id = _add_connection(db, fernet_env, name="Test DB")
        _add_connection_schema(db, conn_id, "zebra_table", [{"name": "id", "type": "integer"}])
        _add_connection_schema(db, conn_id, "alpha_table", [{"name": "id", "type": "integer"}])
        _add_connection_schema(db, conn_id, "middle_table", [{"name": "id", "type": "integer"}])
        db.commit()

        response = await client.get("/api/v1/schema")
        data = response.json()

        table_names = [t["table_name"] for t in data["sources"][0]["tables"]]
        assert table_names == sorted(table_names)


# ---------------------------------------------------------------------------
# Functional: Empty sources included
# ---------------------------------------------------------------------------


class TestSchemaRegistryEmptySources:
    """Test that sources without schema metadata are included."""

    @pytest.mark.asyncio
    async def test_dataset_without_schema_included(self, client, db) -> None:
        """Dataset with no schema metadata appears with empty tables list."""
        _create_dataset(db, name="Empty Dataset", table_name="empty_ds")
        db.commit()

        response = await client.get("/api/v1/schema")
        data = response.json()

        assert len(data["sources"]) == 1
        source = data["sources"][0]
        assert source["source_name"] == "Empty Dataset"
        assert source["tables"] == []

    @pytest.mark.asyncio
    async def test_connection_without_schema_included(self, client, db, fernet_env) -> None:
        """Connection with no schema metadata appears with empty tables list."""
        _add_connection(db, fernet_env, name="No Tables Connection")
        db.commit()

        response = await client.get("/api/v1/schema")
        data = response.json()

        assert len(data["sources"]) == 1
        source = data["sources"][0]
        assert source["source_name"] == "No Tables Connection"
        assert source["tables"] == []


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestSchemaRegistryEdgeCases:
    """Edge case tests for the schema registry."""

    @pytest.mark.asyncio
    async def test_no_sources_returns_empty_array(self, client) -> None:
        """No datasets or connections returns empty sources array."""
        response = await client.get("/api/v1/schema")

        assert response.status_code == 200
        data = response.json()
        assert data["sources"] == []

    @pytest.mark.asyncio
    async def test_mixed_datasets_and_connections(self, client, db, fernet_env) -> None:
        """Both datasets and connections appear in the unified response."""
        ds = _create_dataset(db, name="CSV Upload", table_name="csv_data")
        _add_schema_metadata(
            db,
            source_id=ds.id,
            source_type="dataset",
            table_name="csv_data",
            columns=[{"name": "value", "type": "float"}],
        )

        conn_id = _add_connection(db, fernet_env, name="Live DB")
        _add_connection_schema(
            db,
            conn_id,
            "metrics",
            [{"name": "metric_name", "type": "varchar"}],
        )
        db.commit()

        response = await client.get("/api/v1/schema")
        data = response.json()

        assert len(data["sources"]) == 2
        types = {s["source_type"] for s in data["sources"]}
        assert types == {"dataset", "connection"}

    @pytest.mark.asyncio
    async def test_error_state_connection_shows_cached_schema(self, client, db, fernet_env) -> None:
        """Connection in error state still returns its cached schema metadata."""
        conn_id = _add_connection(db, fernet_env, name="Broken DB", status="error")
        _add_connection_schema(
            db,
            conn_id,
            "cached_table",
            [{"name": "id", "type": "integer", "nullable": False}],
        )
        db.commit()

        response = await client.get("/api/v1/schema")
        data = response.json()

        assert len(data["sources"]) == 1
        source = data["sources"][0]
        assert source["source_name"] == "Broken DB"
        assert len(source["tables"]) == 1
        assert source["tables"][0]["table_name"] == "cached_table"

    @pytest.mark.asyncio
    async def test_column_without_foreign_key_omits_field(self, client, db) -> None:
        """Columns without FK refs do not include the foreign_key_ref field."""
        ds = _create_dataset(db, name="No FK", table_name="nofk")
        _add_schema_metadata(
            db,
            source_id=ds.id,
            source_type="dataset",
            table_name="nofk",
            columns=[{"name": "value", "type": "integer"}],
        )
        db.commit()

        response = await client.get("/api/v1/schema")
        data = response.json()

        col = data["sources"][0]["tables"][0]["columns"][0]
        assert "foreign_key_ref" not in col

    @pytest.mark.asyncio
    async def test_column_with_foreign_key_includes_field(self, client, db) -> None:
        """Columns with FK refs include the foreign_key_ref field."""
        ds = _create_dataset(db, name="With FK", table_name="withfk")
        _add_schema_metadata(
            db,
            source_id=ds.id,
            source_type="dataset",
            table_name="withfk",
            columns=[
                {"name": "user_id", "type": "integer", "foreign_key_ref": "users.id"},
            ],
        )
        db.commit()

        response = await client.get("/api/v1/schema")
        data = response.json()

        col = data["sources"][0]["tables"][0]["columns"][0]
        assert col["foreign_key_ref"] == "users.id"


# ---------------------------------------------------------------------------
# Performance: Many tables respond efficiently
# ---------------------------------------------------------------------------


class TestSchemaRegistryPerformance:
    """Performance tests for the schema registry."""

    @pytest.mark.asyncio
    async def test_many_sources_and_columns(self, client, db) -> None:
        """50 datasets with 20 columns each returns successfully."""
        for i in range(50):
            ds = _create_dataset(
                db,
                name=f"Dataset {i:03d}",
                table_name=f"table_{i:03d}",
            )
            cols = [
                {"name": f"col_{j}", "type": "varchar"}
                for j in range(20)
            ]
            _add_schema_metadata(
                db,
                source_id=ds.id,
                source_type="dataset",
                table_name=f"table_{i:03d}",
                columns=cols,
            )
        db.commit()

        response = await client.get("/api/v1/schema")

        assert response.status_code == 200
        data = response.json()
        assert len(data["sources"]) == 50
        total_cols = sum(
            len(col)
            for s in data["sources"]
            for col in [t["columns"] for t in s["tables"]]
        )
        assert total_cols == 1000
