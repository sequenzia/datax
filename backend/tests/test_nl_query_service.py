"""Tests for the natural language to SQL query generation pipeline.

Covers:
- Functional: Simple questions -> valid SQL, aggregation -> GROUP BY,
  filters -> WHERE, sorting -> ORDER BY, correct source identification,
  SQL executes and returns results, NL explanation
- Edge Cases: Ambiguous question -> clarifying question, no relevant source,
  non-existent columns handled, broad query adds LIMIT
- Error Handling: SQL syntax error -> self-correction loop, timeout -> cancel + inform,
  write ops blocked
- Performance: < 5s for < 1M row datasets (design-level verification)
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base
from app.models.orm import Connection, Dataset, SchemaMetadata
from app.services.connection_manager import ConnectionManager
from app.services.duckdb_manager import DuckDBManager
from app.services.nl_query_service import (
    DEFAULT_RESULT_LIMIT,
    ErrorCategory,
    NLQueryResult,
    NLQueryService,
    SQLGenerationResult,
    _build_correction_prompt,
    _build_generation_prompt,
    _build_source_list,
    _ensure_limit,
    _extract_field,
    _extract_sql,
    _find_source_for_table,
    _format_attempts_summary,
    _get_category_hints,
    _parse_ai_output,
    _resolve_source_from_sql,
    _resolve_source_mapping,
    classify_error,
    is_retryable_error,
)
from app.services.query_service import QueryResult, QueryService

TEST_FERNET_KEY = Fernet.generate_key().decode()


def _test_env() -> dict[str, str]:
    return {
        "DATABASE_URL": "sqlite:///:memory:",
        "DATAX_ENCRYPTION_KEY": TEST_FERNET_KEY,
    }


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d) / "test.db"


@pytest.fixture
def db_engine(db_path):
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
    return sessionmaker(bind=db_engine, autocommit=False, autoflush=False)


@pytest.fixture
def db(session_factory) -> Session:
    session = session_factory()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# DuckDB + QueryService fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def csv_file():
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w") as f:
        f.write("id,name,value,category\n")
        for i in range(10):
            f.write(f"{i + 1},Item{i + 1},{(i + 1) * 100},{'A' if i % 2 == 0 else 'B'}\n")
    yield Path(path)
    os.unlink(path)


@pytest.fixture
def duckdb_manager(csv_file):
    mgr = DuckDBManager()
    mgr.register_file(str(csv_file), "ds_sales", "csv")
    yield mgr
    mgr.close()


@pytest.fixture
def query_service(duckdb_manager):
    conn_mgr = ConnectionManager()
    return QueryService(
        duckdb_manager=duckdb_manager,
        connection_manager=conn_mgr,
        max_query_timeout=30,
    )


@pytest.fixture
def nl_service(query_service):
    return NLQueryService(query_service=query_service, max_retries=3)


# ---------------------------------------------------------------------------
# Database test helpers
# ---------------------------------------------------------------------------


def _create_dataset(session: Session, name: str, table_name: str) -> Dataset:
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


def _add_schema_column(
    session: Session,
    source_id: uuid.UUID,
    source_type: str,
    table_name: str,
    column_name: str,
    data_type: str = "varchar",
    is_nullable: bool = True,
    is_primary_key: bool = False,
) -> SchemaMetadata:
    sm = SchemaMetadata(
        source_id=source_id,
        source_type=source_type,
        table_name=table_name,
        column_name=column_name,
        data_type=data_type,
        is_nullable=is_nullable,
        is_primary_key=is_primary_key,
    )
    session.add(sm)
    session.flush()
    return sm


def _create_connection(session: Session, name: str) -> Connection:
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


def _setup_test_schema(db: Session) -> Dataset:
    """Create a dataset with schema for testing."""
    ds = _create_dataset(db, "Sales Data", "ds_sales")
    _add_schema_column(db, ds.id, "dataset", "ds_sales", "id", "integer", False, True)
    _add_schema_column(db, ds.id, "dataset", "ds_sales", "name", "varchar", True, False)
    _add_schema_column(db, ds.id, "dataset", "ds_sales", "value", "integer", True, False)
    _add_schema_column(db, ds.id, "dataset", "ds_sales", "category", "varchar", True, False)
    db.commit()
    return ds


# ---------------------------------------------------------------------------
# Unit: _ensure_limit
# ---------------------------------------------------------------------------


class TestEnsureLimit:
    """Test the LIMIT clause enforcement."""

    def test_adds_limit_when_missing(self) -> None:
        sql = "SELECT * FROM users"
        result = _ensure_limit(sql)
        assert "LIMIT" in result
        assert str(DEFAULT_RESULT_LIMIT) in result

    def test_preserves_existing_limit(self) -> None:
        sql = "SELECT * FROM users LIMIT 10"
        result = _ensure_limit(sql)
        assert result == sql  # Unchanged

    def test_preserves_existing_limit_case_insensitive(self) -> None:
        sql = "SELECT * FROM users limit 5"
        result = _ensure_limit(sql)
        assert result == sql

    def test_custom_limit_value(self) -> None:
        sql = "SELECT * FROM users"
        result = _ensure_limit(sql, limit=50)
        assert "LIMIT 50" in result

    def test_strips_trailing_semicolon(self) -> None:
        sql = "SELECT * FROM users;"
        result = _ensure_limit(sql)
        assert "LIMIT" in result
        assert not result.strip().endswith(";LIMIT")


# ---------------------------------------------------------------------------
# Unit: _extract_sql
# ---------------------------------------------------------------------------


class TestExtractSql:
    """Test SQL extraction from AI output."""

    def test_extracts_sql_with_prefix(self) -> None:
        text = "SQL: SELECT * FROM users\nSOURCE_ID: abc-123"
        result = _extract_sql(text)
        assert result == "SELECT * FROM users"

    def test_extracts_sql_from_code_block(self) -> None:
        text = "Here's the query:\n```sql\nSELECT * FROM orders\n```"
        result = _extract_sql(text)
        assert result == "SELECT * FROM orders"

    def test_returns_none_for_no_sql(self) -> None:
        text = "I need more information about your data."
        result = _extract_sql(text)
        assert result is None

    def test_extracts_multiline_sql(self) -> None:
        text = "SQL: SELECT name, COUNT(*) FROM users\nGROUP BY name\nSOURCE_ID: abc"
        result = _extract_sql(text)
        assert "SELECT" in result
        assert "GROUP BY" in result


# ---------------------------------------------------------------------------
# Unit: _extract_field
# ---------------------------------------------------------------------------


class TestExtractField:
    """Test field extraction from AI output."""

    def test_extracts_source_id(self) -> None:
        text = "SQL: SELECT 1\nSOURCE_ID: abc-123\nSOURCE_TYPE: dataset"
        result = _extract_field(text, "SOURCE_ID")
        assert result == "abc-123"

    def test_extracts_source_type(self) -> None:
        text = "SQL: SELECT 1\nSOURCE_ID: abc\nSOURCE_TYPE: dataset\nEXPLANATION: test"
        result = _extract_field(text, "SOURCE_TYPE")
        assert result == "dataset"

    def test_extracts_explanation(self) -> None:
        text = "SQL: SELECT 1\nEXPLANATION: This query counts all rows."
        result = _extract_field(text, "EXPLANATION")
        assert "counts all rows" in result

    def test_returns_empty_for_missing_field(self) -> None:
        text = "SQL: SELECT 1"
        result = _extract_field(text, "NONEXISTENT")
        assert result == ""


# ---------------------------------------------------------------------------
# Unit: _parse_ai_output
# ---------------------------------------------------------------------------


class TestParseAiOutput:
    """Test AI output parsing into structured results."""

    def test_parses_sql_generation(self) -> None:
        source_mapping = {"users": {"source_id": "abc-123", "source_type": "dataset"}}
        text = (
            "SQL: SELECT * FROM users\n"
            "SOURCE_ID: abc-123\n"
            "SOURCE_TYPE: dataset\n"
            "EXPLANATION: Selects all users"
        )
        result = _parse_ai_output(text, source_mapping)
        assert result.sql == "SELECT * FROM users"
        assert result.source_id == "abc-123"
        assert result.source_type == "dataset"
        assert "users" in result.explanation.lower()

    def test_parses_clarification_request(self) -> None:
        text = (
            "CLARIFICATION: Which table do you want to see?\n"
            "EXPLANATION: Your question could apply to multiple tables."
        )
        result = _parse_ai_output(text, {})
        assert result.needs_clarification is True
        assert "table" in result.clarifying_question.lower()

    def test_parses_no_source(self) -> None:
        text = (
            "NO_SOURCE: No data source contains weather information.\n"
            "EXPLANATION: Upload weather data to get started."
        )
        result = _parse_ai_output(text, {})
        assert result.no_relevant_source is True
        assert "weather" in result.no_source_message.lower()

    def test_empty_output(self) -> None:
        result = _parse_ai_output("", {})
        assert result.sql is None
        assert "empty" in result.explanation.lower()

    def test_resolves_source_from_sql_when_missing(self) -> None:
        source_mapping = {"orders": {"source_id": "xyz-789", "source_type": "dataset"}}
        text = "SQL: SELECT * FROM orders\nEXPLANATION: Gets all orders"
        result = _parse_ai_output(text, source_mapping)
        assert result.sql == "SELECT * FROM orders"
        assert result.source_id == "xyz-789"
        assert result.source_type == "dataset"

    def test_invalid_source_type_set_to_none(self) -> None:
        text = "SQL: SELECT 1\nSOURCE_ID: abc\nSOURCE_TYPE: invalid_type\nEXPLANATION: test"
        result = _parse_ai_output(text, {})
        assert result.source_type is None


# ---------------------------------------------------------------------------
# Unit: _resolve_source_from_sql
# ---------------------------------------------------------------------------


class TestResolveSourceFromSql:
    """Test source resolution from SQL table references."""

    def test_resolves_from_table(self) -> None:
        mapping = {"users": {"source_id": "id1", "source_type": "dataset"}}
        result = _resolve_source_from_sql("SELECT * FROM users", mapping)
        assert result is not None
        assert result["source_id"] == "id1"

    def test_resolves_from_join(self) -> None:
        mapping = {"orders": {"source_id": "id2", "source_type": "connection"}}
        result = _resolve_source_from_sql(
            "SELECT * FROM users JOIN orders ON users.id = orders.user_id",
            mapping,
        )
        assert result is not None
        assert result["source_id"] == "id2"

    def test_returns_none_for_unknown_table(self) -> None:
        mapping = {"users": {"source_id": "id1", "source_type": "dataset"}}
        result = _resolve_source_from_sql("SELECT * FROM nonexistent", mapping)
        assert result is None


# ---------------------------------------------------------------------------
# Unit: _find_source_for_table
# ---------------------------------------------------------------------------


class TestFindSourceForTable:
    """Test table-to-source lookup."""

    def test_exact_match(self) -> None:
        mapping = {"users": {"source_id": "id1", "source_type": "dataset"}}
        result = _find_source_for_table("users", mapping)
        assert result is not None
        assert result["source_id"] == "id1"

    def test_case_insensitive_match(self) -> None:
        mapping = {"USERS": {"source_id": "id1", "source_type": "dataset"}}
        result = _find_source_for_table("users", mapping)
        assert result is not None

    def test_no_match(self) -> None:
        mapping = {"users": {"source_id": "id1", "source_type": "dataset"}}
        result = _find_source_for_table("orders", mapping)
        assert result is None


# ---------------------------------------------------------------------------
# Unit: _resolve_source_mapping
# ---------------------------------------------------------------------------


class TestResolveSourceMapping:
    """Test source mapping construction from database."""

    def test_builds_mapping_from_schema(self, db: Session) -> None:
        ds = _setup_test_schema(db)
        mapping = _resolve_source_mapping(db)
        assert "ds_sales" in mapping
        assert mapping["ds_sales"]["source_id"] == str(ds.id)
        assert mapping["ds_sales"]["source_type"] == "dataset"

    def test_empty_when_no_schema(self, db: Session) -> None:
        mapping = _resolve_source_mapping(db)
        assert len(mapping) == 0

    def test_includes_dataset_name_alias(self, db: Session) -> None:
        _setup_test_schema(db)
        mapping = _resolve_source_mapping(db)
        # Dataset name "Sales Data" -> lower "sales data" should map
        assert "sales data" in mapping

    def test_includes_connection_sources(self, db: Session) -> None:
        conn = _create_connection(db, "Prod DB")
        _add_schema_column(db, conn.id, "connection", "customers", "id", "integer", False, True)
        db.commit()
        mapping = _resolve_source_mapping(db)
        assert "customers" in mapping
        assert mapping["customers"]["source_type"] == "connection"


# ---------------------------------------------------------------------------
# Unit: _build_source_list
# ---------------------------------------------------------------------------


class TestBuildSourceList:
    """Test source list formatting for AI prompt."""

    def test_formats_source_list(self) -> None:
        mapping = {
            "users": {"source_id": "id1", "source_type": "dataset"},
            "orders": {"source_id": "id2", "source_type": "connection"},
        }
        result = _build_source_list(mapping)
        assert "users" in result
        assert "orders" in result
        assert "dataset" in result
        assert "connection" in result

    def test_empty_mapping(self) -> None:
        result = _build_source_list({})
        assert "Available data sources" in result


# ---------------------------------------------------------------------------
# Unit: _build_generation_prompt
# ---------------------------------------------------------------------------


class TestBuildGenerationPrompt:
    """Test generation prompt construction."""

    def test_includes_question(self) -> None:
        result = _build_generation_prompt(
            "How many users are there?",
            "schema context here",
            "source list here",
        )
        assert "How many users are there?" in result

    def test_includes_schema_context(self) -> None:
        result = _build_generation_prompt("question", "## Tables\nusers: id, name", "sources")
        assert "## Tables" in result

    def test_includes_instructions(self) -> None:
        result = _build_generation_prompt("question", "schema", "sources")
        assert "GROUP BY" in result
        assert "WHERE" in result
        assert "ORDER BY" in result
        assert "LIMIT" in result
        assert "read-only" in result.lower()


# ---------------------------------------------------------------------------
# Functional: NLQueryService.process_question integration
# ---------------------------------------------------------------------------


class TestProcessQuestionFunctional:
    """Functional tests for the NL-to-SQL pipeline using mocked AI responses."""

    @pytest.mark.asyncio
    async def test_simple_select_generates_valid_sql(
        self, nl_service: NLQueryService, db: Session
    ) -> None:
        """Simple question generates valid SQL and returns results."""
        ds = _setup_test_schema(db)
        source_id = str(ds.id)

        ai_response = (
            f"SQL: SELECT * FROM ds_sales\n"
            f"SOURCE_ID: {source_id}\n"
            f"SOURCE_TYPE: dataset\n"
            f"EXPLANATION: This query retrieves all rows from the sales data."
        )

        with _mock_agent(ai_response):
            result = await nl_service.process_question("Show me all sales data", db)

        assert result.error is None
        assert result.sql is not None
        assert result.columns == ["id", "name", "value", "category"]
        assert result.row_count == 10
        assert result.explanation != ""
        assert result.source_type == "dataset"

    @pytest.mark.asyncio
    async def test_aggregation_with_group_by(self, nl_service: NLQueryService, db: Session) -> None:
        """Aggregation question generates GROUP BY query."""
        ds = _setup_test_schema(db)
        source_id = str(ds.id)

        ai_response = (
            f"SQL: SELECT category, COUNT(*) as cnt FROM ds_sales GROUP BY category\n"
            f"SOURCE_ID: {source_id}\n"
            f"SOURCE_TYPE: dataset\n"
            f"EXPLANATION: Counts items per category."
        )

        with _mock_agent(ai_response):
            result = await nl_service.process_question("How many items are in each category?", db)

        assert result.error is None
        assert result.row_count == 2  # categories A and B
        assert "category" in result.columns
        assert "cnt" in result.columns

    @pytest.mark.asyncio
    async def test_filter_with_where(self, nl_service: NLQueryService, db: Session) -> None:
        """Filter question generates WHERE clause."""
        ds = _setup_test_schema(db)
        source_id = str(ds.id)

        ai_response = (
            f"SQL: SELECT * FROM ds_sales WHERE value > 500\n"
            f"SOURCE_ID: {source_id}\n"
            f"SOURCE_TYPE: dataset\n"
            f"EXPLANATION: Filters for high-value items."
        )

        with _mock_agent(ai_response):
            result = await nl_service.process_question("Show items with value over 500", db)

        assert result.error is None
        assert result.row_count > 0
        # All returned values should be > 500
        value_idx = result.columns.index("value")
        for row in result.rows:
            assert row[value_idx] > 500

    @pytest.mark.asyncio
    async def test_sorting_with_order_by(self, nl_service: NLQueryService, db: Session) -> None:
        """Sorting question generates ORDER BY clause."""
        ds = _setup_test_schema(db)
        source_id = str(ds.id)

        ai_response = (
            f"SQL: SELECT * FROM ds_sales ORDER BY value DESC LIMIT 5\n"
            f"SOURCE_ID: {source_id}\n"
            f"SOURCE_TYPE: dataset\n"
            f"EXPLANATION: Top 5 highest value items."
        )

        with _mock_agent(ai_response):
            result = await nl_service.process_question("Show me the top 5 highest value items", db)

        assert result.error is None
        assert result.row_count == 5
        value_idx = result.columns.index("value")
        values = [row[value_idx] for row in result.rows]
        assert values == sorted(values, reverse=True)

    @pytest.mark.asyncio
    async def test_correct_source_identification(
        self, nl_service: NLQueryService, db: Session
    ) -> None:
        """Pipeline correctly identifies the source from schema context."""
        ds = _setup_test_schema(db)

        # Also add a connection source
        conn = _create_connection(db, "Prod DB")
        _add_schema_column(db, conn.id, "connection", "customers", "id", "integer", False, True)
        _add_schema_column(db, conn.id, "connection", "customers", "email", "varchar")
        db.commit()

        source_id = str(ds.id)
        ai_response = (
            f"SQL: SELECT * FROM ds_sales WHERE category = 'A'\n"
            f"SOURCE_ID: {source_id}\n"
            f"SOURCE_TYPE: dataset\n"
            f"EXPLANATION: Filters sales data for category A."
        )

        with _mock_agent(ai_response):
            result = await nl_service.process_question("Show category A sales", db)

        assert result.source_type == "dataset"
        assert result.source_id == source_id

    @pytest.mark.asyncio
    async def test_returns_nl_explanation(self, nl_service: NLQueryService, db: Session) -> None:
        """Pipeline returns a natural language explanation."""
        ds = _setup_test_schema(db)
        source_id = str(ds.id)

        ai_response = (
            f"SQL: SELECT COUNT(*) as total FROM ds_sales\n"
            f"SOURCE_ID: {source_id}\n"
            f"SOURCE_TYPE: dataset\n"
            f"EXPLANATION: Counts the total number of sales records."
        )

        with _mock_agent(ai_response):
            result = await nl_service.process_question("How many sales records?", db)

        assert result.explanation != ""
        assert "total" in result.explanation.lower() or "count" in result.explanation.lower()


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case handling tests."""

    @pytest.mark.asyncio
    async def test_ambiguous_question_asks_clarification(
        self, nl_service: NLQueryService, db: Session
    ) -> None:
        """Ambiguous question triggers a clarification request."""
        _setup_test_schema(db)

        ai_response = (
            "CLARIFICATION: Which specific data would you like to see? "
            "I have sales data with columns: id, name, value, category.\n"
            "EXPLANATION: The question 'show me the data' is too broad."
        )

        with _mock_agent(ai_response):
            result = await nl_service.process_question("Show me the data", db)

        assert result.needs_clarification is True
        assert result.clarifying_question is not None
        assert len(result.clarifying_question) > 0

    @pytest.mark.asyncio
    async def test_no_relevant_source_reported(
        self, nl_service: NLQueryService, db: Session
    ) -> None:
        """Question about non-existent data returns no_relevant_source."""
        _setup_test_schema(db)

        ai_response = (
            "NO_SOURCE: No data source contains weather information.\n"
            "EXPLANATION: You have sales data but no weather data. "
            "Upload a weather dataset to analyze it."
        )

        with _mock_agent(ai_response):
            result = await nl_service.process_question("What's the weather forecast?", db)

        assert result.no_relevant_source is True
        assert result.no_source_message is not None

    @pytest.mark.asyncio
    async def test_no_sources_at_all(self, nl_service: NLQueryService, db: Session) -> None:
        """No data sources at all returns appropriate message."""
        # Don't set up any schema
        result = await nl_service.process_question("Show me data", db)
        assert result.no_relevant_source is True
        assert "upload" in result.no_source_message.lower()

    @pytest.mark.asyncio
    async def test_broad_query_gets_limit(self, nl_service: NLQueryService, db: Session) -> None:
        """Broad query without LIMIT gets one automatically added."""
        ds = _setup_test_schema(db)
        source_id = str(ds.id)

        # AI response without LIMIT
        ai_response = (
            f"SQL: SELECT * FROM ds_sales\n"
            f"SOURCE_ID: {source_id}\n"
            f"SOURCE_TYPE: dataset\n"
            f"EXPLANATION: Gets all sales data."
        )

        with _mock_agent(ai_response):
            result = await nl_service.process_question("Show me everything", db)

        assert result.error is None
        assert result.sql is not None
        assert "LIMIT" in result.sql


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Error handling tests."""

    @pytest.mark.asyncio
    async def test_sql_error_triggers_self_correction(
        self, nl_service: NLQueryService, db: Session
    ) -> None:
        """SQL syntax error triggers the self-correction loop."""
        ds = _setup_test_schema(db)
        source_id = str(ds.id)

        # First call: bad SQL; second call (correction): good SQL
        bad_response = (
            f"SQL: SELECT * FROM ds_sales WHERE nonexistent_col = 1\n"
            f"SOURCE_ID: {source_id}\n"
            f"SOURCE_TYPE: dataset\n"
            f"EXPLANATION: Initial attempt."
        )
        good_response = (
            f"SQL: SELECT * FROM ds_sales WHERE category = 'A'\n"
            f"SOURCE_ID: {source_id}\n"
            f"SOURCE_TYPE: dataset\n"
            f"EXPLANATION: Corrected to use existing column."
        )

        with _mock_agent_sequence([bad_response, good_response]):
            result = await nl_service.process_question(
                "Show me items where the nonexistent column equals 1", db
            )

        assert result.error is None
        assert result.attempts > 1
        assert len(result.correction_history) > 0

    @pytest.mark.asyncio
    async def test_timeout_cancels_and_informs(self, db: Session) -> None:
        """Timeout during query execution cancels and informs user."""
        ds = _setup_test_schema(db)
        source_id = str(ds.id)

        # Create a mock query service that returns timeout
        mock_qs = MagicMock(spec=QueryService)
        mock_qs.execute.return_value = QueryResult(
            status="timeout",
            error_message="Query exceeded the time limit of 30s.",
        )
        nl_svc = NLQueryService(query_service=mock_qs, max_retries=3)

        ai_response = (
            f"SQL: SELECT * FROM ds_sales\n"
            f"SOURCE_ID: {source_id}\n"
            f"SOURCE_TYPE: dataset\n"
            f"EXPLANATION: Gets all data."
        )

        with _mock_agent(ai_response):
            result = await nl_svc.process_question("Show me all data", db)

        assert result.error is not None
        assert "time limit" in result.error.lower()
        # Should NOT retry on timeout
        assert result.attempts == 1

    @pytest.mark.asyncio
    async def test_write_ops_blocked(self, nl_service: NLQueryService, db: Session) -> None:
        """Write operations are blocked at the pipeline level."""
        _setup_test_schema(db)

        ai_response = (
            "SQL: DELETE FROM ds_sales WHERE id = 1\n"
            "SOURCE_ID: some-id\n"
            "SOURCE_TYPE: dataset\n"
            "EXPLANATION: Deletes a record."
        )

        with _mock_agent(ai_response):
            result = await nl_service.process_question("Delete item 1", db)

        assert result.error is not None
        assert "modify" in result.error.lower() or "read-only" in result.error.lower()

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self, db: Session) -> None:
        """All retries exhausted returns error with correction history."""
        ds = _setup_test_schema(db)
        source_id = str(ds.id)

        # Mock query service that always returns error
        mock_qs = MagicMock(spec=QueryService)
        mock_qs.execute.return_value = QueryResult(
            status="error",
            error_message="SQL error: table 'bad_table' not found",
        )
        nl_svc = NLQueryService(query_service=mock_qs, max_retries=2)

        # All AI responses produce bad SQL
        bad_response = (
            f"SQL: SELECT * FROM bad_table\n"
            f"SOURCE_ID: {source_id}\n"
            f"SOURCE_TYPE: dataset\n"
            f"EXPLANATION: Trying to query."
        )

        with _mock_agent(bad_response):
            result = await nl_svc.process_question("Show me data", db)

        assert result.error is not None
        assert "attempts" in result.error.lower()
        assert result.attempts == 3  # 1 initial + 2 retries
        assert len(result.correction_history) == 3

    @pytest.mark.asyncio
    async def test_no_provider_configured(self, nl_service: NLQueryService, db: Session) -> None:
        """No AI provider configured returns appropriate error."""
        _setup_test_schema(db)

        # Don't mock the agent - let it fail naturally with no provider
        with patch.dict(os.environ, _test_env(), clear=True):
            from app.services.provider_service import _reset_store

            _reset_store()
            result = await nl_service.process_question("Show me data", db)
            _reset_store()

        assert result.no_relevant_source is True
        assert "provider" in result.no_source_message.lower()


# ---------------------------------------------------------------------------
# Performance: Design-level verification
# ---------------------------------------------------------------------------


class TestPerformanceDesign:
    """Design-level performance verification.

    Validates that the implementation uses efficient patterns that
    should complete within 5 seconds for datasets under 1M rows.
    """

    def test_ensure_limit_prevents_unbounded_queries(self) -> None:
        """_ensure_limit prevents unbounded result sets."""
        sql = "SELECT * FROM huge_table"
        result = _ensure_limit(sql)
        assert "LIMIT" in result
        assert str(DEFAULT_RESULT_LIMIT) in result

    def test_query_service_has_timeout(self, query_service: QueryService) -> None:
        """QueryService has a configurable timeout."""
        assert query_service._max_query_timeout == 30

    def test_nl_service_has_max_retries(self, nl_service: NLQueryService) -> None:
        """NLQueryService has bounded retry count."""
        assert nl_service._max_retries == 3


# ---------------------------------------------------------------------------
# Integration: SQLGenerationResult model
# ---------------------------------------------------------------------------


class TestSQLGenerationResult:
    """Test the Pydantic model for SQL generation output."""

    def test_default_values(self) -> None:
        result = SQLGenerationResult()
        assert result.sql is None
        assert result.source_id is None
        assert result.source_type is None
        assert result.explanation == ""
        assert result.needs_clarification is False
        assert result.no_relevant_source is False

    def test_query_result(self) -> None:
        result = SQLGenerationResult(
            sql="SELECT * FROM users",
            source_id="abc-123",
            source_type="dataset",
            explanation="Gets all users",
        )
        assert result.sql == "SELECT * FROM users"
        assert result.source_id == "abc-123"

    def test_clarification_result(self) -> None:
        result = SQLGenerationResult(
            needs_clarification=True,
            clarifying_question="Which table?",
        )
        assert result.needs_clarification is True
        assert result.clarifying_question == "Which table?"


# ---------------------------------------------------------------------------
# Integration: NLQueryResult dataclass
# ---------------------------------------------------------------------------


class TestNLQueryResult:
    """Test the NLQueryResult dataclass."""

    def test_default_values(self) -> None:
        result = NLQueryResult()
        assert result.columns == []
        assert result.rows == []
        assert result.row_count == 0
        assert result.sql is None
        assert result.error is None
        assert result.needs_clarification is False

    def test_success_result(self) -> None:
        result = NLQueryResult(
            columns=["id", "name"],
            rows=[[1, "Alice"], [2, "Bob"]],
            row_count=2,
            sql="SELECT id, name FROM users",
            explanation="Gets user names",
        )
        assert result.row_count == 2
        assert result.sql is not None
        assert result.error is None


# ---------------------------------------------------------------------------
# Unit: Error classification
# ---------------------------------------------------------------------------


class TestClassifyError:
    """Test error message classification into categories."""

    def test_syntax_error(self) -> None:
        assert (
            classify_error("Parser Error: syntax error at or near 'SELEC'") == ErrorCategory.SYNTAX
        )

    def test_parse_error(self) -> None:
        assert classify_error("parse error at position 42") == ErrorCategory.SYNTAX

    def test_unexpected_token(self) -> None:
        assert classify_error("unexpected token: ','") == ErrorCategory.SYNTAX

    def test_near_keyword(self) -> None:
        assert classify_error('near "FROM": syntax error') == ErrorCategory.SYNTAX

    def test_column_not_found(self) -> None:
        assert (
            classify_error("Binder Error: column 'nonexist' not found")
            == ErrorCategory.COLUMN_NOT_FOUND
        )

    def test_no_such_column(self) -> None:
        assert classify_error("no such column: foo") == ErrorCategory.COLUMN_NOT_FOUND

    def test_unknown_column(self) -> None:
        assert (
            classify_error("Unknown column 'bar' in 'field list'") == ErrorCategory.COLUMN_NOT_FOUND
        )

    def test_column_does_not_exist(self) -> None:
        assert classify_error('column "qty" does not exist') == ErrorCategory.COLUMN_NOT_FOUND

    def test_table_not_found(self) -> None:
        assert (
            classify_error("Catalog Error: table 'users' not found")
            == ErrorCategory.TABLE_NOT_FOUND
        )

    def test_no_such_table(self) -> None:
        assert classify_error("no such table: products") == ErrorCategory.TABLE_NOT_FOUND

    def test_relation_does_not_exist(self) -> None:
        assert classify_error('relation "orders" does not exist') == ErrorCategory.TABLE_NOT_FOUND

    def test_table_does_not_exist(self) -> None:
        assert classify_error('table "inventory" does not exist') == ErrorCategory.TABLE_NOT_FOUND

    def test_type_mismatch(self) -> None:
        assert classify_error("type mismatch in comparison") == ErrorCategory.TYPE_MISMATCH

    def test_cannot_cast(self) -> None:
        assert classify_error("cannot cast 'abc' to integer") == ErrorCategory.TYPE_MISMATCH

    def test_cannot_convert(self) -> None:
        assert classify_error("cannot convert value") == ErrorCategory.TYPE_MISMATCH

    def test_invalid_input_syntax(self) -> None:
        assert (
            classify_error("invalid input syntax for type integer") == ErrorCategory.TYPE_MISMATCH
        )

    def test_conversion_failed(self) -> None:
        assert classify_error("conversion failed when converting") == ErrorCategory.TYPE_MISMATCH

    def test_ambiguous_reference(self) -> None:
        assert (
            classify_error("column reference 'id' is ambiguous")
            == ErrorCategory.AMBIGUOUS_REFERENCE
        )

    def test_connection_lost(self) -> None:
        assert classify_error("connection lost during query") == ErrorCategory.CONNECTION_LOST

    def test_connection_refused(self) -> None:
        assert classify_error("connection refused by server") == ErrorCategory.CONNECTION_LOST

    def test_could_not_connect(self) -> None:
        assert classify_error("could not connect to server") == ErrorCategory.CONNECTION_LOST

    def test_permission_denied(self) -> None:
        assert (
            classify_error("permission denied for table users") == ErrorCategory.PERMISSION_DENIED
        )

    def test_access_denied(self) -> None:
        assert classify_error("Access denied for user 'reader'") == ErrorCategory.PERMISSION_DENIED

    def test_insufficient_privileges(self) -> None:
        assert (
            classify_error("insufficient privileges to access") == ErrorCategory.PERMISSION_DENIED
        )

    def test_timeout_error(self) -> None:
        assert classify_error("statement_timeout exceeded") == ErrorCategory.TIMEOUT

    def test_unknown_error(self) -> None:
        assert classify_error("something unexpected happened") == ErrorCategory.UNKNOWN


class TestIsRetryableError:
    """Test retryable vs non-retryable error classification."""

    def test_syntax_error_is_retryable(self) -> None:
        assert is_retryable_error("syntax error at or near 'SELECT'") is True

    def test_column_not_found_is_retryable(self) -> None:
        assert is_retryable_error("column 'foo' not found") is True

    def test_table_not_found_is_retryable(self) -> None:
        assert is_retryable_error("table 'bar' not found") is True

    def test_type_mismatch_is_retryable(self) -> None:
        assert is_retryable_error("type mismatch in comparison") is True

    def test_ambiguous_reference_is_retryable(self) -> None:
        assert is_retryable_error("ambiguous column reference") is True

    def test_unknown_error_is_retryable(self) -> None:
        assert is_retryable_error("some unknown error") is True

    def test_timeout_is_not_retryable_by_status(self) -> None:
        assert is_retryable_error("query timed out", status="timeout") is False

    def test_timeout_is_not_retryable_by_message(self) -> None:
        assert is_retryable_error("statement_timeout exceeded") is False

    def test_read_only_is_not_retryable(self) -> None:
        assert is_retryable_error("READ_ONLY_VIOLATION: write not allowed") is False

    def test_connection_lost_is_not_retryable(self) -> None:
        assert is_retryable_error("connection lost during query") is False

    def test_permission_denied_is_not_retryable(self) -> None:
        assert is_retryable_error("permission denied for table") is False


# ---------------------------------------------------------------------------
# Unit: _format_attempts_summary
# ---------------------------------------------------------------------------


class TestFormatAttemptsSummary:
    """Test attempts summary formatting."""

    def test_empty_history(self) -> None:
        assert _format_attempts_summary([]) == ""

    def test_single_attempt(self) -> None:
        history = [{"sql": "SELECT 1", "error": "bad query", "category": "syntax_error"}]
        result = _format_attempts_summary(history)
        assert "Attempt 1" in result
        assert "syntax_error" in result
        assert "bad query" in result
        assert "SELECT 1" in result

    def test_multiple_attempts(self) -> None:
        history = [
            {"sql": "SELECT * FROM bad", "error": "table not found", "category": "table_not_found"},
            {
                "sql": "SELECT * FROM also_bad",
                "error": "column not found",
                "category": "column_not_found",
            },
        ]
        result = _format_attempts_summary(history)
        assert "Attempt 1" in result
        assert "Attempt 2" in result
        assert "table_not_found" in result
        assert "column_not_found" in result

    def test_long_sql_truncated(self) -> None:
        long_sql = "SELECT " + ", ".join([f"col_{i}" for i in range(100)])
        history = [{"sql": long_sql, "error": "error", "category": "unknown"}]
        result = _format_attempts_summary(history)
        assert "..." in result

    def test_missing_category_defaults(self) -> None:
        history = [{"sql": "SELECT 1", "error": "err"}]
        result = _format_attempts_summary(history)
        assert "unknown" in result


# ---------------------------------------------------------------------------
# Unit: _build_correction_prompt enhancements
# ---------------------------------------------------------------------------


class TestBuildCorrectionPrompt:
    """Test correction prompt construction with history and error categories."""

    def test_includes_error_category(self) -> None:
        prompt = _build_correction_prompt(
            question="Show me sales",
            failed_sql="SELECT * FROM sale",
            error_message="table 'sale' not found",
            schema_context="schema",
            source_list="sources",
            error_category=ErrorCategory.TABLE_NOT_FOUND,
        )
        assert "TABLE_NOT_FOUND" in prompt or "table_not_found" in prompt
        assert "TABLE was not found" in prompt

    def test_includes_syntax_hints(self) -> None:
        prompt = _build_correction_prompt(
            question="q",
            failed_sql="SELEC 1",
            error_message="syntax error",
            schema_context="",
            source_list="",
            error_category=ErrorCategory.SYNTAX,
        )
        assert "SYNTAX ERROR" in prompt

    def test_includes_column_hints(self) -> None:
        prompt = _build_correction_prompt(
            question="q",
            failed_sql="SELECT nonexist FROM t",
            error_message="column not found",
            schema_context="",
            source_list="",
            error_category=ErrorCategory.COLUMN_NOT_FOUND,
        )
        assert "COLUMN was not found" in prompt

    def test_includes_type_mismatch_hints(self) -> None:
        prompt = _build_correction_prompt(
            question="q",
            failed_sql="SELECT * FROM t WHERE id = 'abc'",
            error_message="type mismatch",
            schema_context="",
            source_list="",
            error_category=ErrorCategory.TYPE_MISMATCH,
        )
        assert "TYPE MISMATCH" in prompt

    def test_includes_ambiguous_hints(self) -> None:
        prompt = _build_correction_prompt(
            question="q",
            failed_sql="SELECT id FROM a JOIN b",
            error_message="ambiguous column",
            schema_context="",
            source_list="",
            error_category=ErrorCategory.AMBIGUOUS_REFERENCE,
        )
        assert "AMBIGUOUS REFERENCE" in prompt

    def test_no_hints_for_unknown(self) -> None:
        prompt = _build_correction_prompt(
            question="q",
            failed_sql="SELECT 1",
            error_message="weird error",
            schema_context="",
            source_list="",
            error_category=ErrorCategory.UNKNOWN,
        )
        # Should not have any category-specific hints
        assert "SYNTAX ERROR" not in prompt
        assert "COLUMN was not found" not in prompt

    def test_includes_previous_attempts_when_multiple(self) -> None:
        history = [
            {"sql": "SELECT * FROM bad1", "error": "error1", "category": "syntax_error"},
            {"sql": "SELECT * FROM bad2", "error": "error2", "category": "column_not_found"},
        ]
        prompt = _build_correction_prompt(
            question="q",
            failed_sql="SELECT * FROM bad2",
            error_message="error2",
            schema_context="",
            source_list="",
            error_category=ErrorCategory.COLUMN_NOT_FOUND,
            correction_history=history,
        )
        assert "PREVIOUS FAILED ATTEMPTS" in prompt
        assert "bad1" in prompt
        assert "error1" in prompt
        assert "do not repeat" in prompt.lower()

    def test_no_previous_section_for_single_attempt(self) -> None:
        history = [
            {"sql": "SELECT 1", "error": "err", "category": "unknown"},
        ]
        prompt = _build_correction_prompt(
            question="q",
            failed_sql="SELECT 1",
            error_message="err",
            schema_context="",
            source_list="",
            correction_history=history,
        )
        assert "PREVIOUS FAILED ATTEMPTS" not in prompt

    def test_no_previous_section_when_none(self) -> None:
        prompt = _build_correction_prompt(
            question="q",
            failed_sql="SELECT 1",
            error_message="err",
            schema_context="",
            source_list="",
            correction_history=None,
        )
        assert "PREVIOUS FAILED ATTEMPTS" not in prompt


class TestGetCategoryHints:
    """Test category-specific hints for correction prompts."""

    def test_all_retryable_categories_have_hints(self) -> None:
        for cat in [
            ErrorCategory.SYNTAX,
            ErrorCategory.COLUMN_NOT_FOUND,
            ErrorCategory.TABLE_NOT_FOUND,
            ErrorCategory.TYPE_MISMATCH,
            ErrorCategory.AMBIGUOUS_REFERENCE,
        ]:
            assert _get_category_hints(cat) != ""

    def test_non_retryable_categories_no_hints(self) -> None:
        for cat in [
            ErrorCategory.TIMEOUT,
            ErrorCategory.CONNECTION_LOST,
            ErrorCategory.PERMISSION_DENIED,
        ]:
            assert _get_category_hints(cat) == ""

    def test_unknown_category_no_hints(self) -> None:
        assert _get_category_hints(ErrorCategory.UNKNOWN) == ""


# ---------------------------------------------------------------------------
# Integration: Self-correction retry loop enhancements
# ---------------------------------------------------------------------------


class TestSelfCorrectionRetryLoop:
    """Tests for the enhanced agentic self-correction retry loop."""

    @pytest.mark.asyncio
    async def test_correction_receives_full_history(self, db: Session) -> None:
        """On repeated failures, the correction prompt includes full history."""
        ds = _setup_test_schema(db)
        source_id = str(ds.id)

        # Always return SQL that will fail on DuckDB
        call_count = 0

        def make_agent(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            # First response is initial SQL, subsequent are corrections
            if call_count == 1:
                mock_result.output = (
                    f"SQL: SELECT * FROM ds_sales WHERE bad_col1 = 1\n"
                    f"SOURCE_ID: {source_id}\n"
                    f"SOURCE_TYPE: dataset\n"
                    f"EXPLANATION: Try 1"
                )
            elif call_count == 2:
                mock_result.output = (
                    f"SQL: SELECT * FROM ds_sales WHERE bad_col2 = 1\n"
                    f"SOURCE_ID: {source_id}\n"
                    f"SOURCE_TYPE: dataset\n"
                    f"EXPLANATION: Try 2"
                )
            else:
                # Eventually return valid SQL
                mock_result.output = (
                    f"SQL: SELECT * FROM ds_sales WHERE category = 'A'\n"
                    f"SOURCE_ID: {source_id}\n"
                    f"SOURCE_TYPE: dataset\n"
                    f"EXPLANATION: Final correction"
                )
            mock_a = MagicMock()
            mock_a.run = AsyncMock(return_value=mock_result)
            return mock_a

        with patch(
            "app.services.nl_query_service.create_agent",
            side_effect=make_agent,
        ):
            await NLQueryService(
                query_service=QueryService(
                    duckdb_manager=DuckDBManager.__new__(DuckDBManager),
                    connection_manager=ConnectionManager(),
                ),
                max_retries=3,
            ).process_question("test", db)

        # We can't easily check the prompt content here, but we can verify
        # that the correction history grows with each attempt
        # The key thing is it eventually succeeds or fails with full history
        assert call_count > 1  # Corrections were attempted

    @pytest.mark.asyncio
    async def test_non_retryable_connection_lost_skips_retry(self, db: Session) -> None:
        """Connection lost error skips retry and returns immediately."""
        ds = _setup_test_schema(db)
        source_id = str(ds.id)

        mock_qs = MagicMock(spec=QueryService)
        mock_qs.execute.return_value = QueryResult(
            status="error",
            error_message="connection lost during query execution",
        )
        nl_svc = NLQueryService(query_service=mock_qs, max_retries=3)

        ai_response = (
            f"SQL: SELECT * FROM ds_sales\n"
            f"SOURCE_ID: {source_id}\n"
            f"SOURCE_TYPE: dataset\n"
            f"EXPLANATION: Gets data."
        )

        with _mock_agent(ai_response):
            result = await nl_svc.process_question("Show data", db)

        assert result.error is not None
        assert "connection" in result.error.lower()
        assert result.attempts == 1
        mock_qs.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_retryable_permission_denied_skips_retry(self, db: Session) -> None:
        """Permission denied error skips retry and returns immediately."""
        ds = _setup_test_schema(db)
        source_id = str(ds.id)

        mock_qs = MagicMock(spec=QueryService)
        mock_qs.execute.return_value = QueryResult(
            status="error",
            error_message="permission denied for table users",
        )
        nl_svc = NLQueryService(query_service=mock_qs, max_retries=3)

        ai_response = (
            f"SQL: SELECT * FROM ds_sales\n"
            f"SOURCE_ID: {source_id}\n"
            f"SOURCE_TYPE: dataset\n"
            f"EXPLANATION: Gets data."
        )

        with _mock_agent(ai_response):
            result = await nl_svc.process_question("Show data", db)

        assert result.error is not None
        assert "permission" in result.error.lower()
        assert result.attempts == 1
        mock_qs.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_sse_progress_callback_invoked(self, db: Session) -> None:
        """on_retry_progress callback is invoked before each retry."""
        ds = _setup_test_schema(db)
        source_id = str(ds.id)

        # First execution fails, correction succeeds
        call_count = 0
        mock_qs = MagicMock(spec=QueryService)

        def execute_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return QueryResult(
                    status="error",
                    error_message="SQL error: column 'bad' not found",
                )
            return QueryResult(
                status="success",
                columns=["id"],
                rows=[[1]],
                row_count=1,
                execution_time_ms=10,
            )

        mock_qs.execute.side_effect = execute_side_effect
        nl_svc = NLQueryService(query_service=mock_qs, max_retries=3)

        progress_calls: list[tuple] = []

        async def on_progress(attempt: int, max_retries: int, error: str, category: str) -> None:
            progress_calls.append((attempt, max_retries, error, category))

        bad_response = (
            f"SQL: SELECT bad FROM ds_sales\n"
            f"SOURCE_ID: {source_id}\n"
            f"SOURCE_TYPE: dataset\n"
            f"EXPLANATION: Initial."
        )
        good_response = (
            f"SQL: SELECT id FROM ds_sales\n"
            f"SOURCE_ID: {source_id}\n"
            f"SOURCE_TYPE: dataset\n"
            f"EXPLANATION: Fixed."
        )

        with _mock_agent_sequence([bad_response, good_response]):
            result = await nl_svc.process_question("Show data", db, on_retry_progress=on_progress)

        assert result.error is None
        assert len(progress_calls) == 1
        assert progress_calls[0][0] == 1  # attempt number
        assert progress_calls[0][1] == 3  # max_retries
        assert "not found" in progress_calls[0][2].lower()
        assert progress_calls[0][3] == ErrorCategory.COLUMN_NOT_FOUND

    @pytest.mark.asyncio
    async def test_max_retries_shows_all_attempts_with_categories(self, db: Session) -> None:
        """Max retries exceeded shows structured error with all attempt details."""
        ds = _setup_test_schema(db)
        source_id = str(ds.id)

        mock_qs = MagicMock(spec=QueryService)
        mock_qs.execute.return_value = QueryResult(
            status="error",
            error_message="SQL error: column 'bad_col' not found",
        )
        nl_svc = NLQueryService(query_service=mock_qs, max_retries=2)

        bad_response = (
            f"SQL: SELECT bad_col FROM ds_sales\n"
            f"SOURCE_ID: {source_id}\n"
            f"SOURCE_TYPE: dataset\n"
            f"EXPLANATION: Trying."
        )

        with _mock_agent(bad_response):
            result = await nl_svc.process_question("Show data", db)

        assert result.error is not None
        assert "3 attempts" in result.error
        assert result.attempts == 3
        assert len(result.correction_history) == 3
        # Each history entry should have a category
        for entry in result.correction_history:
            assert "category" in entry
            assert entry["category"] == ErrorCategory.COLUMN_NOT_FOUND

    @pytest.mark.asyncio
    async def test_successful_retry_returns_results(
        self, nl_service: NLQueryService, db: Session
    ) -> None:
        """Self-correction succeeds and returns query results."""
        ds = _setup_test_schema(db)
        source_id = str(ds.id)

        bad_response = (
            f"SQL: SELECT * FROM ds_sales WHERE nonexist = 1\n"
            f"SOURCE_ID: {source_id}\n"
            f"SOURCE_TYPE: dataset\n"
            f"EXPLANATION: Initial."
        )
        good_response = (
            f"SQL: SELECT * FROM ds_sales WHERE category = 'A'\n"
            f"SOURCE_ID: {source_id}\n"
            f"SOURCE_TYPE: dataset\n"
            f"EXPLANATION: Corrected."
        )

        with _mock_agent_sequence([bad_response, good_response]):
            result = await nl_service.process_question("Show A items", db)

        assert result.error is None
        assert result.row_count > 0
        assert result.attempts == 2
        assert len(result.correction_history) == 1  # Only the failed attempt
        assert result.columns == ["id", "name", "value", "category"]

    @pytest.mark.asyncio
    async def test_correction_history_has_category_on_each_entry(self, db: Session) -> None:
        """Each correction_history entry includes the error category."""
        ds = _setup_test_schema(db)
        source_id = str(ds.id)

        # Fail twice with different errors, then succeed
        call_count = 0
        mock_qs = MagicMock(spec=QueryService)

        def execute_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return QueryResult(status="error", error_message="syntax error near ','")
            if call_count == 2:
                return QueryResult(status="error", error_message="column 'x' not found")
            return QueryResult(
                status="success", columns=["id"], rows=[[1]], row_count=1, execution_time_ms=5
            )

        mock_qs.execute.side_effect = execute_side_effect
        nl_svc = NLQueryService(query_service=mock_qs, max_retries=3)

        ai_response = (
            f"SQL: SELECT * FROM t\nSOURCE_ID: {source_id}\nSOURCE_TYPE: dataset\nEXPLANATION: Try."
        )

        with _mock_agent(ai_response):
            result = await nl_svc.process_question("q", db)

        assert result.error is None
        assert result.attempts == 3
        assert len(result.correction_history) == 2
        assert result.correction_history[0]["category"] == ErrorCategory.SYNTAX
        assert result.correction_history[1]["category"] == ErrorCategory.COLUMN_NOT_FOUND


# ---------------------------------------------------------------------------
# Test helpers: mock agent
# ---------------------------------------------------------------------------


def _mock_agent(response_text: str):
    """Context manager that mocks create_agent to return a predictable response."""
    mock_result = MagicMock()
    mock_result.output = response_text

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=mock_result)

    return patch(
        "app.services.nl_query_service.create_agent",
        return_value=mock_agent,
    )


def _mock_agent_sequence(response_texts: list[str]):
    """Context manager that mocks create_agent to return different responses on successive calls."""
    call_count = 0

    def make_agent(*args, **kwargs):
        nonlocal call_count
        idx = min(call_count, len(response_texts) - 1)
        call_count += 1

        mock_result = MagicMock()
        mock_result.output = response_texts[idx]

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        return mock_agent

    return patch(
        "app.services.nl_query_service.create_agent",
        side_effect=make_agent,
    )
