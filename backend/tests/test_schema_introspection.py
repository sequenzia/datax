"""Tests for the schema introspection service.

Covers:
- Unit: Type mapping from PostgreSQL/MySQL types to normalised types
- Integration: Introspect SQLite (in-process stand-in for PostgreSQL), verify column metadata
- Integration: FK relationship extraction
- Edge cases: Empty schema, views, system schema exclusion, custom/enum types
- Error handling: Connection lost, permission denied
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Text,
    create_engine,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.orm import SchemaMetadata
from app.services.schema_introspection import (
    ColumnInfo,
    _is_system_schema,
    columns_to_schema_records,
    introspect_engine,
    normalise_type,
    store_schema_metadata,
)

# ---------------------------------------------------------------------------
# Unit: Type mapping
# ---------------------------------------------------------------------------


class TestNormaliseType:
    """Unit tests for normalise_type mapping."""

    # PostgreSQL types
    def test_pg_varchar(self) -> None:
        assert normalise_type("VARCHAR(255)") == "varchar"

    def test_pg_character_varying(self) -> None:
        assert normalise_type("CHARACTER VARYING(100)") == "varchar"

    def test_pg_text(self) -> None:
        assert normalise_type("TEXT") == "text"

    def test_pg_integer(self) -> None:
        assert normalise_type("INTEGER") == "integer"

    def test_pg_bigint(self) -> None:
        assert normalise_type("BIGINT") == "bigint"

    def test_pg_smallint(self) -> None:
        assert normalise_type("SMALLINT") == "smallint"

    def test_pg_boolean(self) -> None:
        assert normalise_type("BOOLEAN") == "boolean"

    def test_pg_double_precision(self) -> None:
        assert normalise_type("DOUBLE PRECISION") == "float"

    def test_pg_numeric(self) -> None:
        assert normalise_type("NUMERIC(10, 2)") == "decimal"

    def test_pg_timestamp_tz(self) -> None:
        assert normalise_type("TIMESTAMP WITH TIME ZONE") == "timestamptz"

    def test_pg_timestamp_no_tz(self) -> None:
        assert normalise_type("TIMESTAMP WITHOUT TIME ZONE") == "timestamp"

    def test_pg_date(self) -> None:
        assert normalise_type("DATE") == "date"

    def test_pg_time(self) -> None:
        assert normalise_type("TIME") == "time"

    def test_pg_uuid(self) -> None:
        assert normalise_type("UUID") == "uuid"

    def test_pg_jsonb(self) -> None:
        assert normalise_type("JSONB") == "jsonb"

    def test_pg_json(self) -> None:
        assert normalise_type("JSON") == "json"

    def test_pg_bytea(self) -> None:
        assert normalise_type("BYTEA") == "binary"

    def test_pg_inet(self) -> None:
        assert normalise_type("INET") == "text"

    def test_pg_array(self) -> None:
        assert normalise_type("INTEGER[]") == "integer"

    def test_pg_serial(self) -> None:
        assert normalise_type("SERIAL") == "integer"

    def test_pg_bigserial(self) -> None:
        assert normalise_type("BIGSERIAL") == "bigint"

    def test_pg_real(self) -> None:
        assert normalise_type("REAL") == "float"

    def test_pg_money(self) -> None:
        assert normalise_type("MONEY") == "decimal"

    def test_pg_interval(self) -> None:
        assert normalise_type("INTERVAL") == "interval"

    # MySQL types
    def test_mysql_int(self) -> None:
        assert normalise_type("INT") == "integer"

    def test_mysql_bigint(self) -> None:
        assert normalise_type("BIGINT") == "bigint"

    def test_mysql_tinyint_bool(self) -> None:
        assert normalise_type("TINYINT(1)") == "boolean"

    def test_mysql_tinyint_non_bool(self) -> None:
        assert normalise_type("TINYINT") == "smallint"

    def test_mysql_mediumint(self) -> None:
        assert normalise_type("MEDIUMINT") == "integer"

    def test_mysql_varchar(self) -> None:
        assert normalise_type("VARCHAR(100)") == "varchar"

    def test_mysql_longtext(self) -> None:
        assert normalise_type("LONGTEXT") == "text"

    def test_mysql_mediumtext(self) -> None:
        assert normalise_type("MEDIUMTEXT") == "text"

    def test_mysql_datetime(self) -> None:
        assert normalise_type("DATETIME") == "timestamp"

    def test_mysql_float(self) -> None:
        assert normalise_type("FLOAT") == "float"

    def test_mysql_double(self) -> None:
        assert normalise_type("DOUBLE") == "float"

    def test_mysql_decimal(self) -> None:
        assert normalise_type("DECIMAL(10,2)") == "decimal"

    def test_mysql_blob(self) -> None:
        assert normalise_type("BLOB") == "binary"

    def test_mysql_longblob(self) -> None:
        assert normalise_type("LONGBLOB") == "binary"

    def test_mysql_enum(self) -> None:
        assert normalise_type("ENUM('a','b')") == "text"

    def test_mysql_year(self) -> None:
        assert normalise_type("YEAR") == "integer"

    # Generic / unknown types
    def test_unknown_type_falls_back_to_text(self) -> None:
        assert normalise_type("GEOMETRY") == "text"

    def test_user_defined_type(self) -> None:
        assert normalise_type("USER-DEFINED") == "text"

    # Case insensitivity
    def test_case_insensitive(self) -> None:
        assert normalise_type("varchar(50)") == "varchar"
        assert normalise_type("Integer") == "integer"
        assert normalise_type("boolean") == "boolean"


# ---------------------------------------------------------------------------
# System schema detection
# ---------------------------------------------------------------------------


class TestIsSystemSchema:
    """Test system schema exclusion."""

    def test_pg_catalog(self) -> None:
        assert _is_system_schema("pg_catalog") is True

    def test_information_schema(self) -> None:
        assert _is_system_schema("information_schema") is True

    def test_pg_toast(self) -> None:
        assert _is_system_schema("pg_toast") is True

    def test_mysql_system(self) -> None:
        assert _is_system_schema("mysql") is True

    def test_performance_schema(self) -> None:
        assert _is_system_schema("performance_schema") is True

    def test_sys_schema(self) -> None:
        assert _is_system_schema("sys") is True

    def test_public_schema_not_system(self) -> None:
        assert _is_system_schema("public") is False

    def test_none_not_system(self) -> None:
        assert _is_system_schema(None) is False

    def test_user_schema_not_system(self) -> None:
        assert _is_system_schema("analytics") is False

    def test_case_insensitive(self) -> None:
        assert _is_system_schema("PG_CATALOG") is True
        assert _is_system_schema("Information_Schema") is True


# ---------------------------------------------------------------------------
# Integration: Introspect SQLite engine
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_engine():
    """Create an in-memory SQLite engine with test tables."""
    from sqlalchemy import Table

    engine = create_engine("sqlite:///:memory:")
    meta = MetaData()

    Table(
        "users",
        meta,
        Column("id", Integer, primary_key=True),
        Column("name", String(100), nullable=False),
        Column("email", String(255), nullable=True),
    )

    Table(
        "orders",
        meta,
        Column("id", Integer, primary_key=True),
        Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
        Column("amount", Integer, nullable=False),
        Column("notes", Text, nullable=True),
    )

    meta.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def empty_engine():
    """Create an in-memory SQLite engine with no tables."""
    engine = create_engine("sqlite:///:memory:")
    yield engine
    engine.dispose()


class TestIntrospectEngine:
    """Integration tests for introspect_engine using SQLite."""

    def test_introspects_tables(self, sqlite_engine) -> None:
        """Discovers all user tables."""
        result = introspect_engine(sqlite_engine)

        assert result.success is True
        assert result.table_count == 2
        table_names = {c.table_name for c in result.columns}
        assert "users" in table_names
        assert "orders" in table_names

    def test_columns_discovered(self, sqlite_engine) -> None:
        """Discovers all columns per table."""
        result = introspect_engine(sqlite_engine)

        user_cols = [c for c in result.columns if c.table_name == "users"]
        col_names = {c.column_name for c in user_cols}
        assert col_names == {"id", "name", "email"}

    def test_primary_key_identified(self, sqlite_engine) -> None:
        """Primary keys are correctly flagged."""
        result = introspect_engine(sqlite_engine)

        id_col = next(
            c for c in result.columns if c.table_name == "users" and c.column_name == "id"
        )
        assert id_col.is_primary_key is True

        name_col = next(
            c for c in result.columns if c.table_name == "users" and c.column_name == "name"
        )
        assert name_col.is_primary_key is False

    def test_nullable_flag(self, sqlite_engine) -> None:
        """Nullable flags are correctly captured."""
        result = introspect_engine(sqlite_engine)

        name_col = next(
            c for c in result.columns if c.table_name == "users" and c.column_name == "name"
        )
        assert name_col.is_nullable is False

        email_col = next(
            c for c in result.columns if c.table_name == "users" and c.column_name == "email"
        )
        assert email_col.is_nullable is True

    def test_type_normalised(self, sqlite_engine) -> None:
        """Column types are normalised."""
        result = introspect_engine(sqlite_engine)

        id_col = next(
            c for c in result.columns if c.table_name == "users" and c.column_name == "id"
        )
        assert id_col.data_type == "integer"

        name_col = next(
            c for c in result.columns if c.table_name == "users" and c.column_name == "name"
        )
        assert name_col.data_type == "varchar"

    def test_raw_type_preserved(self, sqlite_engine) -> None:
        """Raw database type string is preserved alongside normalised type."""
        result = introspect_engine(sqlite_engine)

        id_col = next(
            c for c in result.columns if c.table_name == "users" and c.column_name == "id"
        )
        # SQLite reports INTEGER
        assert "INTEGER" in id_col.raw_type.upper()

    def test_foreign_key_captured(self, sqlite_engine) -> None:
        """FK relationships are captured correctly."""
        result = introspect_engine(sqlite_engine)

        user_id_col = next(
            c for c in result.columns if c.table_name == "orders" and c.column_name == "user_id"
        )
        assert user_id_col.foreign_key_ref is not None
        assert "users" in user_id_col.foreign_key_ref
        assert "id" in user_id_col.foreign_key_ref

    def test_non_fk_column_has_no_ref(self, sqlite_engine) -> None:
        """Non-FK columns have None for foreign_key_ref."""
        result = introspect_engine(sqlite_engine)

        amount_col = next(
            c for c in result.columns if c.table_name == "orders" and c.column_name == "amount"
        )
        assert amount_col.foreign_key_ref is None

    def test_empty_schema(self, empty_engine) -> None:
        """Introspecting an empty database returns success with no columns."""
        result = introspect_engine(empty_engine)

        assert result.success is True
        assert result.table_count == 0
        assert result.columns == []

    def test_system_schema_excluded(self) -> None:
        """System schemas return empty results immediately."""
        engine = create_engine("sqlite:///:memory:")
        result = introspect_engine(engine, schema="pg_catalog")

        assert result.success is True
        assert result.columns == []
        engine.dispose()


# ---------------------------------------------------------------------------
# Integration: Views
# ---------------------------------------------------------------------------


class TestViewIntrospection:
    """Test that views are included when requested."""

    def test_views_included_by_default(self, sqlite_engine) -> None:
        """Views are included alongside tables by default."""
        # Create a view
        with sqlite_engine.connect() as conn:
            conn.execute(
                __import__("sqlalchemy").text(
                    "CREATE VIEW user_emails AS SELECT id, email FROM users"
                )
            )
            conn.commit()

        result = introspect_engine(sqlite_engine, include_views=True)

        assert result.success is True
        assert result.view_count >= 1
        view_cols = [c for c in result.columns if c.table_name == "user_emails"]
        assert len(view_cols) == 2
        assert all(c.is_view for c in view_cols)

    def test_views_excluded_when_disabled(self, sqlite_engine) -> None:
        """Views can be excluded by setting include_views=False."""
        with sqlite_engine.connect() as conn:
            conn.execute(
                __import__("sqlalchemy").text(
                    "CREATE VIEW user_names AS SELECT id, name FROM users"
                )
            )
            conn.commit()

        result = introspect_engine(sqlite_engine, include_views=False)

        assert result.success is True
        assert result.view_count == 0
        view_cols = [c for c in result.columns if c.is_view]
        assert len(view_cols) == 0


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestIntrospectionErrors:
    """Error handling tests for schema introspection."""

    def test_connection_lost_during_introspection(self) -> None:
        """OperationalError with 'connection' keyword produces connection_lost error type."""
        engine = MagicMock()
        with patch(
            "app.services.schema_introspection.inspect",
            side_effect=OperationalError("statement", {}, Exception("connection closed")),
        ):
            result = introspect_engine(engine)

        assert result.success is False
        assert result.error_type == "connection_lost"

    def test_permission_denied(self) -> None:
        """OperationalError with 'permission denied' produces correct error type."""
        engine = MagicMock()
        with patch(
            "app.services.schema_introspection.inspect",
            side_effect=OperationalError("statement", {}, Exception("permission denied for table")),
        ):
            result = introspect_engine(engine)

        assert result.success is False
        assert result.error_type == "permission_denied"

    def test_generic_error(self) -> None:
        """Unexpected exception produces introspection_error type."""
        engine = MagicMock()
        with patch(
            "app.services.schema_introspection.inspect",
            side_effect=RuntimeError("something unexpected"),
        ):
            result = introspect_engine(engine)

        assert result.success is False
        assert result.error_type == "introspection_error"
        assert "something unexpected" in (result.error_message or "")

    def test_per_table_error_skipped_gracefully(self, sqlite_engine) -> None:
        """If a single table fails introspection, others still succeed."""
        original_get_columns = None

        def patched_get_columns(name, schema=None):
            if name == "users":
                raise OperationalError("statement", {}, Exception("permission denied"))
            return original_get_columns(name, schema=schema)

        from sqlalchemy import inspect as sa_inspect

        insp = sa_inspect(sqlite_engine)
        original_get_columns = insp.get_columns

        with patch("app.services.schema_introspection.inspect") as mock_inspect:
            mock_insp = MagicMock(wraps=insp)
            mock_insp.get_columns = patched_get_columns
            mock_insp.get_table_names = insp.get_table_names
            mock_insp.get_view_names = insp.get_view_names
            mock_insp.get_pk_constraint = insp.get_pk_constraint
            mock_insp.get_foreign_keys = insp.get_foreign_keys
            mock_inspect.return_value = mock_insp

            result = introspect_engine(sqlite_engine)

        assert result.success is True
        # Orders table should still be introspected
        table_names = {c.table_name for c in result.columns}
        assert "orders" in table_names
        # Users table was skipped due to error
        assert "users" not in table_names


# ---------------------------------------------------------------------------
# SchemaMetadata persistence helpers
# ---------------------------------------------------------------------------


class TestColumnsToSchemaRecords:
    """Test conversion of ColumnInfo to dict records."""

    def test_converts_correctly(self) -> None:
        source_id = uuid.uuid4()
        cols = [
            ColumnInfo(
                table_name="users",
                column_name="id",
                data_type="integer",
                raw_type="INTEGER",
                is_nullable=False,
                is_primary_key=True,
            ),
            ColumnInfo(
                table_name="users",
                column_name="email",
                data_type="varchar",
                raw_type="VARCHAR(255)",
                is_nullable=True,
                is_primary_key=False,
                foreign_key_ref=None,
            ),
        ]

        records = columns_to_schema_records(source_id, cols)

        assert len(records) == 2
        assert all(r["source_id"] == source_id for r in records)
        assert all(r["source_type"] == "connection" for r in records)
        assert records[0]["table_name"] == "users"
        assert records[0]["column_name"] == "id"
        assert records[0]["data_type"] == "integer"
        assert records[0]["is_primary_key"] is True

    def test_fk_ref_included(self) -> None:
        source_id = uuid.uuid4()
        cols = [
            ColumnInfo(
                table_name="orders",
                column_name="user_id",
                data_type="integer",
                raw_type="INTEGER",
                is_nullable=False,
                is_primary_key=False,
                foreign_key_ref="users.id",
            ),
        ]

        records = columns_to_schema_records(source_id, cols)

        assert records[0]["foreign_key_ref"] == "users.id"


class TestStoreSchemaMetadata:
    """Integration test for persisting schema metadata via SQLAlchemy."""

    @pytest.fixture
    def db_session(self):
        """Create an in-memory SQLite session with SchemaMetadata table."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        session = session_factory()
        yield session
        session.close()
        engine.dispose()

    def test_stores_and_retrieves_metadata(self, db_session) -> None:
        """store_schema_metadata persists rows that can be queried back."""
        source_id = uuid.uuid4()
        cols = [
            ColumnInfo(
                table_name="products",
                column_name="id",
                data_type="integer",
                raw_type="INTEGER",
                is_nullable=False,
                is_primary_key=True,
            ),
            ColumnInfo(
                table_name="products",
                column_name="name",
                data_type="varchar",
                raw_type="VARCHAR(255)",
                is_nullable=False,
                is_primary_key=False,
            ),
        ]

        count = store_schema_metadata(db_session, source_id, cols)
        db_session.commit()

        assert count == 2

        rows = (
            db_session.query(SchemaMetadata)
            .filter(SchemaMetadata.source_id == source_id)
            .all()
        )
        assert len(rows) == 2
        assert {r.column_name for r in rows} == {"id", "name"}
        assert all(r.source_type == "connection" for r in rows)

    def test_refresh_replaces_existing(self, db_session) -> None:
        """Calling store_schema_metadata again replaces old rows."""
        source_id = uuid.uuid4()
        cols_v1 = [
            ColumnInfo(
                table_name="t",
                column_name="a",
                data_type="integer",
                raw_type="INTEGER",
                is_nullable=True,
                is_primary_key=False,
            ),
        ]
        cols_v2 = [
            ColumnInfo(
                table_name="t",
                column_name="b",
                data_type="text",
                raw_type="TEXT",
                is_nullable=True,
                is_primary_key=False,
            ),
            ColumnInfo(
                table_name="t",
                column_name="c",
                data_type="integer",
                raw_type="INTEGER",
                is_nullable=False,
                is_primary_key=True,
            ),
        ]

        store_schema_metadata(db_session, source_id, cols_v1)
        db_session.commit()

        count = store_schema_metadata(db_session, source_id, cols_v2)
        db_session.commit()

        assert count == 2
        rows = (
            db_session.query(SchemaMetadata)
            .filter(SchemaMetadata.source_id == source_id)
            .all()
        )
        assert len(rows) == 2
        assert {r.column_name for r in rows} == {"b", "c"}

    def test_empty_columns_clears_metadata(self, db_session) -> None:
        """Storing empty column list clears existing metadata."""
        source_id = uuid.uuid4()
        cols = [
            ColumnInfo(
                table_name="t",
                column_name="x",
                data_type="text",
                raw_type="TEXT",
                is_nullable=True,
                is_primary_key=False,
            ),
        ]

        store_schema_metadata(db_session, source_id, cols)
        db_session.commit()

        count = store_schema_metadata(db_session, source_id, [])
        db_session.commit()

        assert count == 0
        rows = (
            db_session.query(SchemaMetadata)
            .filter(SchemaMetadata.source_id == source_id)
            .all()
        )
        assert len(rows) == 0
