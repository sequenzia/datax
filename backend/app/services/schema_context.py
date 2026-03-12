"""Schema context injection for the AI agent.

Queries SchemaMetadata from the database, formats it as structured text
suitable for LLM consumption, and injects it into the agent's system
prompt on every request.  This gives the AI full awareness of available
tables, columns, types, constraints, and relationships so it can generate
accurate SQL.

Token budget handling:
    When the total schema exceeds MAX_SCHEMA_TABLES tables, sources are
    prioritised by recency (most recently created first) and the list is
    truncated with a summary of what was omitted.

Reserved-keyword quoting:
    Column and table names that collide with SQL reserved keywords are
    automatically quoted with double-quotes in the formatted output so
    the AI knows to escape them in generated SQL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.models.orm import Connection, Dataset, SchemaMetadata

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


def build_schema_context(session: Session) -> SchemaContextResult:
    """Query all SchemaMetadata and format as structured text for the AI agent.

    Parameters
    ----------
    session:
        An active SQLAlchemy session to query the database.

    Returns
    -------
    SchemaContextResult
        Contains the formatted context text, counts, and any error info.
        On database query failure, returns empty context with an error message.
    """
    try:
        return _build_context_from_db(session)
    except Exception as exc:
        logger.error("schema_context_query_failed", error=str(exc))
        return SchemaContextResult(
            context_text="",
            error=f"Failed to load schema metadata: {exc}",
        )


def _build_context_from_db(session: Session) -> SchemaContextResult:
    """Internal implementation that queries the DB and builds the context."""

    # 1. Load all schema metadata rows
    stmt = select(SchemaMetadata).order_by(
        SchemaMetadata.source_type,
        SchemaMetadata.source_id,
        SchemaMetadata.table_name,
        SchemaMetadata.column_name,
    )
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

    # 2. Build a lookup for source names
    source_names = _load_source_names(session, schema_rows)

    # 3. Group rows by (source_id, table_name)
    tables = _group_into_tables(schema_rows, source_names)

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


def _load_source_names(
    session: Session, schema_rows: list[SchemaMetadata]
) -> dict[UUID, tuple[str, str]]:
    """Load display names for all source IDs referenced in schema rows.

    Returns a dict mapping source_id -> (display_name, source_type).
    """
    # Collect unique source_ids by type
    dataset_ids: set[UUID] = set()
    connection_ids: set[UUID] = set()

    for row in schema_rows:
        if row.source_type == "dataset":
            dataset_ids.add(row.source_id)
        elif row.source_type == "connection":
            connection_ids.add(row.source_id)

    result: dict[UUID, tuple[str, str]] = {}

    # Fetch dataset names
    if dataset_ids:
        ds_stmt = select(Dataset.id, Dataset.name).where(Dataset.id.in_(dataset_ids))
        for ds_id, ds_name in session.execute(ds_stmt).all():
            result[ds_id] = (ds_name, "dataset")

    # Fetch connection names
    if connection_ids:
        conn_stmt = select(Connection.id, Connection.name).where(
            Connection.id.in_(connection_ids)
        )
        for conn_id, conn_name in session.execute(conn_stmt).all():
            result[conn_id] = (conn_name, "connection")

    return result


def _group_into_tables(
    schema_rows: list[SchemaMetadata],
    source_names: dict[UUID, tuple[str, str]],
) -> list[TableContext]:
    """Group flat schema rows into table-level structures."""
    tables_by_key: dict[tuple[UUID, str], TableContext] = {}

    for row in schema_rows:
        key = (row.source_id, row.table_name)

        if key not in tables_by_key:
            source_name, source_type = source_names.get(
                row.source_id, ("Unknown", row.source_type)
            )
            tables_by_key[key] = TableContext(
                table_name=row.table_name,
                source_name=source_name,
                source_type=source_type,
            )

        tables_by_key[key].columns.append(
            ColumnContext(
                column_name=row.column_name,
                data_type=row.data_type,
                is_nullable=row.is_nullable,
                is_primary_key=row.is_primary_key,
                foreign_key_ref=row.foreign_key_ref,
            )
        )

    return list(tables_by_key.values())


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
          - id (integer, PK, NOT NULL)
          - "date" (date, NOT NULL)
          - amount (decimal, nullable)
          - customer_id (integer, NOT NULL, FK -> customers.id)

        ### Connection: "production_db"
        Table: users
          - id (integer, PK, NOT NULL)
          - "name" (varchar, NOT NULL)
          - email (varchar, NOT NULL, UNIQUE)
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
                lines.append(f"  - {col_display} ({annotation})")

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
