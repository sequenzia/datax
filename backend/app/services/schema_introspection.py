"""Schema introspection service for external database connections.

Discovers tables, views, columns, types, primary keys, and foreign key
relationships from connected PostgreSQL and MySQL databases using
SQLAlchemy Inspector.  Normalises database-specific types into a small
set of portable type names so the AI agent can reason about schemas
without caring which engine backs the data.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from app.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Normalised type mapping
# ---------------------------------------------------------------------------

# Maps fragments found in str(column_type) to a normalised type name.
# Order matters: first match wins.  More specific patterns must appear
# before more general ones (e.g. "BIGINT" before "INT").
_TYPE_MAP: list[tuple[str, str]] = [
    # Boolean
    ("BOOLEAN", "boolean"),
    ("BOOL", "boolean"),
    ("TINYINT(1)", "boolean"),  # MySQL convention
    # Date / time (before integers so INTERVAL doesn't match INT)
    ("TIMESTAMPTZ", "timestamptz"),
    ("TIMESTAMP WITH TIME ZONE", "timestamptz"),
    ("TIMESTAMP WITHOUT TIME ZONE", "timestamp"),
    ("TIMESTAMP", "timestamp"),
    ("DATETIME", "timestamp"),
    ("DATE", "date"),
    ("TIME WITH TIME ZONE", "timetz"),
    ("TIMETZ", "timetz"),
    ("INTERVAL", "interval"),
    ("TIME", "time"),
    ("YEAR", "integer"),
    # Integer types (order: most specific first, BIGSERIAL before SERIAL)
    ("BIGSERIAL", "bigint"),
    ("SMALLSERIAL", "smallint"),
    ("SERIAL", "integer"),
    ("BIGINT", "bigint"),
    ("SMALLINT", "smallint"),
    ("MEDIUMINT", "integer"),
    ("TINYINT", "smallint"),
    ("INTEGER", "integer"),
    ("INT", "integer"),
    # Floating point
    ("DOUBLE PRECISION", "float"),
    ("DOUBLE", "float"),
    ("FLOAT", "float"),
    ("REAL", "float"),
    # Fixed precision
    ("NUMERIC", "decimal"),
    ("DECIMAL", "decimal"),
    ("MONEY", "decimal"),
    # Text
    ("CHARACTER VARYING", "varchar"),
    ("VARCHAR", "varchar"),
    ("NVARCHAR", "varchar"),
    ("NCHAR", "char"),
    ("CHAR", "char"),
    ("LONGTEXT", "text"),
    ("MEDIUMTEXT", "text"),
    ("TINYTEXT", "text"),
    ("TEXT", "text"),
    ("CLOB", "text"),
    ("STRING", "text"),
    # Binary
    ("BYTEA", "binary"),
    ("BLOB", "binary"),
    ("LONGBLOB", "binary"),
    ("MEDIUMBLOB", "binary"),
    ("TINYBLOB", "binary"),
    ("VARBINARY", "binary"),
    ("BINARY", "binary"),
    # UUID
    ("UUID", "uuid"),
    # JSON
    ("JSONB", "jsonb"),
    ("JSON", "json"),
    # Array (PostgreSQL)
    ("ARRAY", "array"),
    # Network (PostgreSQL)
    ("INET", "text"),
    ("CIDR", "text"),
    ("MACADDR", "text"),
    # Enum (appears as "user_defined" or "enum" in many drivers)
    ("ENUM", "text"),
    ("USER-DEFINED", "text"),
]

# System schemas to exclude when listing tables / views.
_SYSTEM_SCHEMAS: set[str] = {
    # PostgreSQL
    "pg_catalog",
    "information_schema",
    "pg_toast",
    # MySQL (shown as separate databases, but can appear as schemas)
    "mysql",
    "performance_schema",
    "sys",
    "information_schema",
}


def normalise_type(raw_type: str) -> str:
    """Map a database-specific type string to a normalised type name.

    The mapping is case-insensitive and uses substring matching so that
    parameterised types (e.g. ``VARCHAR(255)``) resolve correctly.

    Falls back to ``"text"`` for completely unrecognised types.
    """
    upper = raw_type.upper()
    for fragment, normalised in _TYPE_MAP:
        if fragment in upper:
            return normalised
    return "text"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ColumnInfo:
    """Schema information for a single column."""

    table_name: str
    column_name: str
    data_type: str  # normalised type
    raw_type: str  # original database type string
    is_nullable: bool
    is_primary_key: bool
    is_view: bool = False
    foreign_key_ref: str | None = None


@dataclass
class IntrospectionResult:
    """Result of schema introspection."""

    success: bool
    columns: list[ColumnInfo] = field(default_factory=list)
    table_count: int = 0
    view_count: int = 0
    error_message: str | None = None
    error_type: str | None = None


# ---------------------------------------------------------------------------
# Core introspection
# ---------------------------------------------------------------------------


def _is_system_schema(schema: str | None) -> bool:
    """Return True if *schema* is a known system schema to skip."""
    if schema is None:
        return False
    return schema.lower() in _SYSTEM_SCHEMAS


def introspect_engine(
    engine: Engine,
    *,
    schema: str | None = None,
    include_views: bool = True,
) -> IntrospectionResult:
    """Introspect an engine and return column-level metadata.

    Parameters
    ----------
    engine:
        A SQLAlchemy engine connected to the target database.
    schema:
        Optional schema name.  ``None`` uses the database default.
    include_views:
        Whether to include database views alongside tables.

    Returns
    -------
    IntrospectionResult
        On success, contains a list of ``ColumnInfo`` objects.
        On failure, ``success`` is False and ``error_message`` is set.
    """
    if _is_system_schema(schema):
        return IntrospectionResult(success=True)

    try:
        insp = inspect(engine)

        # Gather table names
        table_names: list[str] = insp.get_table_names(schema=schema)

        # Gather view names
        view_names: list[str] = []
        if include_views:
            view_names = insp.get_view_names(schema=schema)

        columns: list[ColumnInfo] = []

        # Process tables
        for table_name in table_names:
            _introspect_relation(
                insp,
                table_name,
                schema=schema,
                is_view=False,
                columns=columns,
            )

        # Process views
        for view_name in view_names:
            _introspect_relation(
                insp,
                view_name,
                schema=schema,
                is_view=True,
                columns=columns,
            )

        logger.info(
            "schema_introspection_success",
            table_count=len(table_names),
            view_count=len(view_names),
            column_count=len(columns),
            schema=schema,
        )

        return IntrospectionResult(
            success=True,
            columns=columns,
            table_count=len(table_names),
            view_count=len(view_names),
        )

    except OperationalError as exc:
        error_str = str(exc)
        if "permission denied" in error_str.lower() or "access denied" in error_str.lower():
            error_type = "permission_denied"
        elif (
            "connection" in error_str.lower()
            or "closed" in error_str.lower()
            or "lost" in error_str.lower()
        ):
            error_type = "connection_lost"
        else:
            error_type = "introspection_error"

        logger.warning(
            "schema_introspection_failed",
            error_type=error_type,
            error=error_str,
            schema=schema,
        )
        return IntrospectionResult(
            success=False,
            error_message=error_str,
            error_type=error_type,
        )

    except Exception as exc:
        logger.error(
            "schema_introspection_error",
            error=str(exc),
            schema=schema,
        )
        return IntrospectionResult(
            success=False,
            error_message=str(exc),
            error_type="introspection_error",
        )


def _introspect_relation(
    insp,
    name: str,
    *,
    schema: str | None,
    is_view: bool,
    columns: list[ColumnInfo],
) -> None:
    """Introspect a single table or view and append columns to *columns*.

    Gracefully skips relations that cannot be inspected (e.g. permission
    denied on a specific table) and logs a warning.
    """
    try:
        # Primary keys (views don't have PK constraints, but we still query
        # to be defensive)
        pk_columns: set[str] = set()
        if not is_view:
            pk_constraint = insp.get_pk_constraint(name, schema=schema)
            if pk_constraint:
                pk_columns = set(pk_constraint.get("constrained_columns", []))

        # Foreign keys
        fk_map: dict[str, str] = {}
        if not is_view:
            for fk in insp.get_foreign_keys(name, schema=schema):
                ref_table = fk.get("referred_table", "")
                ref_schema = fk.get("referred_schema")
                ref_cols = fk.get("referred_columns", [])
                for col_name in fk.get("constrained_columns", []):
                    if ref_schema and ref_schema != schema:
                        if ref_cols:
                            ref_str = f"{ref_schema}.{ref_table}.{ref_cols[0]}"
                        else:
                            ref_str = ref_table
                    else:
                        ref_str = f"{ref_table}.{ref_cols[0]}" if ref_cols else ref_table
                    fk_map[col_name] = ref_str

        # Columns
        for col in insp.get_columns(name, schema=schema):
            raw_type = str(col["type"])
            columns.append(
                ColumnInfo(
                    table_name=name,
                    column_name=col["name"],
                    data_type=normalise_type(raw_type),
                    raw_type=raw_type,
                    is_nullable=col.get("nullable", True),
                    is_primary_key=col["name"] in pk_columns,
                    is_view=is_view,
                    foreign_key_ref=fk_map.get(col["name"]),
                )
            )
    except Exception as exc:
        logger.warning(
            "schema_relation_introspection_skipped",
            relation=name,
            is_view=is_view,
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# SchemaMetadata persistence helpers
# ---------------------------------------------------------------------------


def columns_to_schema_records(
    source_id: uuid.UUID,
    columns: list[ColumnInfo],
) -> list[dict]:
    """Convert a list of ColumnInfo to dicts suitable for SchemaMetadata rows.

    Each dict contains the fields expected by the SchemaMetadata ORM model,
    ready for bulk insertion.
    """
    records: list[dict] = []
    for col in columns:
        records.append(
            {
                "id": uuid.uuid4(),
                "source_id": source_id,
                "source_type": "connection",
                "table_name": col.table_name,
                "column_name": col.column_name,
                "data_type": col.data_type,
                "is_nullable": col.is_nullable,
                "is_primary_key": col.is_primary_key,
                "foreign_key_ref": col.foreign_key_ref,
            }
        )
    return records


def store_schema_metadata(
    session,
    source_id: uuid.UUID,
    columns: list[ColumnInfo],
) -> int:
    """Persist introspected schema as SchemaMetadata rows.

    Replaces any existing rows for the given *source_id* so that a
    "refresh schema" operation is idempotent.

    Parameters
    ----------
    session:
        An active SQLAlchemy Session.
    source_id:
        The UUID of the Connection this schema belongs to.
    columns:
        Column metadata from introspection.

    Returns
    -------
    int
        Number of SchemaMetadata rows created.
    """
    from app.models.orm import SchemaMetadata

    # Delete existing metadata for this connection
    session.query(SchemaMetadata).filter(
        SchemaMetadata.source_id == source_id,
        SchemaMetadata.source_type == "connection",
    ).delete()

    # Bulk insert new metadata
    records = columns_to_schema_records(source_id, columns)
    for rec in records:
        row = SchemaMetadata(
            id=rec["id"],
            source_id=rec["source_id"],
            source_type=rec["source_type"],
            table_name=rec["table_name"],
            column_name=rec["column_name"],
            data_type=rec["data_type"],
            is_nullable=rec["is_nullable"],
            is_primary_key=rec["is_primary_key"],
            foreign_key_ref=rec["foreign_key_ref"],
        )
        session.add(row)

    session.flush()

    logger.info(
        "schema_metadata_stored",
        source_id=str(source_id),
        rows_created=len(records),
    )
    return len(records)
