"""Pydantic AI agent tool functions for the DataX analytics agent.

Implements the 9 core agent tools that enable the AI to interact with
data sources, generate visualizations, and manage bookmarks:

1. run_query - Execute SQL via Virtual Data Layer (DuckDB or SQLAlchemy)
2. get_schema - Retrieve schema metadata for a dataset or connection
3. summarize_table - Get SUMMARIZE stats + sample values
4. render_chart - Generate Plotly chart configuration
5. render_table - Signal to render a DataTable component
6. render_data_profile - Signal to render a DataProfile component
7. suggest_followups - Generate contextual follow-up suggestions
8. create_bookmark - Save current result as a bookmark
9. search_bookmarks - Search existing bookmarks

Self-correction loop:
    The agent's built-in retry mechanism (via ``retries`` on the tool)
    handles failed SQL. When ``run_query`` raises a ``ToolRetryError``,
    pydantic-ai sends the error back to the model so it can generate
    corrected SQL on the next attempt.

Progress reporting:
    Each tool returns structured data that includes a ``stage`` field
    so the frontend can display progress indicators.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import ModelRetry
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.models.orm import Bookmark, SchemaMetadata
from app.services.bookmark_service import BookmarkService
from app.services.chart_config import generate_chart_config
from app.services.chart_heuristics import recommend_chart_type
from app.services.connection_manager import ConnectionManager
from app.services.duckdb_manager import DuckDBManager
from app.services.query_service import QueryService, is_read_only_sql

logger = get_logger(__name__)

# Explicit union of JSON-compatible scalar types for tool parameters.
# Using Any generates {"items": {}} in JSON Schema, which lacks a "type"
# key and is rejected by OpenAI's function calling API.
JsonScalar = str | int | float | bool | None


# ---------------------------------------------------------------------------
# Agent dependencies
# ---------------------------------------------------------------------------


@dataclass
class AgentDeps:
    """Dependencies injected into the Pydantic AI agent at runtime.

    Provides access to data services, schema context, and conversation
    state for all agent tool functions.
    """

    # Schema context for the AI system prompt
    schema_context: str = ""
    conversation_id: str | None = None
    available_tables: list[str] = field(default_factory=list)

    # Conversation context for follow-ups
    analysis_state: Any | None = None  # AnalysisState instance

    # Service references for tool execution
    duckdb_manager: DuckDBManager | None = None
    connection_manager: ConnectionManager | None = None
    query_service: QueryService | None = None
    session_factory: Any | None = None

    # Configuration
    max_query_timeout: int = 30
    max_retries: int = 3


# ---------------------------------------------------------------------------
# Progress stages (mirrored on the frontend as ProgressStage)
# ---------------------------------------------------------------------------

PROGRESS_GENERATING_SQL = "generating_sql"
PROGRESS_EXECUTING_QUERY = "executing_query"
PROGRESS_BUILDING_VISUALIZATION = "building_visualization"
PROGRESS_RETRYING = "retrying"
PROGRESS_COMPLETE = "complete"
PROGRESS_ERROR = "error"


def _log_progress(stage: str, tool_name: str, **extra: Any) -> None:
    """Log a structured progress event for observability.

    The AG-UI adapter automatically emits ToolCallStartEvent /
    ToolCallEndEvent for each tool, which CopilotKit maps to
    useCoAgentStateRender on the frontend. This helper adds a
    structured log line for server-side monitoring.
    """
    logger.info("agent_progress", stage=stage, tool=tool_name, **extra)


# ---------------------------------------------------------------------------
# Tool result models
# ---------------------------------------------------------------------------


class QueryResult(BaseModel):
    """Result of a run_query tool call."""

    stage: str = "query_complete"
    progress_stage: str = PROGRESS_COMPLETE
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    execution_time_ms: int = 0
    sql: str = ""
    source_id: str = ""
    source_type: str = ""


class SchemaResult(BaseModel):
    """Result of a get_schema tool call."""

    stage: str = "schema_retrieved"
    progress_stage: str = PROGRESS_GENERATING_SQL
    table_name: str = ""
    source_type: str = ""
    columns: list[dict[str, Any]] = Field(default_factory=list)


class SummarizeResult(BaseModel):
    """Result of a summarize_table tool call."""

    stage: str = "summarize_complete"
    progress_stage: str = PROGRESS_EXECUTING_QUERY
    table_name: str = ""
    stats: list[dict[str, Any]] = Field(default_factory=list)
    sample_values: dict[str, list[Any]] = Field(default_factory=dict)


class ChartResult(BaseModel):
    """Result of a render_chart tool call."""

    stage: str = "chart_ready"
    progress_stage: str = PROGRESS_COMPLETE
    chart_config: dict[str, Any] = Field(default_factory=dict)
    chart_type: str = ""
    reasoning: str = ""


class TableResult(BaseModel):
    """Result of a render_table tool call."""

    stage: str = "table_ready"
    progress_stage: str = PROGRESS_COMPLETE
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0


class DataProfileResult(BaseModel):
    """Result of a render_data_profile tool call."""

    stage: str = "profile_ready"
    progress_stage: str = PROGRESS_BUILDING_VISUALIZATION
    table_name: str = ""
    stats: list[dict[str, Any]] = Field(default_factory=list)
    sample_values: dict[str, list[Any]] = Field(default_factory=dict)


class FollowupSuggestion(BaseModel):
    """A single follow-up suggestion."""

    question: str = ""
    reasoning: str = ""


class FollowupResult(BaseModel):
    """Result of a suggest_followups tool call."""

    stage: str = "followups_ready"
    progress_stage: str = PROGRESS_COMPLETE
    suggestions: list[FollowupSuggestion] = Field(default_factory=list)


class BookmarkResult(BaseModel):
    """Result of a create_bookmark tool call."""

    stage: str = "bookmark_created"
    progress_stage: str = PROGRESS_COMPLETE
    bookmark_id: str = ""
    title: str = ""


class BookmarkSearchResult(BaseModel):
    """Result of a search_bookmarks tool call."""

    stage: str = "bookmarks_found"
    progress_stage: str = PROGRESS_EXECUTING_QUERY
    bookmarks: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register_tools(agent: Agent[AgentDeps, str]) -> None:
    """Register all 9 agent tools on the Pydantic AI agent.

    Each tool is decorated with ``@agent.tool`` and receives a
    ``RunContext[AgentDeps]`` as its first argument, giving access
    to data services and configuration.
    """

    @agent.tool(retries=3)
    async def run_query(
        ctx: RunContext[AgentDeps],
        sql: str,
        source_id: str,
        source_type: str,
    ) -> dict[str, Any]:
        """Execute a SQL query against a dataset (DuckDB) or connection (external database).

        Args:
            sql: The SQL query to execute. Must be a read-only SELECT statement.
            source_id: UUID of the dataset or connection to query.
            source_type: Type of source - either 'dataset' or 'connection'.

        Returns:
            Query results with columns, rows, row_count, and execution_time_ms.
            On error, raises ModelRetry so the agent can self-correct.
        """
        deps = ctx.deps
        _log_progress(PROGRESS_EXECUTING_QUERY, "run_query", sql_length=len(sql))

        # Validate read-only
        if not is_read_only_sql(sql):
            raise ModelRetry(
                "SQL rejected: write operations (INSERT, UPDATE, DELETE, DROP, etc.) "
                "are not allowed. Only read-only SELECT statements are permitted. "
                "Please generate a SELECT query instead."
            )

        # Validate source_type
        if source_type not in ("dataset", "connection"):
            raise ModelRetry(
                f"Invalid source_type '{source_type}'. Must be 'dataset' or 'connection'."
            )

        # Validate source_id as UUID
        try:
            source_uuid = uuid.UUID(source_id)
        except ValueError:
            raise ModelRetry(
                f"Invalid source_id '{source_id}'. Must be a valid UUID."
            )

        # Execute via QueryService
        query_service = deps.query_service
        if query_service is None:
            raise ModelRetry(
                "Query service is not available. The system may be starting up."
            )

        result = query_service.execute(
            sql=sql,
            source_id=source_uuid,
            source_type=source_type,
        )

        # Handle errors with self-correction via ModelRetry
        if result.status != "success":
            # Import lazily to avoid circular import with agent_service
            from app.services.nl_query_service import (
                ErrorCategory,
                classify_error,
                is_retryable_error,
            )

            error_msg = result.error_message or "Unknown query error"
            error_category = classify_error(error_msg)

            # Non-retryable errors should not trigger self-correction
            if not is_retryable_error(error_msg, result.status):
                if result.status == "timeout":
                    return {
                        "stage": "query_error",
                        "error": (
                            f"Query exceeded the time limit of {deps.max_query_timeout}s. "
                            "Try narrowing your question or adding filters."
                        ),
                        "error_category": ErrorCategory.TIMEOUT,
                        "retryable": False,
                    }
                return {
                    "stage": "query_error",
                    "error": error_msg,
                    "error_category": error_category,
                    "retryable": False,
                }

            # Retryable error - raise ModelRetry for agent self-correction
            raise ModelRetry(
                f"SQL query failed ({error_category}): {error_msg}. "
                f"Please analyze the error and generate a corrected SQL query. "
                f"Check the schema context for correct table and column names."
            )

        logger.info(
            "tool_run_query_success",
            row_count=result.row_count,
            execution_time_ms=result.execution_time_ms,
        )

        return QueryResult(
            columns=result.columns,
            rows=result.rows,
            row_count=result.row_count,
            execution_time_ms=result.execution_time_ms,
            sql=sql,
            source_id=source_id,
            source_type=source_type,
        ).model_dump()

    @agent.tool
    async def get_schema(
        ctx: RunContext[AgentDeps],
        source_id: str,
        source_type: str,
    ) -> dict[str, Any]:
        """Retrieve schema metadata for a dataset or connection.

        Args:
            source_id: UUID of the dataset or connection.
            source_type: Type of source - either 'dataset' or 'connection'.

        Returns:
            Schema information with table name and column details including
            name, data_type, is_nullable, and is_primary_key.
        """
        deps = ctx.deps
        _log_progress(PROGRESS_GENERATING_SQL, "get_schema", source_type=source_type)

        try:
            source_uuid = uuid.UUID(source_id)
        except ValueError:
            return {"stage": "schema_error", "error": f"Invalid source_id: {source_id}"}

        if deps.session_factory is None:
            return {"stage": "schema_error", "error": "Database session not available"}

        session: Session = deps.session_factory()
        try:
            stmt = (
                select(SchemaMetadata)
                .where(
                    SchemaMetadata.source_id == source_uuid,
                    SchemaMetadata.source_type == source_type,
                )
                .order_by(SchemaMetadata.table_name, SchemaMetadata.ordinal_position)
            )
            rows = list(session.execute(stmt).scalars().all())

            if not rows:
                return {
                    "stage": "schema_retrieved",
                    "table_name": "",
                    "source_type": source_type,
                    "columns": [],
                    "message": f"No schema found for {source_type} {source_id}",
                }

            columns = [
                {
                    "column_name": r.column_name,
                    "data_type": r.data_type,
                    "is_nullable": r.is_nullable,
                    "is_primary_key": r.is_primary_key,
                    "foreign_key_ref": r.foreign_key_ref,
                }
                for r in rows
            ]

            return SchemaResult(
                table_name=rows[0].table_name,
                source_type=source_type,
                columns=columns,
            ).model_dump()
        finally:
            session.close()

    @agent.tool
    async def summarize_table(
        ctx: RunContext[AgentDeps],
        table_name: str,
    ) -> dict[str, Any]:
        """Get SUMMARIZE statistics and sample values for a DuckDB dataset table.

        Args:
            table_name: The DuckDB table name (e.g., 'ds_sales_2024').

        Returns:
            Column statistics (min, max, avg, std, null_percentage, etc.)
            and up to 5 sample values per column.
        """
        deps = ctx.deps
        _log_progress(PROGRESS_EXECUTING_QUERY, "summarize_table", table_name=table_name)

        if deps.duckdb_manager is None:
            return {"stage": "summarize_error", "error": "DuckDB manager not available"}

        if not deps.duckdb_manager.is_table_registered(table_name):
            return {
                "stage": "summarize_error",
                "error": f"Table '{table_name}' is not registered in DuckDB",
            }

        stats = deps.duckdb_manager.summarize_table(table_name)
        samples = deps.duckdb_manager.get_sample_values(table_name, limit=5)

        return SummarizeResult(
            table_name=table_name,
            stats=stats,
            sample_values=samples,
        ).model_dump()

    @agent.tool
    async def render_chart(
        ctx: RunContext[AgentDeps],
        columns: list[str],
        rows: list[list[JsonScalar]],
        title: str | None = None,
        chart_type_override: str | None = None,
        query_context: str | None = None,
    ) -> dict[str, Any]:
        """Generate a Plotly chart configuration for the given query results.

        Uses chart heuristics to automatically select the best chart type,
        or uses the specified override.

        Args:
            columns: Column names from the query result.
            rows: Row data from the query result (list of lists).
            title: Optional chart title.
            chart_type_override: Optional chart type to force
                (line, bar, pie, scatter, histogram, kpi).
            query_context: Optional description of what the data represents.

        Returns:
            Plotly chart configuration with data traces and layout,
            ready for react-plotly.js rendering.
        """
        _log_progress(PROGRESS_BUILDING_VISUALIZATION, "render_chart")

        # Get chart recommendation using heuristics
        recommendation = recommend_chart_type(
            columns=columns,
            rows=rows,
            ai_override=chart_type_override,
        )

        # Generate Plotly config
        config = generate_chart_config(
            columns=columns,
            rows=rows,
            title=title,
            recommendation=recommendation,
            query_context=query_context,
        )

        return ChartResult(
            chart_config=config.to_dict(),
            chart_type=config.chart_type,
            reasoning=recommendation.reasoning,
        ).model_dump()

    @agent.tool
    async def render_table(
        ctx: RunContext[AgentDeps],
        columns: list[str],
        rows: list[list[JsonScalar]],
    ) -> dict[str, Any]:
        """Signal to render query results as an interactive DataTable component.

        Args:
            columns: Column names from the query result.
            rows: Row data from the query result (list of lists).

        Returns:
            Table configuration with columns, rows, and row count for
            the DataTable component.
        """
        _log_progress(PROGRESS_BUILDING_VISUALIZATION, "render_table", row_count=len(rows))

        return TableResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
        ).model_dump()

    @agent.tool
    async def render_data_profile(
        ctx: RunContext[AgentDeps],
        table_name: str,
    ) -> dict[str, Any]:
        """Signal to render a DataProfile component with profiling statistics.

        Args:
            table_name: The DuckDB table name to profile (e.g., 'ds_sales_2024').

        Returns:
            Profiling statistics and sample values for the DataProfile component.
        """
        deps = ctx.deps
        _log_progress(PROGRESS_BUILDING_VISUALIZATION, "render_data_profile", table_name=table_name)

        if deps.duckdb_manager is None:
            return {"stage": "profile_error", "error": "DuckDB manager not available"}

        if not deps.duckdb_manager.is_table_registered(table_name):
            return {
                "stage": "profile_error",
                "error": f"Table '{table_name}' is not registered in DuckDB",
            }

        stats = deps.duckdb_manager.summarize_table(table_name)
        samples = deps.duckdb_manager.get_sample_values(table_name, limit=5)

        return DataProfileResult(
            table_name=table_name,
            stats=stats,
            sample_values=samples,
        ).model_dump()

    @agent.tool
    async def suggest_followups(
        ctx: RunContext[AgentDeps],
        current_query: str,
        columns: list[str],
        row_count: int,
        chart_type: str | None = None,
    ) -> dict[str, Any]:
        """Generate 2-3 contextual follow-up suggestions based on the current result.

        Analyzes the query structure and result shape to suggest meaningful
        next steps for data exploration.

        Args:
            current_query: The SQL query that produced the current results.
            columns: Column names from the current result.
            row_count: Number of rows in the current result.
            chart_type: The chart type used to visualize the current result.

        Returns:
            A list of 2-3 follow-up question suggestions with reasoning.
        """
        suggestions: list[FollowupSuggestion] = []

        # Suggest drill-down if results are aggregated
        has_group_by = "GROUP BY" in current_query.upper()
        has_agg = any(
            kw in current_query.upper()
            for kw in ("COUNT(", "SUM(", "AVG(", "MAX(", "MIN(")
        )

        if has_group_by or has_agg:
            suggestions.append(
                FollowupSuggestion(
                    question="Can you break this down further by adding another dimension?",
                    reasoning=(
                        "The current query uses aggregation. "
                        "Adding another GROUP BY dimension "
                        "could reveal more patterns."
                    ),
                )
            )

        # Suggest filtering if result set is large
        if row_count > 100:
            suggestions.append(
                FollowupSuggestion(
                    question="Can you filter this to show only the top 10 results?",
                    reasoning=(
                        f"The result has {row_count} rows. "
                        "Filtering to top results may "
                        "highlight key insights."
                    ),
                )
            )

        # Suggest time trend if date columns present
        date_keywords = ("date", "time", "created", "updated", "year", "month", "day")
        has_date_col = any(
            any(kw in col.lower() for kw in date_keywords)
            for col in columns
        )
        if has_date_col and chart_type != "line":
            suggestions.append(
                FollowupSuggestion(
                    question="How does this trend over time?",
                    reasoning="Date columns detected. A time series analysis could reveal trends.",
                )
            )

        # Suggest comparison if categorical data
        if chart_type == "bar" and row_count > 1:
            suggestions.append(
                FollowupSuggestion(
                    question="How does this compare to the previous period?",
                    reasoning=(
                        "Bar chart with categories suggests "
                        "comparison analysis could be valuable."
                    ),
                )
            )

        # Ensure 2-3 suggestions
        if len(suggestions) < 2:
            suggestions.append(
                FollowupSuggestion(
                    question="What other insights can you find in this data?",
                    reasoning="General exploration suggestion based on the current result.",
                )
            )

        return FollowupResult(
            suggestions=suggestions[:3],
        ).model_dump()

    @agent.tool
    async def create_bookmark(
        ctx: RunContext[AgentDeps],
        title: str,
        sql: str,
        source_id: str,
        source_type: str,
        chart_config: dict[str, Any] | None = None,
        result_snapshot: dict[str, Any] | None = None,
        message_id: str | None = None,
    ) -> dict[str, Any]:
        """Save the current result (SQL + chart config + data snapshot) as a bookmark.

        Args:
            title: A descriptive title for the bookmark.
            sql: The SQL query that produced the result.
            source_id: UUID of the data source.
            source_type: Type of source - 'dataset' or 'connection'.
            chart_config: Optional Plotly chart configuration to save.
            result_snapshot: Optional data snapshot (columns + sample rows).
            message_id: Optional UUID of the message to link the bookmark to.

        Returns:
            The created bookmark ID and title.
        """
        deps = ctx.deps

        if deps.session_factory is None:
            return {"stage": "bookmark_error", "error": "Database session not available"}

        if not message_id:
            return {
                "stage": "bookmark_error",
                "error": "message_id is required to create a bookmark",
            }

        try:
            msg_uuid = uuid.UUID(message_id)
        except ValueError:
            return {"stage": "bookmark_error", "error": f"Invalid message_id: {message_id}"}

        session: Session = deps.session_factory()
        try:
            # The agent tool creates bookmarks directly with all provided fields
            # (not via the service's create_bookmark which copies from the message)
            bookmark = Bookmark(
                message_id=msg_uuid,
                title=title,
                sql=sql,
                chart_config=chart_config,
                result_snapshot=result_snapshot,
                source_id=source_id,
                source_type=source_type,
            )
            session.add(bookmark)
            session.commit()
            session.refresh(bookmark)

            logger.info(
                "tool_create_bookmark",
                bookmark_id=str(bookmark.id),
                title=title,
            )

            return BookmarkResult(
                bookmark_id=str(bookmark.id),
                title=title,
            ).model_dump()
        except Exception as exc:
            session.rollback()
            logger.error("tool_create_bookmark_failed", error=str(exc))
            return {
                "stage": "bookmark_error",
                "error": f"Failed to create bookmark: {exc}",
            }
        finally:
            session.close()

    @agent.tool
    async def search_bookmarks(
        ctx: RunContext[AgentDeps],
        query: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search existing bookmarks by title or SQL content.

        Args:
            query: Search term to match against bookmark titles and SQL.
            limit: Maximum number of bookmarks to return (default 10).

        Returns:
            List of matching bookmarks with their IDs, titles, SQL, and chart types.
        """
        deps = ctx.deps

        if deps.session_factory is None:
            return {"stage": "bookmarks_error", "error": "Database session not available"}

        session: Session = deps.session_factory()
        try:
            service = BookmarkService(session)
            bookmarks = service.search_bookmarks(query=query, limit=limit)

            results = [
                {
                    "bookmark_id": b["id"],
                    "title": b["title"],
                    "sql": b["sql"],
                    "source_type": b["source_type"],
                    "chart_type": (
                        b["chart_config"].get("chart_type")
                        if isinstance(b.get("chart_config"), dict)
                        else None
                    ),
                }
                for b in bookmarks
            ]

            return BookmarkSearchResult(
                bookmarks=results,
            ).model_dump()
        finally:
            session.close()
