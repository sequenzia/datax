"""Tests for the schema context injection service.

Covers:
- Unit: build_schema_context with datasets, connections, mixed sources
- Unit: _quote_if_reserved for SQL reserved keywords
- Unit: inject_schema_into_prompt combines base prompt with schema
- Edge cases: no sources, large schema truncation, reserved keyword quoting
- Error handling: database query failure returns empty context
- Integration: build_agent_deps populates AgentDeps correctly
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base
from app.models.orm import Connection, Dataset, SchemaMetadata
from app.services.schema_context import (
    MAX_SCHEMA_TABLES,
    _quote_if_reserved,
    build_schema_context,
    inject_schema_into_prompt,
)

TEST_FERNET_KEY = Fernet.generate_key().decode()


def _test_env() -> dict[str, str]:
    """Return test environment with required settings."""
    return {
        "DATABASE_URL": "sqlite:///:memory:",
        "DATAX_ENCRYPTION_KEY": TEST_FERNET_KEY,
    }


@pytest.fixture
def db_path():
    """Create a temporary file for SQLite database."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d) / "test.db"


@pytest.fixture
def db_engine(db_path):
    """Create a SQLite engine with all tables."""
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
    """Create a database session for tests."""
    session = session_factory()
    yield session
    session.close()


def _create_dataset(session: Session, name: str, table_name: str) -> Dataset:
    """Helper: create a Dataset record."""
    ds = Dataset(
        name=name,
        file_path=f"/tmp/{table_name}.csv",
        file_format="csv",
        file_size_bytes=1024,
        duckdb_table_name=table_name,
        status="ready",
    )
    session.add(ds)
    session.flush()
    return ds


def _create_connection(session: Session, name: str) -> Connection:
    """Helper: create a Connection record."""
    conn = Connection(
        name=name,
        db_type="postgresql",
        host="localhost",
        port=5432,
        database_name="testdb",
        username="testuser",
        encrypted_password=b"encrypted",
        status="connected",
    )
    session.add(conn)
    session.flush()
    return conn


def _add_schema_column(
    session: Session,
    source_id: uuid.UUID,
    source_type: str,
    table_name: str,
    column_name: str,
    data_type: str = "varchar",
    is_nullable: bool = True,
    is_primary_key: bool = False,
    foreign_key_ref: str | None = None,
) -> SchemaMetadata:
    """Helper: add a SchemaMetadata row."""
    sm = SchemaMetadata(
        source_id=source_id,
        source_type=source_type,
        table_name=table_name,
        column_name=column_name,
        data_type=data_type,
        is_nullable=is_nullable,
        is_primary_key=is_primary_key,
        foreign_key_ref=foreign_key_ref,
    )
    session.add(sm)
    session.flush()
    return sm


# ---------------------------------------------------------------------------
# Unit: _quote_if_reserved
# ---------------------------------------------------------------------------


class TestQuoteIfReserved:
    """Test SQL reserved keyword quoting."""

    def test_reserved_keyword_is_quoted(self) -> None:
        """Reserved keywords get double-quoted."""
        assert _quote_if_reserved("select") == '"select"'
        assert _quote_if_reserved("SELECT") == '"SELECT"'
        assert _quote_if_reserved("Order") == '"Order"'

    def test_non_reserved_word_not_quoted(self) -> None:
        """Regular identifiers are returned unchanged."""
        assert _quote_if_reserved("users") == "users"
        assert _quote_if_reserved("customer_name") == "customer_name"
        assert _quote_if_reserved("sales_2024") == "sales_2024"

    def test_date_keyword_quoted(self) -> None:
        """Common collision keywords like 'date' and 'user' are quoted."""
        assert _quote_if_reserved("date") == '"date"'
        assert _quote_if_reserved("user") == '"user"'
        assert _quote_if_reserved("timestamp") == '"timestamp"'


# ---------------------------------------------------------------------------
# Unit: inject_schema_into_prompt
# ---------------------------------------------------------------------------


class TestInjectSchemaIntoPrompt:
    """Test system prompt + schema context combination."""

    def test_appends_schema_to_base_prompt(self) -> None:
        """Schema context is appended after the base prompt."""
        base = "You are a data analytics assistant."
        schema = "## Available Data Sources\n\nTable: users\n  - id (integer, PK)"
        result = inject_schema_into_prompt(base, schema)
        assert result.startswith(base)
        assert schema in result
        assert "\n\n" in result

    def test_empty_schema_returns_base_prompt(self) -> None:
        """Empty schema context returns the base prompt unchanged."""
        base = "You are a data analytics assistant."
        result = inject_schema_into_prompt(base, "")
        assert result == base

    def test_none_like_empty_returns_base(self) -> None:
        """Falsy schema context returns the base prompt unchanged."""
        base = "Base prompt."
        assert inject_schema_into_prompt(base, "") == base


# ---------------------------------------------------------------------------
# Unit: build_schema_context - no sources
# ---------------------------------------------------------------------------


class TestBuildSchemaContextEmpty:
    """Test build_schema_context when no data sources exist."""

    def test_no_sources_returns_upload_message(self, db: Session) -> None:
        """Empty database returns a message telling user to upload data."""
        result = build_schema_context(db)
        assert "upload" in result.context_text.lower()
        assert result.table_count == 0
        assert result.total_columns == 0
        assert result.error is None

    def test_no_sources_mentions_connect(self, db: Session) -> None:
        """Empty database message mentions connecting a database."""
        result = build_schema_context(db)
        assert "connect" in result.context_text.lower()


# ---------------------------------------------------------------------------
# Unit: build_schema_context - with datasets
# ---------------------------------------------------------------------------


class TestBuildSchemaContextDatasets:
    """Test build_schema_context with dataset sources."""

    def test_single_dataset_included(self, db: Session) -> None:
        """A single dataset's schema appears in the context."""
        ds = _create_dataset(db, "Sales Data", "ds_sales")
        _add_schema_column(db, ds.id, "dataset", "ds_sales", "id", "integer", False, True)
        _add_schema_column(db, ds.id, "dataset", "ds_sales", "amount", "decimal", True, False)
        db.commit()

        result = build_schema_context(db)
        assert result.table_count == 1
        assert result.total_columns == 2
        assert "Sales Data" in result.context_text
        assert "ds_sales" in result.context_text
        assert "id" in result.context_text
        assert "amount" in result.context_text
        assert "PK" in result.context_text
        assert "NOT NULL" in result.context_text

    def test_multiple_datasets(self, db: Session) -> None:
        """Multiple datasets are all listed."""
        ds1 = _create_dataset(db, "Users", "ds_users")
        _add_schema_column(db, ds1.id, "dataset", "ds_users", "id", "integer", False, True)
        _add_schema_column(db, ds1.id, "dataset", "ds_users", "name", "varchar", False, False)

        ds2 = _create_dataset(db, "Orders", "ds_orders")
        _add_schema_column(db, ds2.id, "dataset", "ds_orders", "id", "integer", False, True)
        _add_schema_column(db, ds2.id, "dataset", "ds_orders", "total", "decimal", True, False)
        db.commit()

        result = build_schema_context(db)
        assert result.table_count == 2
        assert result.total_columns == 4
        assert "Users" in result.context_text
        assert "Orders" in result.context_text


# ---------------------------------------------------------------------------
# Unit: build_schema_context - with connections
# ---------------------------------------------------------------------------


class TestBuildSchemaContextConnections:
    """Test build_schema_context with connection sources."""

    def test_connection_schema_included(self, db: Session) -> None:
        """Connection schema metadata appears in the context."""
        conn = _create_connection(db, "Production DB")
        _add_schema_column(db, conn.id, "connection", "customers", "id", "integer", False, True)
        _add_schema_column(db, conn.id, "connection", "customers", "email", "varchar", False, False)
        db.commit()

        result = build_schema_context(db)
        assert result.table_count == 1
        assert "Production DB" in result.context_text
        assert "Connection" in result.context_text
        assert "customers" in result.context_text

    def test_foreign_key_annotation(self, db: Session) -> None:
        """Foreign key references appear in the column annotation."""
        conn = _create_connection(db, "Main DB")
        _add_schema_column(db, conn.id, "connection", "orders", "id", "integer", False, True)
        _add_schema_column(
            db,
            conn.id,
            "connection",
            "orders",
            "customer_id",
            "integer",
            False,
            False,
            foreign_key_ref="customers.id",
        )
        db.commit()

        result = build_schema_context(db)
        assert "FK -> customers.id" in result.context_text


# ---------------------------------------------------------------------------
# Unit: build_schema_context - mixed sources
# ---------------------------------------------------------------------------


class TestBuildSchemaContextMixed:
    """Test build_schema_context with both datasets and connections."""

    def test_mixed_sources_both_shown(self, db: Session) -> None:
        """Both dataset and connection schemas appear in context."""
        ds = _create_dataset(db, "CSV Upload", "ds_csv_upload")
        _add_schema_column(db, ds.id, "dataset", "ds_csv_upload", "id", "integer", False, True)

        conn = _create_connection(db, "Staging DB")
        _add_schema_column(db, conn.id, "connection", "accounts", "id", "integer", False, True)
        db.commit()

        result = build_schema_context(db)
        assert result.table_count == 2
        assert "Dataset" in result.context_text
        assert "Connection" in result.context_text
        assert "CSV Upload" in result.context_text
        assert "Staging DB" in result.context_text

    def test_context_updates_on_new_upload(self, db: Session) -> None:
        """Adding a new dataset updates the schema context on next build."""
        ds1 = _create_dataset(db, "First Dataset", "ds_first")
        _add_schema_column(db, ds1.id, "dataset", "ds_first", "id", "integer", False, True)
        db.commit()

        result1 = build_schema_context(db)
        assert result1.table_count == 1
        assert "First Dataset" in result1.context_text

        # Simulate a new upload
        ds2 = _create_dataset(db, "Second Dataset", "ds_second")
        _add_schema_column(db, ds2.id, "dataset", "ds_second", "id", "integer", False, True)
        _add_schema_column(db, ds2.id, "dataset", "ds_second", "value", "float", True, False)
        db.commit()

        result2 = build_schema_context(db)
        assert result2.table_count == 2
        assert "Second Dataset" in result2.context_text
        assert "First Dataset" in result2.context_text


# ---------------------------------------------------------------------------
# Edge case: reserved keyword quoting in context
# ---------------------------------------------------------------------------


class TestReservedKeywordInContext:
    """Test that reserved SQL keywords in table/column names are quoted."""

    def test_reserved_column_name_quoted_in_output(self, db: Session) -> None:
        """Columns named with SQL reserved words are double-quoted."""
        ds = _create_dataset(db, "Time Series", "ds_timeseries")
        _add_schema_column(db, ds.id, "dataset", "ds_timeseries", "date", "date", False, False)
        _add_schema_column(db, ds.id, "dataset", "ds_timeseries", "value", "float", True, False)
        db.commit()

        result = build_schema_context(db)
        # "date" is a reserved keyword and should be quoted
        assert '"date"' in result.context_text
        # "value" is a reserved keyword too
        assert '"value"' in result.context_text


# ---------------------------------------------------------------------------
# Edge case: large schema truncation
# ---------------------------------------------------------------------------


class TestLargeSchematruncation:
    """Test schema truncation when too many tables exist."""

    def test_truncation_at_max_tables(self, db: Session) -> None:
        """Schemas with more than MAX_SCHEMA_TABLES tables are truncated."""
        conn = _create_connection(db, "Big DB")

        # Create MAX_SCHEMA_TABLES + 5 tables
        total_tables = MAX_SCHEMA_TABLES + 5
        for i in range(total_tables):
            _add_schema_column(
                db,
                conn.id,
                "connection",
                f"table_{i:04d}",
                "id",
                "integer",
                False,
                True,
            )
        db.commit()

        result = build_schema_context(db)
        assert result.truncated is True
        assert result.table_count == MAX_SCHEMA_TABLES
        assert "truncated" in result.context_text.lower()
        assert "5" in result.context_text  # 5 omitted tables

    def test_no_truncation_at_exact_max(self, db: Session) -> None:
        """Exactly MAX_SCHEMA_TABLES tables are not truncated."""
        conn = _create_connection(db, "Exact DB")

        for i in range(MAX_SCHEMA_TABLES):
            _add_schema_column(
                db,
                conn.id,
                "connection",
                f"table_{i:04d}",
                "id",
                "integer",
                False,
                True,
            )
        db.commit()

        result = build_schema_context(db)
        assert result.truncated is False
        assert result.table_count == MAX_SCHEMA_TABLES


# ---------------------------------------------------------------------------
# Error handling: database failure
# ---------------------------------------------------------------------------


class TestSchemaContextErrorHandling:
    """Test error handling when database queries fail."""

    def test_query_failure_returns_empty_context(self) -> None:
        """Database query failure returns empty context with error message."""
        mock_session = MagicMock(spec=Session)
        mock_session.execute.side_effect = Exception("Connection refused")

        result = build_schema_context(mock_session)
        assert result.context_text == ""
        assert result.error is not None
        assert "Connection refused" in result.error
        assert result.table_count == 0


# ---------------------------------------------------------------------------
# Integration: build_agent_deps
# ---------------------------------------------------------------------------


class TestBuildAgentDeps:
    """Test build_agent_deps constructs AgentDeps correctly."""

    def test_deps_with_schema(self, db: Session) -> None:
        """build_agent_deps populates schema_context and available_tables."""
        from app.services.agent_service import build_agent_deps

        ds = _create_dataset(db, "Test Data", "ds_test")
        _add_schema_column(db, ds.id, "dataset", "ds_test", "id", "integer", False, True)
        _add_schema_column(db, ds.id, "dataset", "ds_test", "name", "varchar", True, False)
        db.commit()

        deps = build_agent_deps(db)
        assert "ds_test" in deps.schema_context
        assert "ds_test" in deps.available_tables
        assert len(deps.available_tables) == 1

    def test_deps_with_no_sources(self, db: Session) -> None:
        """build_agent_deps with empty database has empty tables list."""
        from app.services.agent_service import build_agent_deps

        deps = build_agent_deps(db)
        assert "upload" in deps.schema_context.lower()
        assert deps.available_tables == []

    def test_deps_multiple_tables(self, db: Session) -> None:
        """build_agent_deps lists all available table names."""
        from app.services.agent_service import build_agent_deps

        ds = _create_dataset(db, "Users", "ds_users")
        _add_schema_column(db, ds.id, "dataset", "ds_users", "id", "integer", False, True)

        conn = _create_connection(db, "Prod")
        _add_schema_column(db, conn.id, "connection", "orders", "id", "integer", False, True)
        _add_schema_column(db, conn.id, "connection", "products", "id", "integer", False, True)
        db.commit()

        deps = build_agent_deps(db)
        assert len(deps.available_tables) == 3
        assert "ds_users" in deps.available_tables
        assert "orders" in deps.available_tables
        assert "products" in deps.available_tables


# ---------------------------------------------------------------------------
# Integration: create_agent with session
# ---------------------------------------------------------------------------


class TestCreateAgentWithSession:
    """Test create_agent integrates schema context when session is provided."""

    def test_agent_prompt_includes_schema(self, db: Session) -> None:
        """Agent system prompt includes schema context when session is passed."""
        from app.services.agent_service import create_agent
        from app.services.provider_service import _reset_store

        ds = _create_dataset(db, "Revenue", "ds_revenue")
        _add_schema_column(db, ds.id, "dataset", "ds_revenue", "amount", "decimal", True, False)
        db.commit()

        _reset_store()
        env = {
            "DATABASE_URL": "sqlite:///:memory:",
            "DATAX_ENCRYPTION_KEY": TEST_FERNET_KEY,
            "DATAX_OPENAI_API_KEY": "sk-test-key",
        }
        with patch.dict(os.environ, env, clear=True):
            agent = create_agent(session=db)
            # The instructions should contain the schema context
            assert agent._instructions is not None
            assert "ds_revenue" in agent._instructions
            assert "Revenue" in agent._instructions

    def test_agent_without_session_has_base_prompt_only(self) -> None:
        """Agent created without session has only the base analytics prompt."""
        from app.services.agent_service import ANALYTICS_SYSTEM_PROMPT, create_agent
        from app.services.provider_service import _reset_store

        _reset_store()
        env = {
            "DATABASE_URL": "sqlite:///:memory:",
            "DATAX_ENCRYPTION_KEY": TEST_FERNET_KEY,
            "DATAX_OPENAI_API_KEY": "sk-test-key",
        }
        with patch.dict(os.environ, env, clear=True):
            agent = create_agent()
            assert agent._instructions == ANALYTICS_SYSTEM_PROMPT
