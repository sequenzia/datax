"""Query execution service.

Routes SQL queries to the appropriate data source (DuckDB for datasets,
SQLAlchemy for connections) with read-only enforcement and timeout handling.

For live database connections, statement-level timeouts are set per-query:
- PostgreSQL: ``SET LOCAL statement_timeout = '<ms>'``
- MySQL: ``SET SESSION max_execution_time = <ms>``

The timeout value comes from ``DATAX_MAX_QUERY_TIMEOUT`` (default 30s).
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.exc import DisconnectionError, OperationalError

from app.logging import get_logger
from app.models.connection import DatabaseType
from app.services.connection_manager import ConnectionManager
from app.services.cross_source_query import (
    CrossSourcePlan,
    CrossSourceQueryEngine,
    CrossSourceResult,
)
from app.services.duckdb_manager import DuckDBManager

logger = get_logger(__name__)

# SQL statements that modify data (case-insensitive).
_WRITE_KEYWORDS = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|MERGE|GRANT|REVOKE|RENAME)\b",
    re.IGNORECASE | re.MULTILINE,
)


def is_read_only_sql(sql: str) -> bool:
    """Return True if the SQL appears to be a read-only statement.

    Checks the first significant keyword. SELECT, WITH, EXPLAIN, SHOW,
    DESCRIBE, and PRAGMA are considered read-only.
    """
    stripped = sql.strip()
    if not stripped:
        return False
    return _WRITE_KEYWORDS.search(stripped) is None


@dataclass
class QueryResult:
    """Result of a query execution."""

    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    row_count: int = 0
    execution_time_ms: int = 0
    status: str = "success"
    error_message: str | None = None


@dataclass
class PaginatedResult:
    """Result of a paginated query execution."""

    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    total_rows: int = 0
    offset: int = 0
    limit: int = 100
    execution_time_ms: int = 0
    status: str = "success"
    error_message: str | None = None


@dataclass
class ExplainResult:
    """Result of an EXPLAIN plan request."""

    plan: str = ""
    error_message: str | None = None


@dataclass
class HistoryEntry:
    """A single query execution history record."""

    id: str = ""
    sql: str = ""
    source_id: str | None = None
    source_type: str | None = None
    row_count: int = 0
    execution_time_ms: int = 0
    status: str = "success"
    error_message: str | None = None
    executed_at: str = ""


class QueryService:
    """Orchestrates query execution across data sources.

    Maintains an in-memory query history. Delegates to DuckDBManager
    for dataset sources and ConnectionManager for connection sources.
    """

    def __init__(
        self,
        duckdb_manager: DuckDBManager,
        connection_manager: ConnectionManager,
        max_query_timeout: int = 30,
    ) -> None:
        self._duckdb = duckdb_manager
        self._conn_mgr = connection_manager
        self._max_query_timeout = max_query_timeout
        self._history: list[HistoryEntry] = []

    # ------------------------------------------------------------------
    # Cross-source execution
    # ------------------------------------------------------------------

    def execute_cross_source(
        self,
        plan: CrossSourcePlan,
        *,
        max_rows_per_subquery: int = 100_000,
    ) -> CrossSourceResult:
        """Execute a cross-source query plan.

        Delegates to ``CrossSourceQueryEngine`` for parallel sub-query
        execution, temp table loading, and final join.

        Args:
            plan: A ``CrossSourcePlan`` with sub-queries and join SQL.
            max_rows_per_subquery: Max rows per sub-query (memory guard).

        Returns:
            A ``CrossSourceResult`` with the unified join output.
        """
        engine = CrossSourceQueryEngine(self._duckdb, self._conn_mgr)
        return engine.execute(
            plan,
            timeout_seconds=self._max_query_timeout,
            max_rows_per_subquery=max_rows_per_subquery,
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        sql: str,
        source_id: uuid.UUID,
        source_type: str,
    ) -> QueryResult:
        """Execute a SQL query against the specified source.

        Enforces read-only mode and time limits.

        Args:
            sql: SQL query string.
            source_id: UUID of the dataset or connection.
            source_type: ``"dataset"`` or ``"connection"``.

        Returns:
            A QueryResult with columns, rows, and timing info.
        """
        if not is_read_only_sql(sql):
            return self._record_and_return_error(
                sql, source_id, source_type,
                "READ_ONLY_VIOLATION",
                "Only read-only SQL statements are allowed. "
                "INSERT, UPDATE, DELETE, DROP, and other write operations are not permitted.",
            )

        start = time.monotonic()

        if source_type == "dataset":
            return self._execute_duckdb(sql, source_id, start)
        elif source_type == "connection":
            return self._execute_connection(sql, source_id, start)
        else:
            return self._record_and_return_error(
                sql, source_id, source_type,
                "INVALID_SOURCE_TYPE",
                f"Invalid source_type '{source_type}'. Must be 'dataset' or 'connection'.",
            )

    # ------------------------------------------------------------------
    # Paginate
    # ------------------------------------------------------------------

    def paginate(
        self,
        sql: str,
        source_id: uuid.UUID,
        source_type: str,
        offset: int = 0,
        limit: int = 100,
        sort_by: str | None = None,
        sort_order: str = "asc",
    ) -> PaginatedResult:
        """Execute a paginated SQL query against the specified source.

        Wraps the original SQL in a subquery, applies optional ORDER BY,
        and adds LIMIT/OFFSET for server-side pagination. Also returns
        the total row count of the original query.

        Args:
            sql: Original SQL query string.
            source_id: UUID of the dataset or connection.
            source_type: ``"dataset"`` or ``"connection"``.
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.
            sort_by: Optional column name to sort by.
            sort_order: ``"asc"`` or ``"desc"`` (default ``"asc"``).

        Returns:
            A PaginatedResult with columns, rows, total count, and timing.
        """
        if not is_read_only_sql(sql):
            return PaginatedResult(
                status="error",
                error_message=(
                    "Only read-only SQL statements are allowed. "
                    "INSERT, UPDATE, DELETE, DROP, and other write operations are not permitted."
                ),
            )

        # Build the paginated SQL by wrapping the original as a subquery
        order_clause = ""
        if sort_by:
            # Sanitize sort_by to prevent injection (allow only alphanumeric + underscore)
            safe_sort_by = re.sub(r"[^a-zA-Z0-9_]", "", sort_by)
            if not safe_sort_by:
                return PaginatedResult(
                    status="error",
                    error_message=f"Invalid sort_by column name: {sort_by}",
                )
            direction = "DESC" if sort_order.lower() == "desc" else "ASC"
            order_clause = f" ORDER BY \"{safe_sort_by}\" {direction}"

        count_sql = f"SELECT COUNT(*) AS _total FROM ({sql}) AS _subq"
        paginated_sql = (
            f"SELECT * FROM ({sql}) AS _subq"
            f"{order_clause}"
            f" LIMIT {limit} OFFSET {offset}"
        )

        start = time.monotonic()

        if source_type == "dataset":
            return self._paginate_duckdb(
                count_sql, paginated_sql, source_id, offset, limit, start
            )
        elif source_type == "connection":
            return self._paginate_connection(
                count_sql, paginated_sql, source_id, offset, limit, start
            )
        else:
            return PaginatedResult(
                status="error",
                error_message=(
                    f"Invalid source_type '{source_type}'. "
                    "Must be 'dataset' or 'connection'."
                ),
            )

    def _paginate_duckdb(
        self,
        count_sql: str,
        paginated_sql: str,
        source_id: uuid.UUID,
        offset: int,
        limit: int,
        start: float,
    ) -> PaginatedResult:
        """Execute a paginated query via DuckDB."""
        try:
            # Get total count
            count_rows = self._duckdb.execute_query(count_sql)
            total_rows = count_rows[0]["_total"] if count_rows else 0

            # Get paginated rows
            rows_dicts = self._duckdb.execute_query(paginated_sql)
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            error_str = str(exc)
            if "timeout" in error_str.lower():
                return PaginatedResult(
                    execution_time_ms=elapsed_ms,
                    status="timeout",
                    error_message=f"Query exceeded the time limit of {self._max_query_timeout}s.",
                )
            return PaginatedResult(
                execution_time_ms=elapsed_ms,
                status="error",
                error_message=f"SQL error: {error_str}",
            )

        elapsed_ms = int((time.monotonic() - start) * 1000)

        if rows_dicts:
            columns = list(rows_dicts[0].keys())
            rows = [list(d.values()) for d in rows_dicts]
        else:
            columns = []
            rows = []

        return PaginatedResult(
            columns=columns,
            rows=rows,
            total_rows=total_rows,
            offset=offset,
            limit=limit,
            execution_time_ms=elapsed_ms,
        )

    def _paginate_connection(
        self,
        count_sql: str,
        paginated_sql: str,
        source_id: uuid.UUID,
        offset: int,
        limit: int,
        start: float,
    ) -> PaginatedResult:
        """Execute a paginated query via an external database connection."""
        engine = self._conn_mgr.get_engine(source_id)
        if engine is None:
            return PaginatedResult(
                status="error",
                error_message=f"Connection {source_id} not found or not connected.",
            )

        db_type = self._conn_mgr.get_db_type(source_id)
        timeout_ms = self._max_query_timeout * 1000

        try:
            with engine.connect() as conn:
                self._set_statement_timeout(conn, db_type, timeout_ms)

                # Get total count
                count_result = conn.execute(text(count_sql))
                total_rows = count_result.scalar() or 0

                # Get paginated rows
                result = conn.execute(text(paginated_sql))
                columns = list(result.keys())
                rows = [list(row) for row in result.fetchall()]
        except OperationalError as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            error_str = str(exc)
            if self._is_timeout_error(error_str):
                return PaginatedResult(
                    execution_time_ms=elapsed_ms,
                    status="timeout",
                    error_message=f"Query exceeded the time limit of {self._max_query_timeout}s.",
                )
            return PaginatedResult(
                execution_time_ms=elapsed_ms,
                status="error",
                error_message=f"Database connection error: {error_str}",
            )
        except DisconnectionError as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return PaginatedResult(
                execution_time_ms=elapsed_ms,
                status="error",
                error_message=f"Database connection was lost: {exc}",
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return PaginatedResult(
                execution_time_ms=elapsed_ms,
                status="error",
                error_message=f"SQL error: {exc}",
            )

        elapsed_ms = int((time.monotonic() - start) * 1000)

        return PaginatedResult(
            columns=columns,
            rows=rows,
            total_rows=total_rows,
            offset=offset,
            limit=limit,
            execution_time_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------
    # Explain
    # ------------------------------------------------------------------

    def explain(
        self,
        sql: str,
        source_id: uuid.UUID,
        source_type: str,
    ) -> ExplainResult:
        """Get the EXPLAIN plan for a SQL query.

        Args:
            sql: SQL query string.
            source_id: UUID of the dataset or connection.
            source_type: ``"dataset"`` or ``"connection"``.

        Returns:
            An ExplainResult with the plan text.
        """
        explain_sql = f"EXPLAIN {sql}"

        if source_type == "dataset":
            return self._explain_duckdb(explain_sql)
        elif source_type == "connection":
            return self._explain_connection(explain_sql, source_id)
        else:
            return ExplainResult(
                error_message=(
                    f"Invalid source_type '{source_type}'. "
                    "Must be 'dataset' or 'connection'."
                ),
            )

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(self, limit: int = 50, offset: int = 0) -> tuple[list[HistoryEntry], int]:
        """Return query execution history with pagination.

        Args:
            limit: Maximum number of entries to return.
            offset: Offset into the history list.

        Returns:
            Tuple of (entries, total_count).
        """
        total = len(self._history)
        # History is stored newest-first
        entries = self._history[offset : offset + limit]
        return entries, total

    # ------------------------------------------------------------------
    # Internal: DuckDB execution
    # ------------------------------------------------------------------

    def _execute_duckdb(
        self,
        sql: str,
        source_id: uuid.UUID,
        start: float,
    ) -> QueryResult:
        """Execute a query via DuckDB."""
        try:
            rows_dicts = self._duckdb.execute_query(sql)
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            error_str = str(exc)

            # Check for timeout-like errors
            if "timeout" in error_str.lower():
                return self._record_and_return_error(
                    sql, source_id, "dataset",
                    "QUERY_TIMEOUT",
                    f"Query exceeded the time limit of {self._max_query_timeout}s.",
                    elapsed_ms=elapsed_ms,
                    status_override="timeout",
                )

            return self._record_and_return_error(
                sql, source_id, "dataset",
                "QUERY_ERROR",
                f"SQL error: {error_str}",
                elapsed_ms=elapsed_ms,
            )

        elapsed_ms = int((time.monotonic() - start) * 1000)

        if rows_dicts:
            columns = list(rows_dicts[0].keys())
            rows = [list(d.values()) for d in rows_dicts]
        else:
            columns = []
            rows = []

        result = QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            execution_time_ms=elapsed_ms,
        )

        self._record_history(
            sql=sql,
            source_id=source_id,
            source_type="dataset",
            row_count=result.row_count,
            execution_time_ms=elapsed_ms,
            status="success",
        )

        return result

    # ------------------------------------------------------------------
    # Internal: Connection (SQLAlchemy) execution
    # ------------------------------------------------------------------

    def _execute_connection(
        self,
        sql: str,
        source_id: uuid.UUID,
        start: float,
    ) -> QueryResult:
        """Execute a query via an external database connection.

        Sets a per-statement timeout before executing the user SQL:
        - PostgreSQL: ``SET LOCAL statement_timeout = '<ms>'``
        - MySQL: ``SET SESSION max_execution_time = <ms>``

        Uses ``pool_pre_ping`` (configured on the engine) to detect stale
        connections before they cause query failures.
        """
        engine = self._conn_mgr.get_engine(source_id)
        if engine is None:
            return self._record_and_return_error(
                sql, source_id, "connection",
                "SOURCE_NOT_FOUND",
                f"Connection {source_id} not found or not connected.",
            )

        db_type = self._conn_mgr.get_db_type(source_id)
        timeout_ms = self._max_query_timeout * 1000

        try:
            with engine.connect() as conn:
                # Set database-level statement timeout so the server cancels
                # long-running queries even if the client is disconnected.
                self._set_statement_timeout(conn, db_type, timeout_ms)

                result = conn.execute(text(sql))
                columns = list(result.keys())
                rows = [list(row) for row in result.fetchall()]
        except OperationalError as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            error_str = str(exc)
            if self._is_timeout_error(error_str):
                return self._record_and_return_error(
                    sql, source_id, "connection",
                    "QUERY_TIMEOUT",
                    f"Query exceeded the time limit of {self._max_query_timeout}s.",
                    elapsed_ms=elapsed_ms,
                    status_override="timeout",
                )
            return self._record_and_return_error(
                sql, source_id, "connection",
                "CONNECTION_ERROR",
                f"Database connection error: {error_str}",
                elapsed_ms=elapsed_ms,
                status_override="error",
            )
        except DisconnectionError as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.warning(
                "connection_drop_detected",
                source_id=str(source_id),
                error=str(exc),
            )
            return self._record_and_return_error(
                sql, source_id, "connection",
                "CONNECTION_ERROR",
                f"Database connection was lost: {exc}",
                elapsed_ms=elapsed_ms,
                status_override="error",
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return self._record_and_return_error(
                sql, source_id, "connection",
                "QUERY_ERROR",
                f"SQL error: {exc}",
                elapsed_ms=elapsed_ms,
            )

        elapsed_ms = int((time.monotonic() - start) * 1000)

        result_obj = QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            execution_time_ms=elapsed_ms,
        )

        self._record_history(
            sql=sql,
            source_id=source_id,
            source_type="connection",
            row_count=result_obj.row_count,
            execution_time_ms=elapsed_ms,
            status="success",
        )

        return result_obj

    @staticmethod
    def _set_statement_timeout(
        conn: object,
        db_type: str | None,
        timeout_ms: int,
    ) -> None:
        """Set a per-statement execution timeout on the database connection.

        Uses the appropriate SQL command for each database dialect:
        - PostgreSQL: ``SET LOCAL statement_timeout`` (transaction-scoped)
        - MySQL: ``SET SESSION max_execution_time`` (session-scoped)

        Silently logs and continues if the timeout cannot be set (e.g.
        unsupported dialect or insufficient privileges).
        """
        try:
            if db_type == DatabaseType.POSTGRESQL:
                conn.execute(text(f"SET LOCAL statement_timeout = '{timeout_ms}'"))  # type: ignore[union-attr]
            elif db_type == DatabaseType.MYSQL:
                conn.execute(text(f"SET SESSION max_execution_time = {timeout_ms}"))  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning(
                "statement_timeout_set_failed",
                db_type=db_type,
                timeout_ms=timeout_ms,
                error=str(exc),
            )

    @staticmethod
    def _is_timeout_error(error_str: str) -> bool:
        """Return True if the error string indicates a query timeout."""
        lower = error_str.lower()
        return (
            "timeout" in lower
            or "timed out" in lower
            or "canceling statement" in lower
            or "statement_timeout" in lower
            or "max_execution_time" in lower
        )

    # ------------------------------------------------------------------
    # Internal: Explain helpers
    # ------------------------------------------------------------------

    def _explain_duckdb(self, explain_sql: str) -> ExplainResult:
        """Get EXPLAIN plan from DuckDB."""
        try:
            rows = self._duckdb.execute_query(explain_sql)
            plan_lines = []
            for row in rows:
                for value in row.values():
                    plan_lines.append(str(value))
            return ExplainResult(plan="\n".join(plan_lines))
        except Exception as exc:
            return ExplainResult(error_message=f"EXPLAIN failed: {exc}")

    def _explain_connection(
        self, explain_sql: str, source_id: uuid.UUID
    ) -> ExplainResult:
        """Get EXPLAIN plan from an external connection."""
        engine = self._conn_mgr.get_engine(source_id)
        if engine is None:
            return ExplainResult(
                error_message=f"Connection {source_id} not found or not connected.",
            )

        try:
            with engine.connect() as conn:
                result = conn.execute(text(explain_sql))
                plan_lines = []
                for row in result.fetchall():
                    plan_lines.append(" ".join(str(v) for v in row))
                return ExplainResult(plan="\n".join(plan_lines))
        except Exception as exc:
            return ExplainResult(error_message=f"EXPLAIN failed: {exc}")

    # ------------------------------------------------------------------
    # Internal: History recording
    # ------------------------------------------------------------------

    def _record_history(
        self,
        sql: str,
        source_id: uuid.UUID,
        source_type: str,
        row_count: int = 0,
        execution_time_ms: int = 0,
        status: str = "success",
        error_message: str | None = None,
    ) -> None:
        """Record a query execution in the in-memory history."""
        entry = HistoryEntry(
            id=str(uuid.uuid4()),
            sql=sql,
            source_id=str(source_id),
            source_type=source_type,
            row_count=row_count,
            execution_time_ms=execution_time_ms,
            status=status,
            error_message=error_message,
            executed_at=datetime.now(UTC).isoformat(),
        )
        # Prepend so newest is first
        self._history.insert(0, entry)

    def _record_and_return_error(
        self,
        sql: str,
        source_id: uuid.UUID,
        source_type: str,
        error_code: str,
        error_message: str,
        elapsed_ms: int = 0,
        status_override: str = "error",
    ) -> QueryResult:
        """Record a failed query and return an error QueryResult."""
        self._record_history(
            sql=sql,
            source_id=source_id,
            source_type=source_type,
            execution_time_ms=elapsed_ms,
            status=status_override,
            error_message=error_message,
        )
        return QueryResult(
            execution_time_ms=elapsed_ms,
            status=status_override,
            error_message=error_message,
        )
