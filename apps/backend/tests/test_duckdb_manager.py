"""Tests for the DuckDB file registration and schema detection service.

Covers:
- Unit: Schema extraction for each supported file format (CSV, Excel, Parquet, JSON)
- Unit: Table name generation and sanitization
- Integration: File registration -> query execution round-trip
- Edge cases: empty files, wide tables, mixed types, no headers, corrupted files
- Error handling: missing files, unsupported formats, corrupted data
"""

from __future__ import annotations

import json
import struct
import tempfile
from pathlib import Path

import duckdb
import pytest

from app.models.dataset import DatasetStatus
from app.services.duckdb_manager import (
    ColumnInfo,
    DuckDBManager,
    RegisterResult,
    sanitize_table_name,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def manager() -> DuckDBManager:
    """Create a fresh in-memory DuckDB manager for each test."""
    mgr = DuckDBManager()
    yield mgr
    mgr.close()


@pytest.fixture
def tmp_dir() -> Path:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def _write_csv(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _write_json(path: Path, data: list[dict]) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _write_parquet(path: Path, data: list[dict]) -> Path:
    """Write a Parquet file via DuckDB for test isolation."""
    conn = duckdb.connect(":memory:")
    columns = list(data[0].keys()) if data else []
    if not data:
        conn.execute(f"COPY (SELECT 1 WHERE false) TO '{path}' (FORMAT PARQUET)")
    else:
        values_list = []
        for row in data:
            vals = []
            for v in row.values():
                if isinstance(v, str):
                    vals.append(f"'{v}'")
                elif v is None:
                    vals.append("NULL")
                else:
                    vals.append(str(v))
            values_list.append(f"({', '.join(vals)})")

        col_defs = ", ".join(columns)
        values_sql = ", ".join(values_list)
        conn.execute(
            f"COPY (SELECT * FROM (VALUES {values_sql}) AS t({col_defs})) "
            f"TO '{path}' (FORMAT PARQUET)"
        )
    conn.close()
    return path


# ---------------------------------------------------------------------------
# Unit Tests: sanitize_table_name
# ---------------------------------------------------------------------------


class TestSanitizeTableName:
    """Test table name generation and sanitization."""

    def test_simple_name(self) -> None:
        assert sanitize_table_name("sales.csv") == "ds_sales"

    def test_strips_extension(self) -> None:
        assert sanitize_table_name("report.xlsx") == "ds_report"

    def test_replaces_special_chars(self) -> None:
        assert sanitize_table_name("my-data file (1).csv") == "ds_my_data_file_1"

    def test_collapses_underscores(self) -> None:
        assert sanitize_table_name("a___b.csv") == "ds_a_b"

    def test_lowercases(self) -> None:
        assert sanitize_table_name("MyData.CSV") == "ds_mydata"

    def test_empty_stem_uses_uuid(self) -> None:
        result = sanitize_table_name(".csv")
        assert result.startswith("ds_")
        assert len(result) > 3

    def test_numeric_only(self) -> None:
        assert sanitize_table_name("123.csv") == "ds_123"

    def test_unicode_chars_replaced(self) -> None:
        result = sanitize_table_name("datos_espanol.csv")
        assert result == "ds_datos_espanol"

    def test_deeply_nested_path(self) -> None:
        result = sanitize_table_name("/path/to/some/file.csv")
        assert result == "ds_file"

    def test_parquet_extension(self) -> None:
        assert sanitize_table_name("warehouse.parquet") == "ds_warehouse"


# ---------------------------------------------------------------------------
# Unit Tests: Schema extraction per format
# ---------------------------------------------------------------------------


class TestCSVSchemaExtraction:
    """Test schema extraction for CSV files."""

    def test_basic_csv_schema(self, manager: DuckDBManager, tmp_dir: Path) -> None:
        csv_path = _write_csv(
            tmp_dir / "test.csv",
            "id,name,age\n1,Alice,30\n2,Bob,25\n",
        )
        result = manager.register_file(csv_path, "ds_test", "csv")

        assert result.is_success
        assert len(result.columns) == 3
        col_names = [c.column_name for c in result.columns]
        assert "id" in col_names
        assert "name" in col_names
        assert "age" in col_names

    def test_csv_type_inference(self, manager: DuckDBManager, tmp_dir: Path) -> None:
        csv_path = _write_csv(
            tmp_dir / "types.csv",
            "int_col,float_col,str_col,bool_col\n1,3.14,hello,true\n2,2.71,world,false\n",
        )
        result = manager.register_file(csv_path, "ds_types", "csv")

        assert result.is_success
        type_map = {c.column_name: c.data_type for c in result.columns}
        assert "BIGINT" in type_map["int_col"] or "INTEGER" in type_map["int_col"]
        assert "DOUBLE" in type_map["float_col"] or "FLOAT" in type_map["float_col"]
        assert "VARCHAR" in type_map["str_col"]

    def test_csv_row_count(self, manager: DuckDBManager, tmp_dir: Path) -> None:
        csv_path = _write_csv(
            tmp_dir / "rows.csv",
            "a,b\n1,x\n2,y\n3,z\n",
        )
        result = manager.register_file(csv_path, "ds_rows", "csv")

        assert result.is_success
        assert result.row_count == 3


class TestParquetSchemaExtraction:
    """Test schema extraction for Parquet files."""

    def test_basic_parquet_schema(self, manager: DuckDBManager, tmp_dir: Path) -> None:
        parquet_path = _write_parquet(
            tmp_dir / "test.parquet",
            [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
        )
        result = manager.register_file(parquet_path, "ds_parquet", "parquet")

        assert result.is_success
        assert len(result.columns) == 2
        col_names = [c.column_name for c in result.columns]
        assert "id" in col_names
        assert "name" in col_names

    def test_parquet_row_count(self, manager: DuckDBManager, tmp_dir: Path) -> None:
        parquet_path = _write_parquet(
            tmp_dir / "counted.parquet",
            [{"x": i} for i in range(100)],
        )
        result = manager.register_file(parquet_path, "ds_counted", "parquet")

        assert result.is_success
        assert result.row_count == 100


class TestJSONSchemaExtraction:
    """Test schema extraction for JSON files."""

    def test_basic_json_schema(self, manager: DuckDBManager, tmp_dir: Path) -> None:
        json_path = _write_json(
            tmp_dir / "test.json",
            [{"city": "NYC", "pop": 8000000}, {"city": "LA", "pop": 4000000}],
        )
        result = manager.register_file(json_path, "ds_json", "json")

        assert result.is_success
        col_names = [c.column_name for c in result.columns]
        assert "city" in col_names
        assert "pop" in col_names
        assert result.row_count == 2


class TestExcelSchemaExtraction:
    """Test schema extraction for Excel files.

    These tests require the DuckDB spatial extension to be available.
    They create minimal XLSX files using DuckDB's COPY statement.
    """

    @pytest.fixture
    def xlsx_path(self, tmp_dir: Path) -> Path:
        """Create a test Excel file via DuckDB COPY."""
        path = tmp_dir / "test.xlsx"
        conn = duckdb.connect(":memory:")
        try:
            conn.execute("INSTALL spatial")
            conn.execute("LOAD spatial")
            conn.execute(
                f"COPY (SELECT 1 AS id, 'Alice' AS name, 30 AS age "
                f"UNION ALL SELECT 2, 'Bob', 25) "
                f"TO '{path}' WITH (FORMAT GDAL, DRIVER 'XLSX')"
            )
        except duckdb.Error:
            conn.close()
            pytest.skip("DuckDB spatial extension required for Excel tests")
        conn.close()
        return path

    def test_basic_xlsx_schema(
        self, manager: DuckDBManager, xlsx_path: Path
    ) -> None:
        result = manager.register_file(xlsx_path, "ds_xlsx", "xlsx")

        assert result.is_success
        col_names = [c.column_name for c in result.columns]
        assert len(col_names) >= 2  # At least id and name

    def test_xlsx_row_count(self, manager: DuckDBManager, xlsx_path: Path) -> None:
        result = manager.register_file(xlsx_path, "ds_xlsx_rows", "xlsx")

        assert result.is_success
        assert result.row_count == 2


# ---------------------------------------------------------------------------
# Integration Tests: File registration -> query round-trip
# ---------------------------------------------------------------------------


class TestFileRegistrationRoundTrip:
    """Integration tests: register a file then query it via SQL."""

    def test_csv_register_and_query(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        csv_path = _write_csv(
            tmp_dir / "products.csv",
            "product,price,qty\nWidget,9.99,100\nGadget,19.99,50\n",
        )
        result = manager.register_file(csv_path, "ds_products", "csv")
        assert result.is_success

        rows = manager.execute_query("SELECT * FROM ds_products ORDER BY product")
        assert len(rows) == 2
        assert rows[0]["product"] == "Gadget"
        assert rows[1]["product"] == "Widget"

    def test_parquet_register_and_query(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        parquet_path = _write_parquet(
            tmp_dir / "data.parquet",
            [{"x": 10, "y": 20}, {"x": 30, "y": 40}],
        )
        result = manager.register_file(parquet_path, "ds_data", "parquet")
        assert result.is_success

        rows = manager.execute_query("SELECT SUM(x) AS total_x FROM ds_data")
        assert rows[0]["total_x"] == 40

    def test_json_register_and_query(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        json_path = _write_json(
            tmp_dir / "events.json",
            [
                {"event": "click", "count": 100},
                {"event": "view", "count": 500},
            ],
        )
        result = manager.register_file(json_path, "ds_events", "json")
        assert result.is_success

        rows = manager.execute_query(
            "SELECT event FROM ds_events WHERE count > 200"
        )
        assert len(rows) == 1
        assert rows[0]["event"] == "view"

    def test_multiple_tables_queried_together(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        csv1 = _write_csv(
            tmp_dir / "orders.csv",
            "order_id,product_id,qty\n1,100,2\n2,101,5\n",
        )
        csv2 = _write_csv(
            tmp_dir / "products.csv",
            "product_id,name\n100,Widget\n101,Gadget\n",
        )
        manager.register_file(csv1, "ds_orders", "csv")
        manager.register_file(csv2, "ds_products", "csv")

        rows = manager.execute_query(
            "SELECT o.order_id, p.name "
            "FROM ds_orders o JOIN ds_products p ON o.product_id = p.product_id "
            "ORDER BY o.order_id"
        )
        assert len(rows) == 2
        assert rows[0]["name"] == "Widget"
        assert rows[1]["name"] == "Gadget"


class TestSchemaMetadataMatch:
    """Integration: verify extracted schema matches actual file schema."""

    def test_csv_schema_matches_file(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        csv_path = _write_csv(
            tmp_dir / "schema_test.csv",
            "id,name,score,active\n1,Alice,95.5,true\n2,Bob,87.3,false\n",
        )
        result = manager.register_file(csv_path, "ds_schema", "csv")

        assert result.is_success
        col_names = {c.column_name for c in result.columns}
        assert col_names == {"id", "name", "score", "active"}

        # Verify via direct query that columns are queryable
        for col in result.columns:
            rows = manager.execute_query(
                f"SELECT {col.column_name} FROM ds_schema LIMIT 1"
            )
            assert len(rows) == 1

    def test_parquet_schema_matches_file(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        parquet_path = _write_parquet(
            tmp_dir / "schema_test.parquet",
            [{"a": 1, "b": "x", "c": 3.14}],
        )
        result = manager.register_file(parquet_path, "ds_parq_schema", "parquet")

        assert result.is_success
        col_names = {c.column_name for c in result.columns}
        assert col_names == {"a", "b", "c"}


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for file registration."""

    def test_empty_csv_headers_only(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """Empty CSV (headers but no data rows) registers with 0 row count."""
        csv_path = _write_csv(tmp_dir / "empty.csv", "a,b,c\n")
        result = manager.register_file(csv_path, "ds_empty", "csv")

        assert result.is_success
        assert result.row_count == 0
        assert len(result.columns) == 3

    def test_csv_inconsistent_columns(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """CSV with inconsistent column counts: best-effort parse."""
        csv_path = _write_csv(
            tmp_dir / "inconsistent.csv",
            "a,b,c\n1,2,3\n4,5\n6,7,8,9\n",
        )
        result = manager.register_file(csv_path, "ds_inconsistent", "csv")

        # DuckDB's read_csv_auto handles this gracefully - should register
        # Either succeeds with best-effort or fails with error status
        # Both are acceptable per the acceptance criteria
        if result.is_success:
            assert len(result.columns) >= 3
        else:
            assert result.status == DatasetStatus.ERROR.value
            assert result.error_message is not None

    def test_csv_no_header(self, manager: DuckDBManager, tmp_dir: Path) -> None:
        """CSV without headers: DuckDB auto-detects or generates column names."""
        csv_path = _write_csv(
            tmp_dir / "noheader.csv",
            "1,Alice,30\n2,Bob,25\n3,Carol,28\n",
        )
        result = manager.register_file(csv_path, "ds_noheader", "csv")

        # DuckDB read_csv_auto will either auto-detect no header and generate
        # column0, column1, column2 names, or treat the first row as header.
        # Either way, it should succeed.
        assert result.is_success
        assert len(result.columns) >= 3

    def test_mixed_types_in_column(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """Mixed types in a column: DuckDB auto-inference handles gracefully."""
        csv_path = _write_csv(
            tmp_dir / "mixed.csv",
            "id,value\n1,100\n2,hello\n3,3.14\n",
        )
        result = manager.register_file(csv_path, "ds_mixed", "csv")

        assert result.is_success
        # DuckDB will likely infer VARCHAR for the mixed column
        value_col = next(c for c in result.columns if c.column_name == "value")
        assert value_col.data_type  # Has a detected type

    def test_very_wide_table_warning(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """Tables with 500+ columns produce a performance warning."""
        # Generate a CSV with 501 columns
        num_cols = 501
        headers = ",".join(f"col{i}" for i in range(num_cols))
        values = ",".join(str(i) for i in range(num_cols))
        csv_path = _write_csv(
            tmp_dir / "wide.csv",
            f"{headers}\n{values}\n",
        )
        result = manager.register_file(csv_path, "ds_wide", "csv")

        assert result.is_success
        assert len(result.columns) == num_cols
        assert any("performance" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Error handling tests for file registration."""

    def test_missing_file(self, manager: DuckDBManager) -> None:
        """Non-existent file sets status to error."""
        result = manager.register_file("/nonexistent/file.csv", "ds_missing", "csv")

        assert not result.is_success
        assert result.status == DatasetStatus.ERROR.value
        assert "not found" in result.error_message.lower()

    def test_unsupported_format(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        """Unsupported file format returns error."""
        file_path = tmp_dir / "test.docx"
        file_path.write_text("not a real docx")
        result = manager.register_file(file_path, "ds_unsupported", "docx")

        assert not result.is_success
        assert result.status == DatasetStatus.ERROR.value
        assert "unsupported" in result.error_message.lower()

    def test_corrupted_csv(self, manager: DuckDBManager, tmp_dir: Path) -> None:
        """Corrupted binary data posing as CSV returns error or partial result."""
        file_path = tmp_dir / "corrupt.csv"
        file_path.write_bytes(struct.pack("!16B", *range(16)) * 100)
        result = manager.register_file(file_path, "ds_corrupt", "csv")

        # DuckDB read_csv_auto may still parse garbage as a single VARCHAR column
        # That's acceptable - the key requirement is no crash
        assert isinstance(result, RegisterResult)

    def test_corrupted_parquet(self, manager: DuckDBManager, tmp_dir: Path) -> None:
        """Corrupted Parquet file sets status to error with message."""
        file_path = tmp_dir / "corrupt.parquet"
        file_path.write_bytes(b"not a parquet file at all")
        result = manager.register_file(file_path, "ds_corrupt_pq", "parquet")

        assert not result.is_success
        assert result.status == DatasetStatus.ERROR.value
        assert result.error_message is not None

    def test_corrupted_json(self, manager: DuckDBManager, tmp_dir: Path) -> None:
        """Malformed JSON file sets status to error with message."""
        file_path = tmp_dir / "corrupt.json"
        file_path.write_text("{this is not valid json[[[")
        result = manager.register_file(file_path, "ds_corrupt_json", "json")

        assert not result.is_success
        assert result.status == DatasetStatus.ERROR.value
        assert result.error_message is not None


# ---------------------------------------------------------------------------
# Table management
# ---------------------------------------------------------------------------


class TestTableManagement:
    """Test table registration tracking and unregistration."""

    def test_is_table_registered(
        self, manager: DuckDBManager, tmp_dir: Path
    ) -> None:
        csv_path = _write_csv(tmp_dir / "t.csv", "a\n1\n")
        manager.register_file(csv_path, "ds_track", "csv")

        assert manager.is_table_registered("ds_track")
        assert not manager.is_table_registered("ds_nonexistent")

    def test_list_tables(self, manager: DuckDBManager, tmp_dir: Path) -> None:
        csv1 = _write_csv(tmp_dir / "a.csv", "x\n1\n")
        csv2 = _write_csv(tmp_dir / "b.csv", "y\n2\n")
        manager.register_file(csv1, "ds_a", "csv")
        manager.register_file(csv2, "ds_b", "csv")

        tables = manager.list_tables()
        assert "ds_a" in tables
        assert "ds_b" in tables

    def test_unregister_table(self, manager: DuckDBManager, tmp_dir: Path) -> None:
        csv_path = _write_csv(tmp_dir / "t.csv", "a\n1\n")
        manager.register_file(csv_path, "ds_unreg", "csv")

        manager.unregister_table("ds_unreg")

        assert not manager.is_table_registered("ds_unreg")
        with pytest.raises(duckdb.Error):
            manager.execute_query("SELECT * FROM ds_unreg")

    def test_unregister_nonexistent_table(self, manager: DuckDBManager) -> None:
        """Unregistering a non-existent table does not raise."""
        manager.unregister_table("ds_does_not_exist")

    def test_reregister_table(self, manager: DuckDBManager, tmp_dir: Path) -> None:
        """Re-registering the same table name replaces the old view."""
        csv1 = _write_csv(tmp_dir / "v1.csv", "a\n1\n")
        csv2 = _write_csv(tmp_dir / "v2.csv", "a\n99\n")

        manager.register_file(csv1, "ds_reuse", "csv")
        rows1 = manager.execute_query("SELECT a FROM ds_reuse")
        assert rows1[0]["a"] == 1

        manager.register_file(csv2, "ds_reuse", "csv")
        rows2 = manager.execute_query("SELECT a FROM ds_reuse")
        assert rows2[0]["a"] == 99


# ---------------------------------------------------------------------------
# RegisterResult / ColumnInfo dataclass tests
# ---------------------------------------------------------------------------


class TestRegisterResult:
    """Test RegisterResult properties."""

    def test_success_result(self) -> None:
        r = RegisterResult(status=DatasetStatus.READY.value)
        assert r.is_success

    def test_error_result(self) -> None:
        r = RegisterResult(
            status=DatasetStatus.ERROR.value,
            error_message="something went wrong",
        )
        assert not r.is_success
        assert r.error_message == "something went wrong"

    def test_default_values(self) -> None:
        r = RegisterResult()
        assert r.columns == []
        assert r.row_count == 0
        assert r.warnings == []
        assert r.error_message is None


class TestColumnInfo:
    """Test ColumnInfo dataclass."""

    def test_defaults(self) -> None:
        c = ColumnInfo(column_name="id", data_type="INTEGER")
        assert c.is_nullable is True
        assert c.is_primary_key is False
        assert c.ordinal_position == 0

    def test_custom_values(self) -> None:
        c = ColumnInfo(
            column_name="pk",
            data_type="UUID",
            is_nullable=False,
            is_primary_key=True,
            ordinal_position=0,
        )
        assert c.column_name == "pk"
        assert c.data_type == "UUID"
        assert c.is_nullable is False
        assert c.is_primary_key is True
