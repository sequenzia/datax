"""Query execution, history, pagination, and cross-source query API endpoints.

Provides endpoints for executing raw SQL, getting EXPLAIN plans,
server-side pagination of query results, cross-source queries,
and viewing query execution history.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from app.errors import AppError
from app.logging import get_logger
from app.services.cross_source_query import CrossSourcePlan, SubQuery
from app.services.query_service import QueryService, is_read_only_sql

logger = get_logger(__name__)

router = APIRouter(prefix="/queries", tags=["queries"])


# ---------------------------------------------------------------------------
# Pydantic request/response schemas
# ---------------------------------------------------------------------------


class ExecuteRequest(BaseModel):
    """Request body for executing a SQL query."""

    sql: str = Field(..., min_length=1, description="SQL query to execute")
    source_id: uuid.UUID = Field(..., description="UUID of the dataset or connection")
    source_type: str = Field(..., description="Source type: 'dataset' or 'connection'")


class ExecuteResponse(BaseModel):
    """Response for a SQL query execution."""

    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    execution_time_ms: int


class ExplainRequest(BaseModel):
    """Request body for getting an EXPLAIN plan."""

    sql: str = Field(..., min_length=1, description="SQL query to explain")
    source_id: uuid.UUID = Field(..., description="UUID of the dataset or connection")
    source_type: str = Field(..., description="Source type: 'dataset' or 'connection'")


class ExplainResponse(BaseModel):
    """Response for an EXPLAIN plan."""

    plan: str


class PaginateRequest(BaseModel):
    """Request body for server-side pagination of query results."""

    sql: str = Field(..., min_length=1, description="SQL query to paginate")
    source_id: uuid.UUID = Field(..., description="UUID of the dataset or connection")
    source_type: str = Field(..., description="Source type: 'dataset' or 'connection'")
    offset: int = Field(default=0, ge=0, description="Number of rows to skip")
    limit: int = Field(default=100, ge=1, le=10_000, description="Maximum rows to return")
    sort_by: str | None = Field(None, description="Column name to sort by")
    sort_order: Literal["asc", "desc"] = Field(default="asc", description="Sort direction")


class PaginateResponse(BaseModel):
    """Response for paginated query results."""

    columns: list[str]
    rows: list[list[Any]]
    total_rows: int
    offset: int
    limit: int
    execution_time_ms: int


class CrossSourceSubQueryRequest(BaseModel):
    """A single sub-query within a cross-source request."""

    alias: str = Field(..., min_length=1, description="Temp table alias for join query")
    sql: str = Field(..., min_length=1, description="SQL to execute against the source")
    source_id: uuid.UUID = Field(..., description="UUID of the dataset or connection")
    source_type: str = Field(..., description="Source type: 'dataset' or 'connection'")


class CrossSourceExecuteRequest(BaseModel):
    """Request body for executing a cross-source query."""

    sub_queries: list[CrossSourceSubQueryRequest] = Field(
        ..., min_length=1, description="Sub-queries to execute per source"
    )
    join_sql: str = Field(
        ..., min_length=1, description="Final join SQL referencing sub-query aliases"
    )


class CrossSourceExecuteResponse(BaseModel):
    """Response for a cross-source query execution."""

    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    execution_time_ms: int
    sub_query_times_ms: dict[str, int]


class HistoryEntryResponse(BaseModel):
    """A single entry in query history."""

    sql: str
    source_id: str | None
    source_type: str | None
    row_count: int
    execution_time_ms: int
    status: str
    executed_at: str


class HistoryResponse(BaseModel):
    """Response for query history."""

    history: list[HistoryEntryResponse]
    total: int
    offset: int
    limit: int


# ---------------------------------------------------------------------------
# In-memory QueryService singleton per-app
# ---------------------------------------------------------------------------


def _get_query_service(request: Request) -> QueryService:
    """Get or create the QueryService from app state."""
    if not hasattr(request.app.state, "query_service"):
        settings = request.app.state.settings
        request.app.state.query_service = QueryService(
            duckdb_manager=request.app.state.duckdb_manager,
            connection_manager=request.app.state.connection_manager,
            max_query_timeout=settings.datax_max_query_timeout,
        )
    return request.app.state.query_service


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/execute")
def execute_query(
    body: ExecuteRequest,
    request: Request,
) -> ExecuteResponse:
    """Execute a raw SQL query against a dataset or connection.

    Routes to DuckDB for datasets and SQLAlchemy for connections.
    Enforces read-only mode and time limits.
    """
    if body.source_type not in ("dataset", "connection"):
        raise AppError(
            code="INVALID_SOURCE_TYPE",
            message=f"Invalid source_type '{body.source_type}'. Must be 'dataset' or 'connection'.",
            status_code=400,
        )

    if not is_read_only_sql(body.sql):
        raise AppError(
            code="READ_ONLY_VIOLATION",
            message="Only read-only SQL statements are allowed. "
            "INSERT, UPDATE, DELETE, DROP, and other write operations are not permitted.",
            status_code=400,
        )

    query_service = _get_query_service(request)
    result = query_service.execute(
        sql=body.sql,
        source_id=body.source_id,
        source_type=body.source_type,
    )

    if result.status == "timeout":
        raise AppError(
            code="QUERY_TIMEOUT",
            message=result.error_message or "Query exceeded the time limit.",
            status_code=408,
        )

    if result.error_message and "not found" in result.error_message.lower():
        raise AppError(
            code="SOURCE_NOT_FOUND",
            message=result.error_message,
            status_code=404,
        )

    if result.error_message and (
        "connection error" in result.error_message.lower()
        or "connection was lost" in result.error_message.lower()
    ):
        raise AppError(
            code="CONNECTION_ERROR",
            message=result.error_message,
            status_code=503,
        )

    if result.error_message:
        raise AppError(
            code="INVALID_SQL",
            message=result.error_message,
            status_code=400,
        )

    return ExecuteResponse(
        columns=result.columns,
        rows=result.rows,
        row_count=result.row_count,
        execution_time_ms=result.execution_time_ms,
    )


@router.post("/execute/cross-source")
def execute_cross_source_query(
    body: CrossSourceExecuteRequest,
    request: Request,
) -> CrossSourceExecuteResponse:
    """Execute a cross-source query that joins data from multiple sources.

    Decomposes the request into per-source sub-queries, executes them in
    parallel, loads results into DuckDB temp tables, and runs the final
    join in DuckDB.
    """
    # Validate all sub-query SQL is read-only
    for sq in body.sub_queries:
        if not is_read_only_sql(sq.sql):
            raise AppError(
                code="READ_ONLY_VIOLATION",
                message=(
                    f"Sub-query '{sq.alias}' contains write operations. "
                    "Only read-only SQL is allowed."
                ),
                status_code=400,
            )
        if sq.source_type not in ("dataset", "connection"):
            raise AppError(
                code="INVALID_SOURCE_TYPE",
                message=(
                    f"Sub-query '{sq.alias}' has invalid source_type "
                    f"'{sq.source_type}'. Must be 'dataset' or 'connection'."
                ),
                status_code=400,
            )

    if not is_read_only_sql(body.join_sql):
        raise AppError(
            code="READ_ONLY_VIOLATION",
            message="Join SQL contains write operations. Only read-only SQL is allowed.",
            status_code=400,
        )

    plan = CrossSourcePlan(
        sub_queries=[
            SubQuery(
                alias=sq.alias,
                sql=sq.sql,
                source_id=sq.source_id,
                source_type=sq.source_type,
            )
            for sq in body.sub_queries
        ],
        join_sql=body.join_sql,
    )

    query_service = _get_query_service(request)
    settings = request.app.state.settings
    result = query_service.execute_cross_source(
        plan,
        max_rows_per_subquery=settings.datax_max_cross_source_rows,
    )

    if result.status != "success":
        error_msg = result.error_message or "Cross-source query failed."
        if "not found" in error_msg.lower() or "not connected" in error_msg.lower():
            raise AppError(
                code="SOURCE_NOT_FOUND",
                message=error_msg,
                status_code=404,
            )
        if "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
            raise AppError(
                code="QUERY_TIMEOUT",
                message=error_msg,
                status_code=408,
            )
        if "connection lost" in error_msg.lower() or "connection was lost" in error_msg.lower():
            raise AppError(
                code="CONNECTION_ERROR",
                message=error_msg,
                status_code=503,
            )
        raise AppError(
            code="CROSS_SOURCE_ERROR",
            message=error_msg,
            status_code=400,
        )

    return CrossSourceExecuteResponse(
        columns=result.columns,
        rows=result.rows,
        row_count=result.row_count,
        execution_time_ms=result.execution_time_ms,
        sub_query_times_ms=result.sub_query_times_ms,
    )


@router.post("/explain")
def explain_query(
    body: ExplainRequest,
    request: Request,
) -> ExplainResponse:
    """Get the EXPLAIN plan for a SQL query.

    Routes to the appropriate data source.
    """
    if body.source_type not in ("dataset", "connection"):
        raise AppError(
            code="INVALID_SOURCE_TYPE",
            message=f"Invalid source_type '{body.source_type}'. Must be 'dataset' or 'connection'.",
            status_code=400,
        )

    query_service = _get_query_service(request)
    result = query_service.explain(
        sql=body.sql,
        source_id=body.source_id,
        source_type=body.source_type,
    )

    if result.error_message:
        if "not found" in result.error_message.lower():
            raise AppError(
                code="SOURCE_NOT_FOUND",
                message=result.error_message,
                status_code=404,
            )
        raise AppError(
            code="EXPLAIN_ERROR",
            message=result.error_message,
            status_code=400,
        )

    return ExplainResponse(plan=result.plan)


@router.post("/paginate")
def paginate_query(
    body: PaginateRequest,
    request: Request,
) -> PaginateResponse:
    """Paginate query results with server-side LIMIT/OFFSET.

    Re-executes the original SQL wrapped as a subquery with LIMIT/OFFSET
    and optional ORDER BY. Returns paginated rows and the total row count
    for the original query. Routes through DuckDB for datasets and
    SQLAlchemy for connections.
    """
    if body.source_type not in ("dataset", "connection"):
        raise AppError(
            code="INVALID_SOURCE_TYPE",
            message=f"Invalid source_type '{body.source_type}'. Must be 'dataset' or 'connection'.",
            status_code=400,
        )

    if not is_read_only_sql(body.sql):
        raise AppError(
            code="READ_ONLY_VIOLATION",
            message="Only read-only SQL statements are allowed. "
            "INSERT, UPDATE, DELETE, DROP, and other write operations are not permitted.",
            status_code=400,
        )

    query_service = _get_query_service(request)
    result = query_service.paginate(
        sql=body.sql,
        source_id=body.source_id,
        source_type=body.source_type,
        offset=body.offset,
        limit=body.limit,
        sort_by=body.sort_by,
        sort_order=body.sort_order,
    )

    if result.status == "timeout":
        raise AppError(
            code="QUERY_TIMEOUT",
            message=result.error_message or "Query exceeded the time limit.",
            status_code=408,
        )

    if result.error_message and "not found" in result.error_message.lower():
        raise AppError(
            code="SOURCE_NOT_FOUND",
            message=result.error_message,
            status_code=404,
        )

    if result.error_message:
        raise AppError(
            code="INVALID_SQL",
            message=result.error_message,
            status_code=400,
        )

    return PaginateResponse(
        columns=result.columns,
        rows=result.rows,
        total_rows=result.total_rows,
        offset=result.offset,
        limit=result.limit,
        execution_time_ms=result.execution_time_ms,
    )


@router.get("/history")
def get_query_history(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500, description="Max entries to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
) -> HistoryResponse:
    """Get query execution history with pagination.

    Returns recent queries sorted by execution time (newest first).
    """
    query_service = _get_query_service(request)
    entries, total = query_service.get_history(limit=limit, offset=offset)

    return HistoryResponse(
        history=[
            HistoryEntryResponse(
                sql=e.sql,
                source_id=e.source_id,
                source_type=e.source_type,
                row_count=e.row_count,
                execution_time_ms=e.execution_time_ms,
                status=e.status,
                executed_at=e.executed_at,
            )
            for e in entries
        ],
        total=total,
        offset=offset,
        limit=limit,
    )
