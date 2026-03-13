"""Cross-source query orchestration engine.

Decomposes a cross-source query into per-source sub-queries, executes them in
parallel, loads live DB results into DuckDB temporary tables, runs the final
join in DuckDB, and returns a unified result.

Architecture:
1. Accept a ``CrossSourcePlan`` describing per-source sub-queries and a
   final join query referencing temporary table aliases.
2. Execute sub-queries in parallel using ``concurrent.futures.ThreadPoolExecutor``.
3. Load each sub-query result into a DuckDB temp table.
4. Execute the final join query in DuckDB.
5. Clean up temp tables on completion (success or failure).

This module does NOT parse SQL to determine which sources are involved.
The caller (typically the AI agent service) provides a structured plan.
"""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import text
from sqlalchemy.exc import DisconnectionError, OperationalError

from app.logging import get_logger
from app.models.connection import DatabaseType
from app.services.connection_manager import ConnectionManager
from app.services.duckdb_manager import DuckDBManager

logger = get_logger(__name__)

# Default row limit per sub-query to prevent DuckDB memory pressure.
DEFAULT_MAX_SUBQUERY_ROWS = 100_000


class SubQuerySourceType(StrEnum):
    """Source type for a sub-query."""
    DATASET = "dataset"
    CONNECTION = "connection"


@dataclass
class SubQuery:
    """A single sub-query within a cross-source plan.

    Attributes:
        alias: Temp table alias used in the final join query.
        sql: SQL to execute against the source.
        source_id: UUID of the dataset or connection.
        source_type: ``"dataset"`` or ``"connection"``.
    """
    alias: str
    sql: str
    source_id: uuid.UUID
    source_type: str


@dataclass
class CrossSourcePlan:
    """Describes a cross-source query: sub-queries + final join.

    Attributes:
        sub_queries: List of per-source sub-queries.
        join_sql: Final SQL query referencing sub-query aliases as table names.
    """
    sub_queries: list[SubQuery]
    join_sql: str


@dataclass
class SubQueryResult:
    """Result of a single sub-query execution."""
    alias: str
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    row_count: int = 0
    execution_time_ms: int = 0
    error_message: str | None = None
    truncated: bool = False


@dataclass
class CrossSourceResult:
    """Result of a cross-source query execution."""
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    row_count: int = 0
    execution_time_ms: int = 0
    status: str = "success"
    error_message: str | None = None
    sub_query_times_ms: dict[str, int] = field(default_factory=dict)


def _resolve_column_collisions(columns: list[str], alias: str) -> list[str]:
    """Prefix duplicate column names with the sub-query alias.

    If a column name appears more than once within a single sub-query result
    set (unlikely but possible with ``SELECT *`` across JOINs inside a
    sub-query), append ``_{alias}_{n}`` to disambiguate.

    For cross-sub-query collisions, the final join SQL is expected to alias
    explicitly. This helper ensures within-result uniqueness needed to create
    the DuckDB temp table.
    """
    seen: dict[str, int] = {}
    resolved: list[str] = []
    for col in columns:
        count = seen.get(col, 0)
        if count > 0:
            resolved.append(f"{col}_{alias}_{count}")
        else:
            resolved.append(col)
        seen[col] = count + 1
    return resolved


class CrossSourceQueryEngine:
    """Orchestrates cross-source queries across DuckDB and live databases.

    Usage::

        engine = CrossSourceQueryEngine(duckdb_mgr, conn_mgr)
        result = engine.execute(plan, timeout_seconds=30, max_rows=100_000)
    """

    def __init__(
        self,
        duckdb_manager: DuckDBManager,
        connection_manager: ConnectionManager,
    ) -> None:
        self._duckdb = duckdb_manager
        self._conn_mgr = connection_manager

    def execute(
        self,
        plan: CrossSourcePlan,
        *,
        timeout_seconds: int = 30,
        max_rows_per_subquery: int = DEFAULT_MAX_SUBQUERY_ROWS,
    ) -> CrossSourceResult:
        """Execute a cross-source query plan.

        Steps:
        1. Execute DuckDB sub-queries sequentially (DuckDB is not thread-safe).
        2. Execute connection sub-queries in parallel via thread pool.
        3. If any sub-query fails, abort and return the error.
        4. Load live DB results into DuckDB temp tables.
        5. Execute the final join query in DuckDB.
        6. Clean up temp tables.

        Args:
            plan: The cross-source query plan.
            timeout_seconds: Timeout for each sub-query.
            max_rows_per_subquery: Max rows per sub-query (memory guard).

        Returns:
            A ``CrossSourceResult`` with the unified join output.
        """
        overall_start = time.monotonic()
        temp_tables: list[str] = []

        try:
            # Separate DuckDB and connection sub-queries
            duckdb_sqs = [
                sq for sq in plan.sub_queries
                if sq.source_type == SubQuerySourceType.DATASET
            ]
            conn_sqs = [
                sq for sq in plan.sub_queries
                if sq.source_type == SubQuerySourceType.CONNECTION
            ]
            other_sqs = [
                sq for sq in plan.sub_queries
                if sq.source_type not in (
                    SubQuerySourceType.DATASET, SubQuerySourceType.CONNECTION,
                )
            ]

            # Step 1: Execute DuckDB sub-queries sequentially (not thread-safe)
            duckdb_results: list[SubQueryResult] = []
            for sq in duckdb_sqs:
                start = time.monotonic()
                duckdb_results.append(
                    self._execute_subquery_duckdb(sq, start, max_rows_per_subquery)
                )

            # Step 2: Execute connection sub-queries in parallel
            conn_results = self._execute_subqueries_parallel(
                conn_sqs,
                timeout_seconds=timeout_seconds,
                max_rows=max_rows_per_subquery,
            ) if conn_sqs else []

            # Handle invalid source types
            other_results = [
                SubQueryResult(
                    alias=sq.alias,
                    error_message=(
                        f"Invalid source_type '{sq.source_type}' "
                        f"for sub-query '{sq.alias}'"
                    ),
                )
                for sq in other_sqs
            ]

            sub_results = duckdb_results + conn_results + other_results

            # Step 2: Check for failures - abort all if any failed
            for sr in sub_results:
                if sr.error_message is not None:
                    elapsed = int((time.monotonic() - overall_start) * 1000)
                    return CrossSourceResult(
                        execution_time_ms=elapsed,
                        status="error",
                        error_message=(
                            f"Sub-query '{sr.alias}' failed: {sr.error_message}"
                        ),
                        sub_query_times_ms={
                            r.alias: r.execution_time_ms for r in sub_results
                        },
                    )

            # Step 3: Load results into DuckDB temp tables
            for sr in sub_results:
                resolved_cols = _resolve_column_collisions(sr.columns, sr.alias)
                self._create_temp_table(sr.alias, resolved_cols, sr.rows)
                temp_tables.append(sr.alias)

            # Step 4: Execute the final join query in DuckDB
            join_result = self._execute_join(plan.join_sql)

            elapsed = int((time.monotonic() - overall_start) * 1000)

            if join_result.error_message is not None:
                return CrossSourceResult(
                    execution_time_ms=elapsed,
                    status="error",
                    error_message=f"Join query failed: {join_result.error_message}",
                    sub_query_times_ms={
                        r.alias: r.execution_time_ms for r in sub_results
                    },
                )

            return CrossSourceResult(
                columns=join_result.columns,
                rows=join_result.rows,
                row_count=join_result.row_count,
                execution_time_ms=elapsed,
                status="success",
                sub_query_times_ms={
                    r.alias: r.execution_time_ms for r in sub_results
                },
            )

        finally:
            # Step 5: Always clean up temp tables
            for table_name in temp_tables:
                self._drop_temp_table(table_name)

    # ------------------------------------------------------------------
    # Internal: Parallel sub-query execution
    # ------------------------------------------------------------------

    def _execute_subqueries_parallel(
        self,
        sub_queries: list[SubQuery],
        *,
        timeout_seconds: int,
        max_rows: int,
    ) -> list[SubQueryResult]:
        """Execute connection sub-queries in parallel using a thread pool.

        DuckDB sub-queries must be executed sequentially in the caller
        because DuckDB connections are not thread-safe.

        If any sub-query times out or fails, returns the error in its
        ``SubQueryResult``. The caller decides whether to abort.
        """
        results: list[SubQueryResult] = [
            SubQueryResult(alias=sq.alias) for sq in sub_queries
        ]
        idx_map: dict[str, int] = {
            sq.alias: i for i, sq in enumerate(sub_queries)
        }

        with ThreadPoolExecutor(max_workers=max(1, len(sub_queries))) as executor:
            futures = {
                executor.submit(
                    self._execute_subquery_connection,
                    sq,
                    time.monotonic(),
                    timeout_seconds,
                    max_rows,
                ): sq.alias
                for sq in sub_queries
            }

            try:
                for future in as_completed(futures, timeout=timeout_seconds + 5):
                    alias = futures[future]
                    idx = idx_map[alias]
                    try:
                        results[idx] = future.result()
                    except Exception as exc:
                        results[idx] = SubQueryResult(
                            alias=alias,
                            error_message=f"Unexpected error: {exc}",
                        )
            except TimeoutError:
                # Cancel remaining futures
                for future in futures:
                    future.cancel()
                # Mark all unfinished sub-queries as timed out
                for future, alias in futures.items():
                    idx = idx_map[alias]
                    if not future.done():
                        results[idx] = SubQueryResult(
                            alias=alias,
                            error_message=(
                                f"Sub-query timed out after {timeout_seconds}s"
                            ),
                        )

        return results

    def _execute_subquery_duckdb(
        self,
        sub_query: SubQuery,
        start: float,
        max_rows: int,
    ) -> SubQueryResult:
        """Execute a sub-query against DuckDB.

        Uses the raw DuckDB connection to preserve column metadata even
        for empty result sets (``execute_query`` returns ``[]`` for zero
        rows, losing column info).
        """
        try:
            result = self._duckdb._conn.execute(sub_query.sql)
            columns = [desc[0] for desc in result.description]
            raw_rows = result.fetchall()
            all_rows = [list(row) for row in raw_rows]
        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            return SubQueryResult(
                alias=sub_query.alias,
                execution_time_ms=elapsed,
                error_message=f"DuckDB query error: {exc}",
            )

        elapsed = int((time.monotonic() - start) * 1000)

        truncated = len(all_rows) > max_rows
        if truncated:
            original_count = len(all_rows)
            all_rows = all_rows[:max_rows]
            logger.warning(
                "subquery_result_truncated",
                alias=sub_query.alias,
                max_rows=max_rows,
                original_count=original_count,
            )

        return SubQueryResult(
            alias=sub_query.alias,
            columns=columns,
            rows=all_rows,
            row_count=len(all_rows),
            execution_time_ms=elapsed,
            truncated=truncated,
        )

    def _execute_subquery_connection(
        self,
        sub_query: SubQuery,
        start: float,
        timeout_seconds: int,
        max_rows: int,
    ) -> SubQueryResult:
        """Execute a sub-query against a live database connection."""
        engine = self._conn_mgr.get_engine(sub_query.source_id)
        if engine is None:
            elapsed = int((time.monotonic() - start) * 1000)
            return SubQueryResult(
                alias=sub_query.alias,
                execution_time_ms=elapsed,
                error_message=(
                    f"Connection {sub_query.source_id} not found or not connected."
                ),
            )

        db_type = self._conn_mgr.get_db_type(sub_query.source_id)
        timeout_ms = timeout_seconds * 1000

        try:
            with engine.connect() as conn:
                self._set_statement_timeout(conn, db_type, timeout_ms)
                result = conn.execute(text(sub_query.sql))
                columns = list(result.keys())
                all_rows = [list(row) for row in result.fetchall()]
        except OperationalError as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            error_str = str(exc).lower()
            if "timeout" in error_str or "canceling statement" in error_str:
                return SubQueryResult(
                    alias=sub_query.alias,
                    execution_time_ms=elapsed,
                    error_message=(
                        f"Sub-query timed out after {timeout_seconds}s"
                    ),
                )
            return SubQueryResult(
                alias=sub_query.alias,
                execution_time_ms=elapsed,
                error_message=f"Database error: {exc}",
            )
        except DisconnectionError as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            return SubQueryResult(
                alias=sub_query.alias,
                execution_time_ms=elapsed,
                error_message=f"Connection lost: {exc}",
            )
        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            return SubQueryResult(
                alias=sub_query.alias,
                execution_time_ms=elapsed,
                error_message=f"Query error: {exc}",
            )

        elapsed = int((time.monotonic() - start) * 1000)

        truncated = len(all_rows) > max_rows
        if truncated:
            all_rows = all_rows[:max_rows]
            logger.warning(
                "subquery_result_truncated",
                alias=sub_query.alias,
                max_rows=max_rows,
                original_count=len(all_rows) + (len(all_rows) - max_rows),
            )

        return SubQueryResult(
            alias=sub_query.alias,
            columns=columns,
            rows=all_rows,
            row_count=len(all_rows),
            execution_time_ms=elapsed,
            truncated=truncated,
        )

    # ------------------------------------------------------------------
    # Internal: DuckDB temp table management
    # ------------------------------------------------------------------

    def _create_temp_table(
        self,
        alias: str,
        columns: list[str],
        rows: list[list],
    ) -> None:
        """Create a DuckDB temporary table from sub-query results.

        Uses ``CREATE TEMP TABLE`` + ``INSERT INTO`` to load data.
        All columns are created as VARCHAR; DuckDB will cast as needed
        during the final join query.
        """
        if not columns:
            # No columns at all -- create a dummy empty table
            self._duckdb._conn.execute(
                f'CREATE TEMP TABLE IF NOT EXISTS "{alias}" AS SELECT 1 WHERE false'
            )
            return

        # Sanitize column names for DDL
        safe_cols = [f'"{c}"' for c in columns]
        col_defs = ", ".join(f"{c} VARCHAR" for c in safe_cols)

        self._duckdb._conn.execute(
            f'CREATE TEMP TABLE IF NOT EXISTS "{alias}" ({col_defs})'
        )

        # Batch insert rows (skip if empty -- table structure still exists)
        if rows:
            placeholders = ", ".join("?" for _ in columns)
            insert_sql = (
                f'INSERT INTO "{alias}" VALUES ({placeholders})'
            )
            self._duckdb._conn.executemany(insert_sql, rows)

    def _drop_temp_table(self, alias: str) -> None:
        """Drop a temporary table, ignoring errors."""
        try:
            self._duckdb._conn.execute(f'DROP TABLE IF EXISTS "{alias}"')
        except Exception as exc:
            logger.warning(
                "temp_table_drop_failed",
                alias=alias,
                error=str(exc),
            )

    def _execute_join(self, join_sql: str) -> SubQueryResult:
        """Execute the final join query in DuckDB."""
        start = time.monotonic()
        try:
            rows_dicts = self._duckdb.execute_query(join_sql)
        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            return SubQueryResult(
                alias="__join__",
                execution_time_ms=elapsed,
                error_message=str(exc),
            )

        elapsed = int((time.monotonic() - start) * 1000)

        if rows_dicts:
            columns = list(rows_dicts[0].keys())
            rows = [list(d.values()) for d in rows_dicts]
        else:
            columns = []
            rows = []

        return SubQueryResult(
            alias="__join__",
            columns=columns,
            rows=rows,
            row_count=len(rows),
            execution_time_ms=elapsed,
        )

    # ------------------------------------------------------------------
    # Internal: Statement timeout (duplicated from QueryService to
    # avoid circular imports; could be extracted to a shared util)
    # ------------------------------------------------------------------

    @staticmethod
    def _set_statement_timeout(
        conn: object,
        db_type: str | None,
        timeout_ms: int,
    ) -> None:
        """Set a per-statement execution timeout on the database connection."""
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
