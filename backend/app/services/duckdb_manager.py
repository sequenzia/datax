"""DuckDB integration layer for file registration and schema detection.

Manages an in-process DuckDB instance that registers uploaded files as virtual
tables. Supports CSV, Excel, Parquet, and JSON formats with automatic schema
detection.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from app.logging import get_logger
from app.models.dataset import DatasetStatus

logger = get_logger(__name__)

# Column count threshold for performance warning
WIDE_TABLE_THRESHOLD = 500


def sanitize_table_name(name: str) -> str:
    """Generate a safe DuckDB table name from a dataset name.

    Strips the file extension, replaces non-alphanumeric characters with
    underscores, collapses consecutive underscores, trims leading/trailing
    underscores, lowercases the result, and prefixes with ``ds_``. If the
    sanitized base is empty, a short UUID fragment is used instead.

    Args:
        name: Original file or dataset name.

    Returns:
        A sanitized table name safe for use as a DuckDB identifier.
    """
    # Strip file extension
    base = Path(name).stem

    # Replace non-alphanumeric with underscores
    base = re.sub(r"[^a-zA-Z0-9]", "_", base)

    # Collapse consecutive underscores and strip leading/trailing
    base = re.sub(r"_+", "_", base).strip("_").lower()

    if not base:
        base = uuid.uuid4().hex[:8]

    return f"ds_{base}"


@dataclass
class ColumnInfo:
    """Schema information for a single column extracted from DuckDB.

    This is a plain data transfer object used to pass column metadata between
    the DuckDB manager and the persistence layer. It does not depend on
    SQLAlchemy.
    """

    column_name: str
    data_type: str
    is_nullable: bool = True
    is_primary_key: bool = False
    ordinal_position: int = 0


@dataclass
class RegisterResult:
    """Result of a file registration operation.

    Attributes:
        status: ``ready`` on success, ``error`` on failure.
        columns: Extracted column metadata.
        row_count: Number of data rows in the file.
        error_message: Human-readable error description when ``status`` is ``error``.
        warnings: Non-fatal issues encountered during registration (e.g.,
            wide-table performance warning, fallback schema detection).
    """

    status: str = DatasetStatus.READY.value
    columns: list[ColumnInfo] = field(default_factory=list)
    row_count: int = 0
    error_message: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return self.status == DatasetStatus.READY.value


class DuckDBManager:
    """Manages a DuckDB in-process connection for file-based analytics.

    Lifecycle:
    - Create via ``DuckDBManager()`` (defaults to in-memory database).
    - Call ``register_file`` to add a file as a virtual table.
    - Call ``execute_query`` to run SQL against registered tables.
    - Call ``unregister_table`` to drop a virtual table.
    - Call ``close`` to release the DuckDB connection.

    The manager is **not** thread-safe. In a FastAPI context it should be
    accessed within a single event-loop or via a dedicated background worker.
    """

    def __init__(self, database: str = ":memory:") -> None:
        self._conn = duckdb.connect(database=database)
        self._registered_tables: dict[str, str] = {}
        logger.info("duckdb_initialized", database=database)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_file(
        self,
        file_path: str | Path,
        table_name: str,
        file_format: str,
    ) -> RegisterResult:
        """Register an uploaded file as a queryable DuckDB virtual table.

        Creates a persistent view backed by the file so that subsequent SQL
        queries can reference the table by name.

        Args:
            file_path: Absolute path to the uploaded file.
            table_name: Desired DuckDB table name (should be pre-sanitized).
            file_format: One of ``csv``, ``xlsx``, ``xls``, ``parquet``, ``json``.

        Returns:
            A ``RegisterResult`` with extracted column info, row count, status,
            and any warnings.
        """
        file_path = Path(file_path)

        if not file_path.exists():
            return RegisterResult(
                status=DatasetStatus.ERROR.value,
                error_message=f"File not found: {file_path}",
            )

        try:
            read_expr = self._build_read_expression(file_path, file_format)
        except ValueError as exc:
            return RegisterResult(
                status=DatasetStatus.ERROR.value,
                error_message=str(exc),
            )

        try:
            self._conn.execute(
                f"CREATE OR REPLACE VIEW {table_name} AS SELECT * FROM {read_expr}"
            )
        except duckdb.Error as exc:
            error_msg = f"DuckDB registration failed: {exc}"
            logger.error(
                "duckdb_registration_failed",
                table_name=table_name,
                file_path=str(file_path),
                error=str(exc),
            )
            return RegisterResult(
                status=DatasetStatus.ERROR.value,
                error_message=error_msg,
            )

        # Extract schema and row count
        warnings: list[str] = []
        try:
            columns = self._extract_schema(table_name)
        except duckdb.Error as exc:
            logger.warning(
                "schema_detection_fallback",
                table_name=table_name,
                error=str(exc),
            )
            columns = self._fallback_schema(table_name)
            warnings.append(f"Schema detection failed, defaulting to VARCHAR: {exc}")

        if len(columns) >= WIDE_TABLE_THRESHOLD:
            msg = (
                f"Table has {len(columns)} columns (>= {WIDE_TABLE_THRESHOLD}); "
                "query performance may be affected"
            )
            logger.warning(
                "wide_table_detected", table_name=table_name, column_count=len(columns)
            )
            warnings.append(msg)

        try:
            row_count = self._count_rows(table_name)
        except duckdb.Error as exc:
            logger.warning("row_count_failed", table_name=table_name, error=str(exc))
            row_count = 0
            warnings.append(f"Row count failed: {exc}")

        self._registered_tables[table_name] = str(file_path)

        logger.info(
            "file_registered",
            table_name=table_name,
            file_path=str(file_path),
            file_format=file_format,
            column_count=len(columns),
            row_count=row_count,
        )

        return RegisterResult(
            status=DatasetStatus.READY.value,
            columns=columns,
            row_count=row_count,
            warnings=warnings,
        )

    def unregister_table(self, table_name: str) -> None:
        """Drop a registered virtual table.

        Silently ignores tables that are not registered.
        """
        try:
            self._conn.execute(f"DROP VIEW IF EXISTS {table_name}")
        except duckdb.Error as exc:
            logger.warning("unregister_failed", table_name=table_name, error=str(exc))
        self._registered_tables.pop(table_name, None)
        logger.info("table_unregistered", table_name=table_name)

    def execute_query(self, sql: str) -> list[dict]:
        """Execute a SQL query and return results as a list of dicts.

        Args:
            sql: SQL query string.

        Returns:
            List of row dictionaries.

        Raises:
            duckdb.Error: If the query fails.
        """
        result = self._conn.execute(sql)
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    def is_table_registered(self, table_name: str) -> bool:
        """Check whether a table name is currently registered."""
        return table_name in self._registered_tables

    def list_tables(self) -> list[str]:
        """Return all currently registered table names."""
        return list(self._registered_tables.keys())

    def close(self) -> None:
        """Close the DuckDB connection and release resources."""
        try:
            self._conn.close()
        except Exception:
            pass
        self._registered_tables.clear()
        logger.info("duckdb_closed")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_read_expression(self, file_path: Path, file_format: str) -> str:
        """Return the DuckDB read function call for the given format."""
        path_str = str(file_path).replace("'", "''")

        match file_format.lower():
            case "csv":
                return f"read_csv_auto('{path_str}')"
            case "xlsx" | "xls":
                self._ensure_excel_extension()
                return f"st_read('{path_str}')"
            case "parquet":
                return f"read_parquet('{path_str}')"
            case "json":
                return f"read_json_auto('{path_str}')"
            case _:
                raise ValueError(f"Unsupported file format: {file_format}")

    def _ensure_excel_extension(self) -> None:
        """Install and load the spatial extension for Excel file support."""
        try:
            self._conn.execute("INSTALL spatial")
            self._conn.execute("LOAD spatial")
        except duckdb.Error:
            try:
                self._conn.execute("LOAD spatial")
            except duckdb.Error as exc:
                logger.warning("spatial_extension_load_failed", error=str(exc))
                raise ValueError(
                    "Excel support requires the DuckDB spatial extension "
                    "which could not be loaded"
                ) from exc

    def _extract_schema(self, table_name: str) -> list[ColumnInfo]:
        """Extract column metadata from a registered table via PRAGMA."""
        result = self._conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
        columns: list[ColumnInfo] = []
        for row in result:
            # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
            cid, col_name, col_type, notnull, _, pk = row
            columns.append(
                ColumnInfo(
                    column_name=col_name,
                    data_type=col_type,
                    is_nullable=not bool(notnull),
                    is_primary_key=bool(pk),
                    ordinal_position=cid,
                )
            )
        return columns

    def _fallback_schema(self, table_name: str) -> list[ColumnInfo]:
        """Extract column names and default all types to VARCHAR.

        Used as a fallback when PRAGMA-based schema detection fails.
        """
        try:
            result = self._conn.execute(f"SELECT * FROM {table_name} LIMIT 0")
            col_names = [desc[0] for desc in result.description]
        except duckdb.Error:
            return []

        return [
            ColumnInfo(
                column_name=name,
                data_type="VARCHAR",
                is_nullable=True,
                ordinal_position=idx,
            )
            for idx, name in enumerate(col_names)
        ]

    def _count_rows(self, table_name: str) -> int:
        """Return the row count for a registered table."""
        result = self._conn.execute(f"SELECT COUNT(*) FROM {table_name}")
        return result.fetchone()[0]  # type: ignore[index]
