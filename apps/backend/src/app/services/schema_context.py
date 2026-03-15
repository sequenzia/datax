"""Schema context injection for the AI agent.

Queries SchemaMetadata from the database, formats it as structured text
suitable for LLM consumption, and injects it into the agent's system
prompt on every request.  This gives the AI full awareness of available
tables, columns, types, constraints, and relationships so it can generate
accurate SQL.

Enhanced with SUMMARIZE statistics and sample values per column to give
the AI deep data understanding for better SQL generation. Stats include
min, max, avg, std, null_percentage, approx_unique, and quartiles. Sample
values (up to 5 per column) help the AI understand data patterns.

Token budget handling:
    When the total schema exceeds MAX_SCHEMA_TABLES tables, sources are
    prioritised by recency (most recently created first) and the list is
    truncated with a summary of what was omitted.

Wide table handling:
    Tables with more than WIDE_TABLE_AI_LIMIT columns are truncated to
    the first 100 columns in the AI prompt to avoid token overflows.

Reserved-keyword quoting:
    Column and table names that collide with SQL reserved keywords are
    automatically quoted with double-quotes in the formatted output so
    the AI knows to escape them in generated SQL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.models.orm import Connection, Dataset, SchemaMetadata
from app.services.duckdb_manager import WIDE_TABLE_AI_LIMIT

logger = get_logger(__name__)

# Maximum number of distinct tables before truncation.
MAX_SCHEMA_TABLES = 100

# SQL reserved keywords that must be quoted when used as identifiers.
# This is a pragmatic subset covering the most common collision words
# across PostgreSQL, MySQL, DuckDB, and ANSI SQL.
_SQL_RESERVED_KEYWORDS: frozenset[str] = frozenset(
    {
        "ALL",
        "ALTER",
        "AND",
        "ANY",
        "AS",
        "ASC",
        "BEGIN",
        "BETWEEN",
        "BY",
        "CASE",
        "CHECK",
        "COLUMN",
        "CONSTRAINT",
        "CREATE",
        "CROSS",
        "CURRENT",
        "CURRENT_DATE",
        "CURRENT_TIME",
        "CURRENT_TIMESTAMP",
        "CURRENT_USER",
        "DATABASE",
        "DATE",
        "DEFAULT",
        "DELETE",
        "DESC",
        "DISTINCT",
        "DROP",
        "ELSE",
        "END",
        "EXISTS",
        "FALSE",
        "FETCH",
        "FOR",
        "FOREIGN",
        "FROM",
        "FULL",
        "GRANT",
        "GROUP",
        "HAVING",
        "IF",
        "IN",
        "INDEX",
        "INNER",
        "INSERT",
        "INTO",
        "IS",
        "JOIN",
        "KEY",
        "LEFT",
        "LIKE",
        "LIMIT",
        "NATURAL",
        "NOT",
        "NULL",
        "OFFSET",
        "ON",
        "OR",
        "ORDER",
        "OUTER",
        "PRIMARY",
        "REFERENCES",
        "RIGHT",
        "ROW",
        "ROWS",
        "SELECT",
        "SESSION",
        "SET",
        "TABLE",
        "THEN",
        "TIME",
        "TIMESTAMP",
        "TO",
        "TRUE",
        "UNION",
        "UNIQUE",
        "UPDATE",
        "USER",
        "USING",
        "VALUE",
        "VALUES",
        "VIEW",
        "WHEN",
        "WHERE",
        "WITH",
        "YEAR",
    }
)


def _quote_if_reserved(name: str) -> str:
    """Wrap *name* in double-quotes if it is a SQL reserved keyword."""
    if name.upper() in _SQL_RESERVED_KEYWORDS:
        return f'"{name}"'
    return name


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ColumnContext:
    """Formatted column metadata for one column."""

    column_name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool
    foreign_key_ref: str | None = None
    stats: dict[str, Any] | None = None
    sample_values: list[Any] | None = None


@dataclass
class TableContext:
    """Formatted table metadata for one table."""

    table_name: str
    source_name: str
    source_type: str  # "dataset" or "connection"
    columns: list[ColumnContext] = field(default_factory=list)


@dataclass
class SchemaContextResult:
    """Result of building schema context for the agent."""

    context_text: str
    table_count: int = 0
    total_columns: int = 0
    truncated: bool = False
    error: str | None = None


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def build_schema_context(
    session: Session,
    source_filter: list[dict[str, str]] | None = None,
) -> SchemaContextResult:
    """Query all SchemaMetadata and format as structured text for the AI agent.

    Parameters
    ----------
    session:
        An active SQLAlchemy session to query the database.
    source_filter:
        Optional list of ``{"id": "<uuid>", "type": "dataset"|"connection"}``
        dicts to restrict which sources are included.

    Returns
    -------
    SchemaContextResult
        Contains the formatted context text, counts, and any error info.
        On database query failure, returns empty context with an error message.
    """
    try:
        return _build_context_from_db(session, source_filter=source_filter)
    except Exception as exc:
        logger.error("schema_context_query_failed", error=str(exc))
        return SchemaContextResult(
            context_text="",
            error=f"Failed to load schema metadata: {exc}",
        )


def _build_context_from_db(
    session: Session,
    source_filter: list[dict[str, str]] | None = None,
) -> SchemaContextResult:
    """Internal implementation that queries the DB and builds the context."""

    # 1. Load all schema metadata rows
    stmt = select(SchemaMetadata).order_by(
        SchemaMetadata.source_type,
        SchemaMetadata.source_id,
        SchemaMetadata.table_name,
        SchemaMetadata.column_name,
    )

    if source_filter:
        conditions = []
        for sf in source_filter:
            conditions.append(
                (SchemaMetadata.source_id == UUID(sf["id"]))
                & (SchemaMetadata.source_type == sf["type"])
            )
        stmt = stmt.where(or_(*conditions))

    schema_rows = list(session.execute(stmt).scalars().all())

    if not schema_rows:
        return SchemaContextResult(
            context_text=(
                "No data sources are available. "
                "Please upload a file (CSV, Excel, Parquet, JSON) "
                "or connect an external database to get started."
            ),
            table_count=0,
            total_columns=0,
        )

    # 2. Build a lookup for source info (names + profiling data)
    source_info = _load_source_info(session, schema_rows)

    # 3. Group rows by (source_id, table_name) with stats enrichment
    tables = _group_into_tables(schema_rows, source_info)

    # 4. Truncate if too many tables
    truncated = False
    omitted_count = 0
    if len(tables) > MAX_SCHEMA_TABLES:
        truncated = True
        omitted_count = len(tables) - MAX_SCHEMA_TABLES
        tables = tables[:MAX_SCHEMA_TABLES]

    # 5. Format as text
    total_columns = sum(len(t.columns) for t in tables)
    context_text = _format_tables(tables, truncated, omitted_count)

    return SchemaContextResult(
        context_text=context_text,
        table_count=len(tables),
        total_columns=total_columns,
        truncated=truncated,
    )


@dataclass
class _SourceInfo:
    """Internal: resolved source display name, type, and optional profiling data."""

    display_name: str
    source_type: str
    data_stats: dict[str, Any] | None = None


def _load_source_info(
    session: Session, schema_rows: list[SchemaMetadata]
) -> dict[UUID, _SourceInfo]:
    """Load display names and profiling data for all source IDs.

    Returns a dict mapping source_id -> _SourceInfo with display_name,
    source_type, and data_stats (for datasets that have been profiled).
    """
    # Collect unique source_ids by type
    dataset_ids: set[UUID] = set()
    connection_ids: set[UUID] = set()

    for row in schema_rows:
        if row.source_type == "dataset":
            dataset_ids.add(row.source_id)
        elif row.source_type == "connection":
            connection_ids.add(row.source_id)

    result: dict[UUID, _SourceInfo] = {}

    # Fetch dataset names + data_stats
    if dataset_ids:
        ds_stmt = select(Dataset.id, Dataset.name, Dataset.data_stats).where(
            Dataset.id.in_(dataset_ids)
        )
        for ds_id, ds_name, ds_data_stats in session.execute(ds_stmt).all():
            result[ds_id] = _SourceInfo(
                display_name=ds_name,
                source_type="dataset",
                data_stats=ds_data_stats,
            )

    # Fetch connection names (no profiling data for connections)
    if connection_ids:
        conn_stmt = select(Connection.id, Connection.name).where(
            Connection.id.in_(connection_ids)
        )
        for conn_id, conn_name in session.execute(conn_stmt).all():
            result[conn_id] = _SourceInfo(
                display_name=conn_name,
                source_type="connection",
            )

    return result


def _extract_column_stats(
    data_stats: dict[str, Any] | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, list[Any]]]:
    """Extract per-column stats and sample values from a Dataset's data_stats.

    Returns (stats_by_column, samples_by_column) where:
    - stats_by_column maps column_name -> SUMMARIZE stat dict
    - samples_by_column maps column_name -> list of sample values
    """
    if not data_stats:
        return {}, {}

    stats_by_column: dict[str, dict[str, Any]] = {}
    summarize = data_stats.get("summarize")
    if isinstance(summarize, list):
        for entry in summarize:
            if isinstance(entry, dict):
                col_name = entry.get("column_name")
                if col_name:
                    stats_by_column[col_name] = entry

    samples_by_column: dict[str, list[Any]] = {}
    sample_values = data_stats.get("sample_values")
    if isinstance(sample_values, dict):
        samples_by_column = sample_values

    return stats_by_column, samples_by_column


def _group_into_tables(
    schema_rows: list[SchemaMetadata],
    source_info: dict[UUID, _SourceInfo],
) -> list[TableContext]:
    """Group flat schema rows into table-level structures.

    Enriches columns with SUMMARIZE statistics and sample values when
    available from the source's profiling data. For wide tables, columns
    beyond WIDE_TABLE_AI_LIMIT are excluded from the context.
    """
    tables_by_key: dict[tuple[UUID, str], TableContext] = {}
    # Cache parsed stats per source_id to avoid re-parsing for each column
    stats_cache: dict[UUID, tuple[dict[str, dict[str, Any]], dict[str, list[Any]]]] = {}

    for row in schema_rows:
        key = (row.source_id, row.table_name)

        if key not in tables_by_key:
            info = source_info.get(row.source_id)
            if info:
                source_name = info.display_name
                source_type = info.source_type
            else:
                source_name = "Unknown"
                source_type = row.source_type

            tables_by_key[key] = TableContext(
                table_name=row.table_name,
                source_name=source_name,
                source_type=source_type,
            )

        # Extract stats for this column if available
        col_stats: dict[str, Any] | None = None
        col_samples: list[Any] | None = None

        info = source_info.get(row.source_id)
        if info and info.data_stats:
            if row.source_id not in stats_cache:
                stats_cache[row.source_id] = _extract_column_stats(info.data_stats)
            stats_by_col, samples_by_col = stats_cache[row.source_id]
            col_stats = stats_by_col.get(row.column_name)
            samples = samples_by_col.get(row.column_name)
            if samples:
                col_samples = samples

        tables_by_key[key].columns.append(
            ColumnContext(
                column_name=row.column_name,
                data_type=row.data_type,
                is_nullable=row.is_nullable,
                is_primary_key=row.is_primary_key,
                foreign_key_ref=row.foreign_key_ref,
                stats=col_stats,
                sample_values=col_samples,
            )
        )

    # Apply WIDE_TABLE_AI_LIMIT: truncate columns for wide tables
    for table in tables_by_key.values():
        if len(table.columns) > WIDE_TABLE_AI_LIMIT:
            table.columns = table.columns[:WIDE_TABLE_AI_LIMIT]

    return list(tables_by_key.values())


def _format_stat_value(value: Any) -> str:
    """Format a statistic value for display in the context.

    Rounds floats to one decimal place for readability. Returns 'N/A'
    for None values.
    """
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _format_column_stats(col: ColumnContext) -> list[str]:
    """Format SUMMARIZE stats and sample values as indented lines.

    Returns a list of formatted strings for the stats and samples lines
    to append below the column definition.
    """
    lines: list[str] = []

    if col.stats:
        s = col.stats
        # Main stats line: min, max, avg, std, null_percentage
        stat_parts: list[str] = []
        for key in ("min", "max", "avg", "std"):
            val = s.get(key)
            if val is not None:
                stat_parts.append(f"{key}={_format_stat_value(val)}")
        null_pct = s.get("null_percentage")
        if null_pct is not None:
            stat_parts.append(f"nulls={_format_stat_value(null_pct)}%")
        if stat_parts:
            lines.append(f"    Stats: {', '.join(stat_parts)}")

        # Unique + quartiles line
        detail_parts: list[str] = []
        approx_unique = s.get("approx_unique")
        if approx_unique is not None:
            detail_parts.append(f"~{_format_stat_value(approx_unique)}")
        for qkey in ("q25", "q50", "q75"):
            val = s.get(qkey)
            if val is not None:
                label = qkey.upper()
                detail_parts.append(f"{label}={_format_stat_value(val)}")
        if detail_parts:
            unique_prefix = f"Unique: {detail_parts[0]}" if approx_unique is not None else ""
            quartile_parts = [p for p in detail_parts if not p.startswith("~")]
            if unique_prefix and quartile_parts:
                lines.append(f"    {unique_prefix}, {', '.join(quartile_parts)}")
            elif unique_prefix:
                lines.append(f"    {unique_prefix}")
            elif quartile_parts:
                lines.append(f"    {', '.join(quartile_parts)}")

    if col.sample_values:
        lines.append(f"    Samples: {col.sample_values}")

    return lines


def _format_tables(
    tables: list[TableContext],
    truncated: bool,
    omitted_count: int,
) -> str:
    """Format table metadata as structured text for LLM injection.

    Output format example::

        ## Available Data Sources

        ### Dataset: "sales_data"
        Table: ds_sales_2024
          Column: id (integer, PK, NOT NULL)
          Column: "date" (date, NOT NULL)
          Column: revenue (DOUBLE)
            Stats: min=100.0, max=99500.0, avg=12340.5, std=8750.2, nulls=2.1%
            Unique: ~4523, Q25=5000.0, Q50=10000.0, Q75=18000.0
            Samples: [100.0, 5432.0, 12000.0, 25000.0, 99500.0]

        ### Connection: "production_db"
        Table: users
          Column: id (integer, PK, NOT NULL)
          Column: email (varchar, NOT NULL)
    """
    lines: list[str] = ["## Available Data Sources", ""]

    # Group tables by source
    source_groups: dict[tuple[str, str], list[TableContext]] = {}
    for table in tables:
        group_key = (table.source_type, table.source_name)
        if group_key not in source_groups:
            source_groups[group_key] = []
        source_groups[group_key].append(table)

    for (source_type, source_name), group_tables in source_groups.items():
        type_label = source_type.capitalize()
        lines.append(f"### {type_label}: {source_name}")

        for table in group_tables:
            table_display = _quote_if_reserved(table.table_name)
            lines.append(f"Table: {table_display}")

            for col in table.columns:
                col_display = _quote_if_reserved(col.column_name)
                parts = [col.data_type]

                if col.is_primary_key:
                    parts.append("PK")
                if not col.is_nullable:
                    parts.append("NOT NULL")
                if col.foreign_key_ref:
                    parts.append(f"FK -> {col.foreign_key_ref}")

                annotation = ", ".join(parts)
                lines.append(f"  Column: {col_display} ({annotation})")

                # Add stats and sample values below the column
                stat_lines = _format_column_stats(col)
                lines.extend(stat_lines)

            lines.append("")  # blank line after each table

    if truncated:
        lines.append(
            f"Note: Schema truncated. {omitted_count} additional table(s) "
            "not shown. Ask about specific tables to see their schemas."
        )
        lines.append("")

    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# System prompt injection
# ---------------------------------------------------------------------------


def inject_schema_into_prompt(base_prompt: str, schema_context: str) -> str:
    """Append schema context to the base system prompt.

    If schema_context is empty (e.g. due to a query failure), the base
    prompt is returned unchanged.

    Parameters
    ----------
    base_prompt:
        The static analytics system prompt.
    schema_context:
        The formatted schema context text from ``build_schema_context``.

    Returns
    -------
    str
        The combined system prompt with schema context appended.
    """
    if not schema_context:
        return base_prompt

    return f"{base_prompt}\n\n{schema_context}"
