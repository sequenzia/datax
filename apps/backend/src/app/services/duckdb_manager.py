"""DuckDB integration layer for file registration and schema detection.

Manages an in-process DuckDB instance that registers uploaded files as virtual
tables. Supports CSV, Excel, Parquet, and JSON formats with automatic schema
detection. Uses persistent file-backed storage so registered tables survive
application restarts. Optionally enables the httpfs extension for querying
remote files via S3 URIs or HTTP URLs.
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import duckdb

from app.logging import get_logger
from app.models.dataset import DatasetStatus

logger = get_logger(__name__)

# Column count threshold for performance warning
WIDE_TABLE_THRESHOLD = 500

# Maximum columns to include in AI prompt for wide tables
WIDE_TABLE_AI_LIMIT = 100

# Default database file path (relative to project root)
DEFAULT_DUCKDB_PATH = "data/datax.duckdb"


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
    - Create via ``DuckDBManager(database=path)`` for persistent storage,
      or ``DuckDBManager()`` for the default file-backed database.
    - Call ``register_file`` to add a file as a virtual table.
    - Call ``register_remote`` to add a remote S3/HTTP file as a virtual table.
    - Call ``execute_query`` to run SQL against registered tables.
    - Call ``unregister_table`` to drop a virtual table.
    - Call ``close`` to release the DuckDB connection.

    The manager uses file-backed storage by default so that registered tables
    (views) persist across application restarts without re-registration from
    PostgreSQL metadata.

    When ``httpfs_enabled`` is ``True``, the httpfs extension is installed and
    loaded so that users can query remote files via S3 URIs or HTTP URLs
    without downloading them locally.

    The manager is **not** thread-safe. In a FastAPI context it should be
    accessed within a single event-loop or via a dedicated background worker.
    """

    def __init__(
        self,
        database: str | Path = ":memory:",
        *,
        httpfs_enabled: bool = False,
        s3_access_key_id: str | None = None,
        s3_secret_access_key: str | None = None,
        s3_region: str | None = None,
        httpfs_timeout: int = 30,
    ) -> None:
        self._database = str(database)
        self._registered_tables: dict[str, str] = {}
        self._httpfs_enabled = False
        self._httpfs_timeout = httpfs_timeout

        # Auto-create parent directory for file-backed databases
        if self._database != ":memory:":
            db_path = Path(self._database)
            try:
                db_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise OSError(
                    f"Cannot create directory for DuckDB database at "
                    f"'{db_path.parent}': {exc}"
                ) from exc

            # Verify the path is writable
            if db_path.exists() and not os.access(db_path, os.W_OK):
                raise OSError(
                    f"DuckDB database file is not writable: {db_path}"
                )
            if not db_path.exists() and not os.access(db_path.parent, os.W_OK):
                raise OSError(
                    f"DuckDB database directory is not writable: {db_path.parent}"
                )

        self._conn = duckdb.connect(database=self._database)

        # Enable httpfs extension for remote data access
        if httpfs_enabled:
            self._setup_httpfs(
                s3_access_key_id=s3_access_key_id,
                s3_secret_access_key=s3_secret_access_key,
                s3_region=s3_region,
            )

        # For file-backed databases, sync the in-memory table registry
        # from the persisted DuckDB views so `is_table_registered` and
        # `list_tables` reflect tables that survived a restart.
        if self._database != ":memory:":
            self._sync_registered_tables()

        logger.info(
            "duckdb_initialized",
            database=self._database,
            httpfs_enabled=self._httpfs_enabled,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def health_check(self) -> dict[str, object]:
        """Verify database accessibility and return status information.

        Returns a dict with:
        - ``healthy``: bool indicating whether the database is accessible
        - ``database``: the database path
        - ``table_count``: number of registered tables
        - ``error``: error message if unhealthy

        This method is safe to call at any time for startup verification
        or readiness probes.
        """
        try:
            result = self._conn.execute("SELECT 1 AS health_check")
            result.fetchone()
            return {
                "healthy": True,
                "database": self._database,
                "table_count": len(self._registered_tables),
            }
        except Exception as exc:
            logger.error("duckdb_health_check_failed", error=str(exc))
            return {
                "healthy": False,
                "database": self._database,
                "table_count": 0,
                "error": str(exc),
            }

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

    @property
    def httpfs_enabled(self) -> bool:
        """Whether the httpfs extension is loaded and available."""
        return self._httpfs_enabled

    def register_remote(
        self,
        url: str,
        table_name: str,
    ) -> RegisterResult:
        """Register a remote file (S3 URI or HTTP URL) as a queryable DuckDB view.

        The httpfs extension must be enabled for this method to work. Remote
        files are queried directly by DuckDB without local download, leveraging
        predicate pushdown for Parquet files.

        Args:
            url: S3 URI (``s3://bucket/path/file.parquet``) or HTTP URL
                (``https://example.com/data.csv``).
            table_name: Desired DuckDB table name (should be pre-sanitized).

        Returns:
            A ``RegisterResult`` with extracted column info, row count, status,
            and any warnings.
        """
        if not self._httpfs_enabled:
            return RegisterResult(
                status=DatasetStatus.ERROR.value,
                error_message=(
                    "httpfs extension is not enabled. Set DATAX_HTTPFS_ENABLED=true "
                    "to enable remote data access."
                ),
            )

        warnings: list[str] = []

        # Validate and classify the URL
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()

        if scheme == "s3":
            # S3 URI: check credentials were configured
            try:
                cred_check = self._conn.execute(
                    "SELECT current_setting('s3_access_key_id')"
                ).fetchone()
                # current_setting returns None when not set, or a non-empty
                # string when explicitly configured
                has_credentials = (
                    cred_check is not None
                    and cred_check[0] is not None
                    and cred_check[0] != ""
                )
            except duckdb.Error:
                has_credentials = False

            if not has_credentials:
                return RegisterResult(
                    status=DatasetStatus.ERROR.value,
                    error_message=(
                        "S3 credentials not configured. Set AWS_ACCESS_KEY_ID "
                        "and AWS_SECRET_ACCESS_KEY environment variables."
                    ),
                )
        elif scheme == "http":
            warnings.append(
                "Using insecure HTTP connection. Consider using HTTPS for "
                "secure data transfer."
            )
        elif scheme != "https":
            return RegisterResult(
                status=DatasetStatus.ERROR.value,
                error_message=(
                    f"Unsupported URL scheme: {scheme}. Use s3://, https://, "
                    f"or http://."
                ),
            )

        # Detect format from URL path
        url_path = parsed.path.lower()
        if url_path.endswith(".parquet"):
            file_format = "parquet"
        elif url_path.endswith(".csv"):
            file_format = "csv"
        elif url_path.endswith(".json"):
            file_format = "json"
        else:
            return RegisterResult(
                status=DatasetStatus.ERROR.value,
                error_message=(
                    "Cannot detect file format from URL. Supported formats: "
                    ".parquet, .csv, .json"
                ),
            )

        # Build the read expression for remote files
        escaped_url = url.replace("'", "''")
        match file_format:
            case "parquet":
                read_expr = f"read_parquet('{escaped_url}')"
            case "csv":
                read_expr = f"read_csv_auto('{escaped_url}')"
            case "json":
                read_expr = f"read_json_auto('{escaped_url}')"

        # Create the view
        try:
            self._conn.execute(
                f"CREATE OR REPLACE VIEW {table_name} AS SELECT * FROM {read_expr}"
            )
        except duckdb.Error as exc:
            error_str = str(exc)
            logger.error(
                "remote_registration_failed",
                table_name=table_name,
                url=url,
                error=error_str,
            )

            # Translate common errors to user-friendly messages
            error_lower = error_str.lower()
            if "404" in error_str or "not found" in error_lower:
                return RegisterResult(
                    status=DatasetStatus.ERROR.value,
                    error_message=f"Remote file not found at URL: {url}",
                )
            if "403" in error_str or "access denied" in error_lower:
                return RegisterResult(
                    status=DatasetStatus.ERROR.value,
                    error_message=(
                        "S3 authentication failed. Verify your AWS_ACCESS_KEY_ID "
                        "and AWS_SECRET_ACCESS_KEY are correct and have access "
                        f"to: {url}"
                    ),
                )
            if "timeout" in error_lower or "timed out" in error_lower:
                return RegisterResult(
                    status=DatasetStatus.ERROR.value,
                    error_message=(
                        f"Network timeout while accessing remote file: {url}. "
                        f"Current timeout is {self._httpfs_timeout}s. Adjust "
                        f"DATAX_HTTPFS_TIMEOUT to increase."
                    ),
                )
            return RegisterResult(
                status=DatasetStatus.ERROR.value,
                error_message=f"Failed to access remote file: {exc}",
            )

        # Extract schema
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

        # Row count for remote files: warn about broad queries on large datasets
        try:
            row_count = self._count_rows(table_name)
            if row_count > 1_000_000:
                warnings.append(
                    f"Remote dataset has {row_count:,} rows. Use LIMIT or WHERE "
                    f"clauses for better performance with remote data."
                )
        except duckdb.Error as exc:
            logger.warning("row_count_failed", table_name=table_name, error=str(exc))
            row_count = 0
            warnings.append(f"Row count failed: {exc}")

        self._registered_tables[table_name] = url

        logger.info(
            "remote_file_registered",
            table_name=table_name,
            url=url,
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

    def summarize_table(self, table_name: str) -> list[dict]:
        """Run DuckDB SUMMARIZE on a table and return structured column statistics.

        Returns a list of dicts, one per column, with keys matching DuckDB's
        SUMMARIZE output: column_name, column_type, min, max, approx_unique,
        avg, std, q25, q50, q75, count, null_percentage.

        For tables with more columns than ``WIDE_TABLE_AI_LIMIT``, only the
        first ``WIDE_TABLE_AI_LIMIT`` columns are returned (the full SUMMARIZE
        still runs, but results are truncated for AI prompt injection).

        Args:
            table_name: Name of a registered DuckDB table.

        Returns:
            List of column statistics dicts. Empty list if SUMMARIZE fails
            or the table has no rows.
        """
        try:
            result = self._conn.execute(f"SUMMARIZE {table_name}")
            col_names = [desc[0] for desc in result.description]
            rows = result.fetchall()
        except duckdb.Error as exc:
            logger.warning(
                "summarize_failed", table_name=table_name, error=str(exc)
            )
            return []

        stats: list[dict] = []
        for row in rows:
            row_dict: dict = {}
            for col_name, value in zip(col_names, row):
                # Convert non-serializable types to strings
                if value is None:
                    row_dict[col_name] = None
                elif isinstance(value, (int, float, str, bool)):
                    row_dict[col_name] = value
                else:
                    row_dict[col_name] = str(value)
            stats.append(row_dict)

        # Truncate for wide tables (AI prompt injection limit)
        if len(stats) > WIDE_TABLE_AI_LIMIT:
            logger.info(
                "summarize_truncated",
                table_name=table_name,
                total_columns=len(stats),
                limit=WIDE_TABLE_AI_LIMIT,
            )
            stats = stats[:WIDE_TABLE_AI_LIMIT]

        return stats

    def get_sample_values(
        self, table_name: str, limit: int = 5
    ) -> dict[str, list]:
        """Extract up to ``limit`` distinct sample values per column.

        Iterates over each column in the table and runs
        ``SELECT DISTINCT column FROM table LIMIT limit``.

        For tables with more columns than ``WIDE_TABLE_AI_LIMIT``, only the
        first ``WIDE_TABLE_AI_LIMIT`` columns are sampled.

        Args:
            table_name: Name of a registered DuckDB table.
            limit: Maximum number of distinct values per column.

        Returns:
            Dict mapping column names to lists of sample values.
            Columns with all NULL values will have an empty list.
        """
        # Get column names
        try:
            result = self._conn.execute(f"SELECT * FROM {table_name} LIMIT 0")
            columns = [desc[0] for desc in result.description]
        except duckdb.Error as exc:
            logger.warning(
                "sample_values_schema_failed",
                table_name=table_name,
                error=str(exc),
            )
            return {}

        # Truncate for wide tables
        if len(columns) > WIDE_TABLE_AI_LIMIT:
            columns = columns[:WIDE_TABLE_AI_LIMIT]

        samples: dict[str, list] = {}
        for col_name in columns:
            try:
                result = self._conn.execute(
                    f'SELECT DISTINCT "{col_name}" FROM {table_name} '
                    f'WHERE "{col_name}" IS NOT NULL LIMIT {limit}'
                )
                values = [row[0] for row in result.fetchall()]
                # Serialize non-primitive values to strings
                serialized: list = []
                for v in values:
                    if v is None:
                        serialized.append(None)
                    elif isinstance(v, (int, float, str, bool)):
                        serialized.append(v)
                    else:
                        serialized.append(str(v))
                samples[col_name] = serialized
            except duckdb.Error as exc:
                logger.warning(
                    "sample_values_column_failed",
                    table_name=table_name,
                    column=col_name,
                    error=str(exc),
                )
                samples[col_name] = []

        return samples

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

    def _sync_registered_tables(self) -> None:
        """Sync the in-memory table registry from persisted DuckDB views.

        On startup with a file-backed database, DuckDB already has the view
        definitions from previous sessions. This method queries the DuckDB
        catalog to rebuild the ``_registered_tables`` dict so that
        ``is_table_registered`` and ``list_tables`` work correctly.

        Only views with the ``ds_`` prefix are included (matching the
        ``sanitize_table_name`` convention).
        """
        try:
            result = self._conn.execute(
                "SELECT view_name FROM duckdb_views() "
                "WHERE NOT internal AND schema_name = 'main'"
            ).fetchall()

            for (view_name,) in result:
                if view_name.startswith("ds_"):
                    # We don't have the original file path from the catalog,
                    # so store an empty string. The rehydration step in
                    # main.py will update this if the dataset still exists
                    # in PostgreSQL.
                    self._registered_tables[view_name] = ""

            if self._registered_tables:
                logger.info(
                    "duckdb_tables_synced",
                    table_count=len(self._registered_tables),
                    tables=list(self._registered_tables.keys()),
                )
        except duckdb.Error as exc:
            logger.warning("duckdb_sync_failed", error=str(exc))

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

    def _setup_httpfs(
        self,
        *,
        s3_access_key_id: str | None = None,
        s3_secret_access_key: str | None = None,
        s3_region: str | None = None,
    ) -> None:
        """Install and load the httpfs extension, then configure S3 credentials.

        If S3 credentials are not provided, httpfs still works for HTTP/HTTPS
        URLs and for S3 when running on AWS with IAM roles (automatic
        credential resolution).
        """
        try:
            self._conn.execute("INSTALL httpfs")
        except duckdb.Error:
            # Already installed; ignore
            pass

        try:
            self._conn.execute("LOAD httpfs")
        except duckdb.Error as exc:
            logger.error("httpfs_extension_load_failed", error=str(exc))
            return

        self._httpfs_enabled = True

        # Configure S3 credentials if provided
        if s3_access_key_id and s3_secret_access_key:
            try:
                self._conn.execute(
                    f"SET s3_access_key_id='{s3_access_key_id}'"
                )
                self._conn.execute(
                    f"SET s3_secret_access_key='{s3_secret_access_key}'"
                )
                if s3_region:
                    self._conn.execute(f"SET s3_region='{s3_region}'")
                logger.info(
                    "httpfs_s3_configured",
                    region=s3_region or "default",
                    has_credentials=True,
                )
            except duckdb.Error as exc:
                logger.error("httpfs_s3_config_failed", error=str(exc))
        else:
            logger.info(
                "httpfs_s3_no_credentials",
                message="S3 credentials not provided; IAM role or HTTP-only access",
            )

        # Set HTTP timeout
        try:
            self._conn.execute(
                f"SET http_timeout={self._httpfs_timeout * 1000}"
            )
        except duckdb.Error as exc:
            logger.warning("httpfs_timeout_config_failed", error=str(exc))

        logger.info("httpfs_extension_loaded")
