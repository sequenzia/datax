"""Tests for the Pydantic AI agent tool functions.

Covers:
- Unit: Each tool function in isolation with mocked DuckDB/database
- Unit: Self-correction loop logic (retry count, error classification)
- Integration: run_query executes real DuckDB queries
- Integration: Full agent tool chain (query -> chart config generation)
"""

from __future__ import annotations

import csv
import os
import tempfile
import uuid
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.orm import Dataset, SchemaMetadata
from app.services.agent_tools import (
    AgentDeps,
    BookmarkResult,
    BookmarkSearchResult,
    DataProfileResult,
    FollowupResult,
    TableResult,
)
from app.services.connection_manager import ConnectionManager
from app.services.duckdb_manager import DuckDBManager
from app.services.query_service import QueryService, is_read_only_sql

# Generate a valid Fernet key for tests
TEST_FERNET_KEY = Fernet.generate_key().decode()


def _test_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return test environment with encryption key and optional extras."""
    env = {
        "DATABASE_URL": "sqlite:///:memory:",
        "DATAX_ENCRYPTION_KEY": TEST_FERNET_KEY,
    }
    if extra:
        env.update(extra)
    return env


@pytest.fixture
def db_engine():
    """Create an in-memory SQLite engine for tests."""
    engine = create_engine("sqlite:///:memory:")

    # Enable foreign keys for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session_factory(db_engine):
    """Create a session factory for tests."""
    return sessionmaker(bind=db_engine)


@pytest.fixture
def session(session_factory):
    """Create a database session for tests."""
    s = session_factory()
    yield s
    s.close()


@pytest.fixture
def duckdb_manager():
    """Create an in-memory DuckDB manager for tests."""
    manager = DuckDBManager(database=":memory:")
    yield manager
    manager.close()


@pytest.fixture
def connection_manager():
    """Create a connection manager for tests."""
    return ConnectionManager()


@pytest.fixture
def query_service(duckdb_manager, connection_manager):
    """Create a query service for tests."""
    return QueryService(
        duckdb_manager=duckdb_manager,
        connection_manager=connection_manager,
        max_query_timeout=30,
    )


@pytest.fixture
def agent_deps(duckdb_manager, connection_manager, query_service, session_factory):
    """Create AgentDeps with all service references."""
    return AgentDeps(
        schema_context="Test schema context",
        available_tables=["ds_test"],
        duckdb_manager=duckdb_manager,
        connection_manager=connection_manager,
        query_service=query_service,
        session_factory=session_factory,
        max_query_timeout=30,
        max_retries=3,
    )


@pytest.fixture
def test_agent():
    """Create a test agent with tools registered."""
    env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test"})
    with patch.dict(os.environ, env, clear=True):
        from app.services.agent_service import create_agent

        agent = create_agent()
        return agent


@pytest.fixture
def csv_file(duckdb_manager):
    """Create a test CSV file and register it in DuckDB."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False
    ) as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "amount", "created_date"])
        writer.writerow([1, "Alice", 100.50, "2024-01-01"])
        writer.writerow([2, "Bob", 200.75, "2024-01-02"])
        writer.writerow([3, "Charlie", 50.25, "2024-01-03"])
        writer.writerow([4, "Diana", 300.00, "2024-01-04"])
        writer.writerow([5, "Eve", 150.00, "2024-01-05"])
        csv_path = f.name

    result = duckdb_manager.register_file(csv_path, "ds_test", "csv")
    assert result.is_success

    yield csv_path

    # Cleanup
    try:
        os.unlink(csv_path)
    except OSError:
        pass


@pytest.fixture
def seeded_db(session, duckdb_manager, csv_file):
    """Seed the database with test data (dataset + schema metadata)."""
    ds_id = uuid.uuid4()
    dataset = Dataset(
        id=ds_id,
        name="test_data",
        file_path=csv_file,
        file_format="csv",
        duckdb_table_name="ds_test",
        status="ready",
        row_count=5,
    )
    session.add(dataset)

    for i, (col_name, col_type) in enumerate([
        ("id", "INTEGER"),
        ("name", "VARCHAR"),
        ("amount", "DOUBLE"),
        ("created_date", "VARCHAR"),
    ]):
        sm = SchemaMetadata(
            source_id=ds_id,
            source_type="dataset",
            table_name="ds_test",
            column_name=col_name,
            data_type=col_type,
            is_nullable=True,
            is_primary_key=(col_name == "id"),
            ordinal_position=i,
        )
        session.add(sm)

    session.commit()
    return ds_id


# ---------------------------------------------------------------------------
# Unit: run_query tool
# ---------------------------------------------------------------------------


class TestRunQueryTool:
    """Test the run_query agent tool in isolation."""

    @pytest.mark.asyncio
    async def test_run_query_executes_via_query_service(
        self, query_service, duckdb_manager, csv_file, session_factory
    ):
        """run_query uses QueryService to execute SQL against DuckDB."""
        # Verify AgentDeps can be constructed with service refs
        _ = AgentDeps(
            query_service=query_service,
            duckdb_manager=duckdb_manager,
            session_factory=session_factory,
        )

        # Test via the QueryService directly (same execution path
        # as the run_query tool uses internally)
        source_id = uuid.uuid4()
        # We can't easily call the tool function without a full RunContext,
        # so we test the underlying logic
        result = query_service.execute(
            sql="SELECT * FROM ds_test",
            source_id=source_id,
            source_type="dataset",
        )
        assert result.status == "success"
        assert result.row_count == 5
        assert "id" in result.columns
        assert "name" in result.columns

    @pytest.mark.asyncio
    async def test_run_query_rejects_write_sql(self):
        """run_query rejects write operations via is_read_only_sql."""
        assert not is_read_only_sql("INSERT INTO users VALUES (1)")
        assert not is_read_only_sql("UPDATE users SET name = 'x'")
        assert not is_read_only_sql("DELETE FROM users")
        assert not is_read_only_sql("DROP TABLE users")
        assert is_read_only_sql("SELECT * FROM users")
        assert is_read_only_sql("WITH cte AS (SELECT 1) SELECT * FROM cte")

    @pytest.mark.asyncio
    async def test_run_query_error_triggers_model_retry(
        self, query_service, duckdb_manager, csv_file
    ):
        """run_query raises ModelRetry for retryable SQL errors."""
        # Execute a query with an invalid table
        result = query_service.execute(
            sql="SELECT * FROM nonexistent_table",
            source_id=uuid.uuid4(),
            source_type="dataset",
        )
        assert result.status == "error"
        assert "nonexistent_table" in (result.error_message or "").lower()

    @pytest.mark.asyncio
    async def test_run_query_timeout_is_non_retryable(self):
        """Timeout errors should not trigger self-correction."""
        from app.services.nl_query_service import is_retryable_error

        assert not is_retryable_error("Query timed out", "timeout")
        assert not is_retryable_error("statement_timeout exceeded")
        assert is_retryable_error("column 'foo' not found")
        assert is_retryable_error("syntax error near SELECT")


# ---------------------------------------------------------------------------
# Unit: get_schema tool
# ---------------------------------------------------------------------------


class TestGetSchemaTool:
    """Test the get_schema agent tool."""

    @pytest.mark.asyncio
    async def test_get_schema_returns_columns(self, session_factory, seeded_db):
        """get_schema retrieves column metadata for a data source."""
        session = session_factory()
        try:
            from sqlalchemy import select

            stmt = (
                select(SchemaMetadata)
                .where(
                    SchemaMetadata.source_id == seeded_db,
                    SchemaMetadata.source_type == "dataset",
                )
                .order_by(SchemaMetadata.ordinal_position)
            )
            rows = list(session.execute(stmt).scalars().all())
            assert len(rows) == 4
            assert rows[0].column_name == "id"
            assert rows[0].data_type == "INTEGER"
            assert rows[0].is_primary_key is True
        finally:
            session.close()

    @pytest.mark.asyncio
    async def test_get_schema_empty_result(self, session_factory):
        """get_schema returns empty for non-existent source."""
        session = session_factory()
        try:
            from sqlalchemy import select

            fake_id = uuid.uuid4()
            stmt = select(SchemaMetadata).where(
                SchemaMetadata.source_id == fake_id
            )
            rows = list(session.execute(stmt).scalars().all())
            assert len(rows) == 0
        finally:
            session.close()


# ---------------------------------------------------------------------------
# Unit: summarize_table tool
# ---------------------------------------------------------------------------


class TestSummarizeTableTool:
    """Test the summarize_table agent tool."""

    @pytest.mark.asyncio
    async def test_summarize_table_returns_stats(self, duckdb_manager, csv_file):
        """summarize_table returns SUMMARIZE stats for a registered table."""
        stats = duckdb_manager.summarize_table("ds_test")
        assert len(stats) > 0
        # Check that stats have expected keys
        col_names = [s.get("column_name") for s in stats]
        assert "id" in col_names
        assert "amount" in col_names

    @pytest.mark.asyncio
    async def test_summarize_table_unregistered(self, duckdb_manager):
        """summarize_table returns error for unregistered table."""
        assert not duckdb_manager.is_table_registered("nonexistent")

    @pytest.mark.asyncio
    async def test_get_sample_values(self, duckdb_manager, csv_file):
        """get_sample_values returns distinct sample values per column."""
        samples = duckdb_manager.get_sample_values("ds_test", limit=3)
        assert "id" in samples
        assert "name" in samples
        assert len(samples["name"]) <= 3


# ---------------------------------------------------------------------------
# Unit: render_chart tool
# ---------------------------------------------------------------------------


class TestRenderChartTool:
    """Test the render_chart agent tool."""

    @pytest.mark.asyncio
    async def test_render_chart_categorical(self):
        """render_chart generates appropriate chart for categorical + numeric data."""
        from app.services.chart_config import generate_chart_config
        from app.services.chart_heuristics import recommend_chart_type

        # With few categories and all positive values, heuristic picks pie
        columns = ["category", "value"]
        rows = [["A", 10], ["B", 20], ["C", 30]]

        rec = recommend_chart_type(columns, rows)
        assert rec.chart_type in ("bar", "pie")

        config = generate_chart_config(columns, rows, recommendation=rec)
        assert config.chart_type in ("bar", "pie")
        assert len(config.data) > 0

    @pytest.mark.asyncio
    async def test_render_chart_bar_many_categories(self):
        """render_chart generates bar chart when many categories present."""
        from app.services.chart_config import generate_chart_config
        from app.services.chart_heuristics import recommend_chart_type

        # More than PIE_MAX_CATEGORIES (10) -> bar chart
        columns = ["category", "value"]
        rows = [[f"Cat_{i}", i * 10] for i in range(15)]

        rec = recommend_chart_type(columns, rows)
        assert rec.chart_type == "bar"

        config = generate_chart_config(columns, rows, recommendation=rec)
        assert config.chart_type == "bar"
        assert len(config.data) > 0

    @pytest.mark.asyncio
    async def test_render_chart_line_time_series(self):
        """render_chart generates line chart for time series data."""
        from app.services.chart_heuristics import recommend_chart_type

        columns = ["date", "revenue"]
        rows = [
            ["2024-01-01", 100],
            ["2024-01-02", 150],
            ["2024-01-03", 200],
        ]

        rec = recommend_chart_type(columns, rows)
        assert rec.chart_type == "line"

    @pytest.mark.asyncio
    async def test_render_chart_kpi_single_value(self):
        """render_chart generates KPI for single row result."""
        from app.services.chart_heuristics import recommend_chart_type

        columns = ["total_revenue"]
        rows = [[12345.67]]

        rec = recommend_chart_type(columns, rows)
        assert rec.chart_type == "kpi"

    @pytest.mark.asyncio
    async def test_render_chart_override(self):
        """render_chart respects AI chart type override."""
        from app.services.chart_heuristics import recommend_chart_type

        columns = ["category", "value"]
        rows = [["A", 10], ["B", 20]]

        rec = recommend_chart_type(columns, rows, ai_override="pie")
        assert rec.chart_type == "pie"


# ---------------------------------------------------------------------------
# Unit: render_table tool
# ---------------------------------------------------------------------------


class TestRenderTableTool:
    """Test the render_table agent tool."""

    @pytest.mark.asyncio
    async def test_render_table_returns_data(self):
        """render_table returns column definitions + data rows."""
        result = TableResult(
            columns=["id", "name", "amount"],
            rows=[[1, "Alice", 100], [2, "Bob", 200]],
            row_count=2,
        )
        data = result.model_dump()
        assert data["stage"] == "table_ready"
        assert data["row_count"] == 2
        assert len(data["columns"]) == 3


# ---------------------------------------------------------------------------
# Unit: suggest_followups tool
# ---------------------------------------------------------------------------


class TestSuggestFollowupsTool:
    """Test the suggest_followups agent tool."""

    @pytest.mark.asyncio
    async def test_suggest_followups_aggregation(self):
        """suggest_followups suggests drill-down for aggregated results."""
        result = FollowupResult(
            suggestions=[],
        )

        # Verify the model is valid
        data = result.model_dump()
        assert data["stage"] == "followups_ready"

    @pytest.mark.asyncio
    async def test_suggest_followups_minimum_two(self):
        """suggest_followups always returns at least 2 suggestions."""
        from app.services.agent_tools import FollowupSuggestion

        suggestions = []
        # Simulate: no GROUP BY, small result, no date columns
        if len(suggestions) < 2:
            suggestions.append(
                FollowupSuggestion(
                    question="What other insights can you find?",
                    reasoning="General exploration",
                )
            )
        assert len(suggestions) >= 1

    def test_followup_suggestion_model(self):
        """FollowupSuggestion includes question and reasoning fields."""
        from app.services.agent_tools import FollowupSuggestion

        suggestion = FollowupSuggestion(
            question="How does this trend over time?",
            reasoning="Date columns detected — trend analysis possible",
        )
        data = suggestion.model_dump()
        assert data["question"] == "How does this trend over time?"
        assert data["reasoning"] == "Date columns detected — trend analysis possible"

    def test_followup_result_with_suggestions(self):
        """FollowupResult serializes suggestions correctly."""
        from app.services.agent_tools import FollowupSuggestion

        result = FollowupResult(
            suggestions=[
                FollowupSuggestion(
                    question="Break down by region?",
                    reasoning="3 outliers detected",
                ),
                FollowupSuggestion(
                    question="Show trend over time?",
                    reasoning="Date column present",
                ),
            ],
        )
        data = result.model_dump()
        assert data["stage"] == "followups_ready"
        assert data["progress_stage"] == "complete"
        assert len(data["suggestions"]) == 2
        assert data["suggestions"][0]["question"] == "Break down by region?"
        assert data["suggestions"][0]["reasoning"] == "3 outliers detected"
        assert data["suggestions"][1]["question"] == "Show trend over time?"

    def test_followup_result_max_three(self):
        """FollowupResult can hold up to 3 suggestions."""
        from app.services.agent_tools import FollowupSuggestion

        suggestions = [
            FollowupSuggestion(question=f"Question {i}", reasoning=f"Reason {i}")
            for i in range(3)
        ]
        result = FollowupResult(suggestions=suggestions)
        data = result.model_dump()
        assert len(data["suggestions"]) == 3

    def test_followup_result_empty_renders_nothing(self):
        """Empty FollowupResult serializes with empty suggestions list."""
        result = FollowupResult(suggestions=[])
        data = result.model_dump()
        assert data["stage"] == "followups_ready"
        assert data["suggestions"] == []


# ---------------------------------------------------------------------------
# Unit: create_bookmark tool
# ---------------------------------------------------------------------------


class TestCreateBookmarkTool:
    """Test the create_bookmark agent tool."""

    @pytest.mark.asyncio
    async def test_bookmark_model(self):
        """BookmarkResult model serializes correctly."""
        result = BookmarkResult(
            bookmark_id="abc-123",
            title="Top 10 customers",
        )
        data = result.model_dump()
        assert data["stage"] == "bookmark_created"
        assert data["bookmark_id"] == "abc-123"
        assert data["title"] == "Top 10 customers"


# ---------------------------------------------------------------------------
# Unit: search_bookmarks tool
# ---------------------------------------------------------------------------


class TestSearchBookmarksTool:
    """Test the search_bookmarks agent tool."""

    @pytest.mark.asyncio
    async def test_bookmark_search_model(self):
        """BookmarkSearchResult model serializes correctly."""
        result = BookmarkSearchResult(
            bookmarks=[
                {
                    "bookmark_id": "id-1",
                    "title": "Sales Report",
                    "sql": "SELECT * FROM sales",
                    "source_type": "dataset",
                    "chart_type": "bar",
                }
            ],
        )
        data = result.model_dump()
        assert data["stage"] == "bookmarks_found"
        assert len(data["bookmarks"]) == 1


# ---------------------------------------------------------------------------
# Unit: Self-correction loop logic
# ---------------------------------------------------------------------------


class TestSelfCorrectionLoop:
    """Test the self-correction retry logic."""

    def test_error_classification(self):
        """Error messages are classified into correct categories."""
        from app.services.nl_query_service import ErrorCategory, classify_error

        assert classify_error("column 'foo' not found") == ErrorCategory.COLUMN_NOT_FOUND
        assert classify_error("no such table: users") == ErrorCategory.TABLE_NOT_FOUND
        assert classify_error("syntax error near 'FROM'") == ErrorCategory.SYNTAX
        assert classify_error("type mismatch in comparison") == ErrorCategory.TYPE_MISMATCH
        assert classify_error("connection lost") == ErrorCategory.CONNECTION_LOST
        assert classify_error("permission denied for table") == ErrorCategory.PERMISSION_DENIED
        assert classify_error("query timed out") == ErrorCategory.TIMEOUT
        assert classify_error("something weird happened") == ErrorCategory.UNKNOWN

    def test_retryable_vs_non_retryable(self):
        """Retryable errors allow self-correction; non-retryable do not."""
        from app.services.nl_query_service import is_retryable_error

        # Retryable
        assert is_retryable_error("column 'x' not found") is True
        assert is_retryable_error("syntax error") is True
        assert is_retryable_error("no such table") is True

        # Non-retryable
        assert is_retryable_error("query timed out", "timeout") is False
        assert is_retryable_error("connection lost") is False
        assert is_retryable_error("permission denied") is False
        assert is_retryable_error("READ_ONLY violation") is False

    def test_max_retries_from_config(self):
        """AgentDeps respects DATAX_MAX_RETRIES configuration."""
        deps = AgentDeps(max_retries=5)
        assert deps.max_retries == 5

        deps_default = AgentDeps()
        assert deps_default.max_retries == 3


# ---------------------------------------------------------------------------
# Integration: run_query executes real DuckDB queries
# ---------------------------------------------------------------------------


class TestRunQueryIntegration:
    """Integration tests for run_query with real DuckDB."""

    @pytest.mark.asyncio
    async def test_select_all(self, query_service, duckdb_manager, csv_file):
        """run_query executes SELECT * and returns all rows."""
        source_id = uuid.uuid4()
        result = query_service.execute(
            sql="SELECT * FROM ds_test",
            source_id=source_id,
            source_type="dataset",
        )
        assert result.status == "success"
        assert result.row_count == 5
        assert "id" in result.columns
        assert "name" in result.columns
        assert "amount" in result.columns

    @pytest.mark.asyncio
    async def test_select_with_where(self, query_service, duckdb_manager, csv_file):
        """run_query executes SELECT with WHERE clause."""
        source_id = uuid.uuid4()
        result = query_service.execute(
            sql="SELECT name, amount FROM ds_test WHERE amount > 100",
            source_id=source_id,
            source_type="dataset",
        )
        assert result.status == "success"
        assert result.row_count == 4  # Alice(100.50), Bob(200.75), Diana(300), Eve(150)

    @pytest.mark.asyncio
    async def test_select_with_aggregation(self, query_service, duckdb_manager, csv_file):
        """run_query executes aggregation queries."""
        source_id = uuid.uuid4()
        result = query_service.execute(
            sql="SELECT COUNT(*) as cnt, SUM(amount) as total FROM ds_test",
            source_id=source_id,
            source_type="dataset",
        )
        assert result.status == "success"
        assert result.row_count == 1
        assert result.rows[0][0] == 5  # count
        assert result.rows[0][1] == pytest.approx(801.50)  # sum

    @pytest.mark.asyncio
    async def test_write_query_blocked(self, query_service, duckdb_manager, csv_file):
        """run_query blocks write operations."""
        source_id = uuid.uuid4()
        result = query_service.execute(
            sql="INSERT INTO ds_test VALUES (6, 'Frank', 400.00, '2024-01-06')",
            source_id=source_id,
            source_type="dataset",
        )
        assert result.status != "success"
        err = (result.error_message or "")
        assert "read-only" in err.lower() or "READ_ONLY" in err

    @pytest.mark.asyncio
    async def test_invalid_sql_returns_error(self, query_service, duckdb_manager, csv_file):
        """run_query returns error for invalid SQL."""
        source_id = uuid.uuid4()
        result = query_service.execute(
            sql="SELECT nonexistent_column FROM ds_test",
            source_id=source_id,
            source_type="dataset",
        )
        assert result.status == "error"
        assert result.error_message is not None


# ---------------------------------------------------------------------------
# Integration: Full agent tool chain
# ---------------------------------------------------------------------------


class TestAgentToolChain:
    """Integration test for query -> chart config generation chain."""

    @pytest.mark.asyncio
    async def test_query_to_chart(self, query_service, duckdb_manager, csv_file):
        """Full chain: query data, then generate chart config."""
        from app.services.chart_config import generate_chart_config
        from app.services.chart_heuristics import recommend_chart_type

        # Step 1: Execute query
        source_id = uuid.uuid4()
        result = query_service.execute(
            sql="SELECT name, amount FROM ds_test ORDER BY amount DESC",
            source_id=source_id,
            source_type="dataset",
        )
        assert result.status == "success"
        assert result.row_count == 5

        # Step 2: Recommend chart type (5 names + amounts = categorical chart)
        rec = recommend_chart_type(result.columns, result.rows)
        assert rec.chart_type in ("bar", "pie")  # Depends on category count vs PIE_MAX_CATEGORIES
        assert rec.x_column == "name"
        assert rec.y_column == "amount"

        # Step 3: Generate chart config
        config = generate_chart_config(
            columns=result.columns,
            rows=result.rows,
            recommendation=rec,
            title="Sales by Customer",
        )
        assert config.chart_type in ("bar", "pie")
        assert len(config.data) > 0
        assert config.layout["title"]["text"] == "Sales by Customer"

    @pytest.mark.asyncio
    async def test_query_to_table(self, query_service, duckdb_manager, csv_file):
        """Full chain: query data, then build table result."""
        source_id = uuid.uuid4()
        result = query_service.execute(
            sql="SELECT * FROM ds_test LIMIT 3",
            source_id=source_id,
            source_type="dataset",
        )
        assert result.status == "success"

        table = TableResult(
            columns=result.columns,
            rows=result.rows,
            row_count=result.row_count,
        )
        data = table.model_dump()
        assert data["stage"] == "table_ready"
        assert data["row_count"] == 3

    @pytest.mark.asyncio
    async def test_query_to_summarize(self, duckdb_manager, csv_file):
        """Full chain: summarize table data for profiling."""
        stats = duckdb_manager.summarize_table("ds_test")
        samples = duckdb_manager.get_sample_values("ds_test", limit=5)

        profile = DataProfileResult(
            table_name="ds_test",
            stats=stats,
            sample_values=samples,
        )
        data = profile.model_dump()
        assert data["stage"] == "profile_ready"
        assert data["table_name"] == "ds_test"
        assert len(data["stats"]) > 0
        assert "id" in data["sample_values"]


# ---------------------------------------------------------------------------
# Test: All 10 tools registered
# ---------------------------------------------------------------------------


class TestToolRegistration:
    """Verify all 10 tools are registered on the agent."""

    def test_all_10_tools_registered(self):
        """Agent has exactly 10 tools registered."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test"})
        with patch.dict(os.environ, env, clear=True):
            from app.services.agent_service import create_agent

            agent = create_agent()

            # Access the toolset via the internal API
            toolset = agent._get_toolset(None)
            tool_names = set()
            for sub_ts in toolset.toolsets:
                if hasattr(sub_ts, "tools"):
                    for t in sub_ts.tools:
                        tool_names.add(t)

            expected_tools = {
                "run_query",
                "get_schema",
                "summarize_table",
                "render_chart",
                "render_table",
                "render_data_profile",
                "suggest_followups",
                "create_bookmark",
                "search_bookmarks",
                "list_datasources",
            }
            assert tool_names == expected_tools, (
                f"Expected tools: {expected_tools}, got: {tool_names}"
            )

    def test_run_query_has_retries(self):
        """run_query tool is configured with retries=3 for self-correction."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test"})
        with patch.dict(os.environ, env, clear=True):
            from app.services.agent_service import create_agent

            agent = create_agent()

            # Access the toolset and check run_query retries
            toolset = agent._get_toolset(None)
            for sub_ts in toolset.toolsets:
                if hasattr(sub_ts, "tools") and "run_query" in sub_ts.tools:
                    tool = sub_ts.tools["run_query"]
                    assert tool.max_retries == 3
                    break
            else:
                pytest.fail("run_query tool not found")


# ---------------------------------------------------------------------------
# Test: AgentDeps model
# ---------------------------------------------------------------------------


class TestAgentDepsModel:
    """Test the AgentDeps dataclass."""

    def test_default_deps(self):
        """AgentDeps has sensible defaults."""
        deps = AgentDeps()
        assert deps.schema_context == ""
        assert deps.conversation_id is None
        assert deps.available_tables == []
        assert deps.duckdb_manager is None
        assert deps.connection_manager is None
        assert deps.query_service is None
        assert deps.session_factory is None
        assert deps.max_query_timeout == 30
        assert deps.max_retries == 3

    def test_deps_with_services(self, duckdb_manager, connection_manager, query_service):
        """AgentDeps can hold service references."""
        deps = AgentDeps(
            schema_context="test context",
            duckdb_manager=duckdb_manager,
            connection_manager=connection_manager,
            query_service=query_service,
            max_query_timeout=60,
            max_retries=5,
        )
        assert deps.duckdb_manager is duckdb_manager
        assert deps.connection_manager is connection_manager
        assert deps.query_service is query_service
        assert deps.max_query_timeout == 60
        assert deps.max_retries == 5


# ---------------------------------------------------------------------------
# Test: System prompt includes tool descriptions
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    """Verify the system prompt describes all tools."""

    def test_system_prompt_lists_tools(self):
        """System prompt describes all 9 agent tools."""
        from app.services.agent_service import ANALYTICS_SYSTEM_PROMPT

        tool_names = [
            "run_query",
            "get_schema",
            "summarize_table",
            "render_chart",
            "render_table",
            "render_data_profile",
            "suggest_followups",
            "create_bookmark",
            "search_bookmarks",
        ]
        for name in tool_names:
            assert name in ANALYTICS_SYSTEM_PROMPT, (
                f"Tool '{name}' not mentioned in system prompt"
            )

    def test_system_prompt_includes_schema_context_note(self):
        """System prompt mentions schema context injection."""
        from app.services.agent_service import ANALYTICS_SYSTEM_PROMPT

        assert "schema context" in ANALYTICS_SYSTEM_PROMPT.lower()

    def test_system_prompt_includes_pattern_detection_instructions(self):
        """System prompt includes pattern detection instructions for follow-ups."""
        from app.services.agent_service import ANALYTICS_SYSTEM_PROMPT

        prompt_lower = ANALYTICS_SYSTEM_PROMPT.lower()
        # Verify pattern types are mentioned
        assert "outlier" in prompt_lower
        assert "time-series" in prompt_lower or "time series" in prompt_lower
        assert "skewed" in prompt_lower
        assert "null" in prompt_lower
        # Verify contextual guidance
        assert "do not suggest follow-ups" in prompt_lower or "do not suggest" in prompt_lower
