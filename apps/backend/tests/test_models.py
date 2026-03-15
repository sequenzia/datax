"""Tests for SQLAlchemy ORM models (v2 schema).

Unit tests verify model instantiation, field types, constraints, and relationships.
Integration tests use an in-memory SQLite database to verify table creation and
basic CRUD operations (note: JSONB and LargeBinary behave differently in SQLite
vs PostgreSQL, but structural correctness is validated).
"""

import uuid

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.models import (
    Base,
    Bookmark,
    Connection,
    Conversation,
    Dashboard,
    DashboardItem,
    DataProfile,
    Dataset,
    Message,
    ProviderConfig,
    SchemaMetadata,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine():
    """Create an in-memory SQLite engine with all tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    """Create a SQLAlchemy session bound to the in-memory engine."""
    with Session(engine) as session:
        yield session


# ---------------------------------------------------------------------------
# Unit: Model instantiation with valid data
# ---------------------------------------------------------------------------


class TestDatasetModel:
    """Test Dataset ORM model definition."""

    def test_instantiate_with_required_fields(self) -> None:
        dataset = Dataset(
            name="sales.csv",
            file_path="/data/uploads/sales.csv",
            file_format="csv",
            duckdb_table_name="ds_sales",
        )
        assert dataset.name == "sales.csv"
        assert dataset.file_format == "csv"

    def test_id_column_has_default(self) -> None:
        """UUID primary key column has a callable default for auto-generation."""
        id_col = Dataset.__table__.c.id
        assert id_col.default is not None
        assert callable(id_col.default.arg)

    def test_user_id_accepts_none(self) -> None:
        dataset = Dataset(
            name="test",
            file_path="/tmp/test.csv",
            file_format="csv",
            duckdb_table_name="ds_test",
            user_id=None,
        )
        assert dataset.user_id is None

    def test_row_count_nullable(self) -> None:
        dataset = Dataset(
            name="test",
            file_path="/tmp/test.csv",
            file_format="csv",
            duckdb_table_name="ds_test",
        )
        assert dataset.row_count is None

    def test_data_stats_nullable(self) -> None:
        dataset = Dataset(
            name="test",
            file_path="/tmp/test.csv",
            file_format="csv",
            duckdb_table_name="ds_test",
        )
        assert dataset.data_stats is None

    def test_data_stats_accepts_dict(self) -> None:
        stats = {"row_count": 1000, "column_count": 5, "sample": [1, 2, 3]}
        dataset = Dataset(
            name="test",
            file_path="/tmp/test.csv",
            file_format="csv",
            duckdb_table_name="ds_test",
            data_stats=stats,
        )
        assert dataset.data_stats == stats

    def test_tablename(self) -> None:
        assert Dataset.__tablename__ == "datasets"

    def test_duckdb_table_name_unique_constraint(self) -> None:
        table = Dataset.__table__
        duckdb_col = table.c.duckdb_table_name
        assert duckdb_col.unique is True

    def test_has_profile_relationship(self) -> None:
        assert hasattr(Dataset, "profile")


class TestConnectionModel:
    """Test Connection ORM model definition."""

    def test_instantiate_with_required_fields(self) -> None:
        conn = Connection(
            name="Production DB",
            db_type="postgresql",
            host="localhost",
            port=5432,
            database_name="mydb",
            username="admin",
            encrypted_password=b"encrypted_data",
        )
        assert conn.name == "Production DB"
        assert conn.db_type == "postgresql"
        assert conn.port == 5432

    def test_encrypted_password_is_bytes(self) -> None:
        conn = Connection(
            name="Test",
            db_type="mysql",
            host="localhost",
            port=3306,
            database_name="testdb",
            username="root",
            encrypted_password=b"\x00\x01\x02\xff",
        )
        assert isinstance(conn.encrypted_password, bytes)

    def test_user_id_accepts_none(self) -> None:
        conn = Connection(
            name="Test",
            db_type="postgresql",
            host="localhost",
            port=5432,
            database_name="testdb",
            username="user",
            encrypted_password=b"enc",
            user_id=None,
        )
        assert conn.user_id is None

    def test_tablename(self) -> None:
        assert Connection.__tablename__ == "connections"

    def test_uses_created_at_mixin(self) -> None:
        """Connection uses CreatedAtMixin (created_at only, no updated_at)."""
        table = Connection.__table__
        col_names = {col.name for col in table.columns}
        assert "created_at" in col_names


class TestSchemaMetadataModel:
    """Test SchemaMetadata ORM model definition."""

    def test_instantiate_with_required_fields(self) -> None:
        schema = SchemaMetadata(
            source_id=uuid.uuid4(),
            source_type="dataset",
            table_name="sales",
            column_name="revenue",
            data_type="DOUBLE",
        )
        assert schema.source_type == "dataset"
        assert schema.column_name == "revenue"

    def test_defaults(self) -> None:
        schema = SchemaMetadata(
            source_id=uuid.uuid4(),
            source_type="connection",
            table_name="users",
            column_name="id",
            data_type="INTEGER",
        )
        assert schema.foreign_key_ref is None
        assert schema.ordinal_position is None

    def test_ordinal_position_accepts_value(self) -> None:
        schema = SchemaMetadata(
            source_id=uuid.uuid4(),
            source_type="dataset",
            table_name="orders",
            column_name="price",
            data_type="DECIMAL",
            ordinal_position=3,
        )
        assert schema.ordinal_position == 3

    def test_polymorphic_dataset_source_type(self) -> None:
        schema = SchemaMetadata(
            source_id=uuid.uuid4(),
            source_type="dataset",
            table_name="t",
            column_name="c",
            data_type="TEXT",
        )
        assert schema.source_type == "dataset"

    def test_polymorphic_connection_source_type(self) -> None:
        schema = SchemaMetadata(
            source_id=uuid.uuid4(),
            source_type="connection",
            table_name="t",
            column_name="c",
            data_type="TEXT",
        )
        assert schema.source_type == "connection"

    def test_indexes_defined(self) -> None:
        table = SchemaMetadata.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "idx_schema_source" in index_names
        assert "idx_schema_table" in index_names

    def test_source_index_columns(self) -> None:
        table = SchemaMetadata.__table__
        for idx in table.indexes:
            if idx.name == "idx_schema_source":
                col_names = [col.name for col in idx.columns]
                assert col_names == ["source_id", "source_type"]
                break

    def test_table_index_columns(self) -> None:
        table = SchemaMetadata.__table__
        for idx in table.indexes:
            if idx.name == "idx_schema_table":
                col_names = [col.name for col in idx.columns]
                assert col_names == ["table_name"]
                break

    def test_tablename(self) -> None:
        assert SchemaMetadata.__tablename__ == "schema_metadata"


class TestConversationModel:
    """Test Conversation ORM model definition."""

    def test_instantiate_with_required_fields(self) -> None:
        conv = Conversation(title="Data analysis session")
        assert conv.title == "Data analysis session"

    def test_user_id_accepts_none(self) -> None:
        conv = Conversation(title="Test", user_id=None)
        assert conv.user_id is None

    def test_analysis_context_nullable(self) -> None:
        conv = Conversation(title="Test")
        assert conv.analysis_context is None

    def test_analysis_context_accepts_dict(self) -> None:
        ctx = {"datasets": ["sales"], "last_query": "SELECT 1"}
        conv = Conversation(title="Test", analysis_context=ctx)
        assert conv.analysis_context == ctx

    def test_has_messages_relationship(self) -> None:
        assert hasattr(Conversation, "messages")

    def test_tablename(self) -> None:
        assert Conversation.__tablename__ == "conversations"


class TestMessageModel:
    """Test Message ORM model definition."""

    def test_instantiate_with_required_fields(self) -> None:
        msg = Message(
            conversation_id=uuid.uuid4(),
            role="user",
            content="What are the total sales?",
        )
        assert msg.role == "user"
        assert msg.content == "What are the total sales?"

    def test_sql_nullable(self) -> None:
        msg = Message(
            conversation_id=uuid.uuid4(),
            role="assistant",
            content="Results",
        )
        assert msg.sql is None

    def test_sql_accepts_text(self) -> None:
        msg = Message(
            conversation_id=uuid.uuid4(),
            role="assistant",
            content="Results",
            sql="SELECT SUM(amount) FROM sales",
        )
        assert msg.sql == "SELECT SUM(amount) FROM sales"

    def test_chart_config_nullable(self) -> None:
        msg = Message(
            conversation_id=uuid.uuid4(),
            role="assistant",
            content="Results",
        )
        assert msg.chart_config is None

    def test_chart_config_accepts_dict(self) -> None:
        config = {"type": "bar", "x": "month", "y": "revenue"}
        msg = Message(
            conversation_id=uuid.uuid4(),
            role="assistant",
            content="Results",
            chart_config=config,
        )
        assert msg.chart_config == config

    def test_query_result_summary_nullable(self) -> None:
        msg = Message(
            conversation_id=uuid.uuid4(),
            role="assistant",
            content="Results",
        )
        assert msg.query_result_summary is None

    def test_execution_time_ms_nullable(self) -> None:
        msg = Message(
            conversation_id=uuid.uuid4(),
            role="assistant",
            content="Results",
        )
        assert msg.execution_time_ms is None

    def test_source_fields_nullable(self) -> None:
        msg = Message(
            conversation_id=uuid.uuid4(),
            role="user",
            content="Query",
        )
        assert msg.source_id is None
        assert msg.source_type is None

    def test_attempts_nullable(self) -> None:
        msg = Message(
            conversation_id=uuid.uuid4(),
            role="assistant",
            content="Results",
        )
        assert msg.attempts is None

    def test_correction_history_nullable(self) -> None:
        msg = Message(
            conversation_id=uuid.uuid4(),
            role="assistant",
            content="Results",
        )
        assert msg.correction_history is None

    def test_has_conversation_relationship(self) -> None:
        assert hasattr(Message, "conversation")

    def test_has_bookmark_relationship(self) -> None:
        assert hasattr(Message, "bookmark")

    def test_foreign_key_to_conversations(self) -> None:
        table = Message.__table__
        fk_targets = set()
        for fk in table.foreign_keys:
            fk_targets.add(fk.target_fullname)
        assert "conversations.id" in fk_targets

    def test_tablename(self) -> None:
        assert Message.__tablename__ == "messages"


class TestBookmarkModel:
    """Test Bookmark ORM model definition."""

    def test_instantiate_with_required_fields(self) -> None:
        bm = Bookmark(
            message_id=uuid.uuid4(),
            title="Q4 Revenue by Region",
        )
        assert bm.title == "Q4 Revenue by Region"

    def test_sql_nullable(self) -> None:
        bm = Bookmark(
            message_id=uuid.uuid4(),
            title="Test",
        )
        assert bm.sql is None

    def test_chart_config_nullable(self) -> None:
        bm = Bookmark(
            message_id=uuid.uuid4(),
            title="Test",
        )
        assert bm.chart_config is None

    def test_result_snapshot_nullable(self) -> None:
        bm = Bookmark(
            message_id=uuid.uuid4(),
            title="Test",
        )
        assert bm.result_snapshot is None

    def test_source_fields_nullable(self) -> None:
        bm = Bookmark(
            message_id=uuid.uuid4(),
            title="Test",
        )
        assert bm.source_id is None
        assert bm.source_type is None

    def test_user_id_accepts_none(self) -> None:
        bm = Bookmark(
            message_id=uuid.uuid4(),
            title="Test",
            user_id=None,
        )
        assert bm.user_id is None

    def test_has_message_relationship(self) -> None:
        assert hasattr(Bookmark, "message")

    def test_has_dashboard_items_relationship(self) -> None:
        assert hasattr(Bookmark, "dashboard_items")

    def test_foreign_key_to_messages(self) -> None:
        table = Bookmark.__table__
        fk_targets = set()
        for fk in table.foreign_keys:
            fk_targets.add(fk.target_fullname)
        assert "messages.id" in fk_targets

    def test_tablename(self) -> None:
        assert Bookmark.__tablename__ == "bookmarks"


class TestDashboardModel:
    """Test Dashboard ORM model definition."""

    def test_instantiate_with_required_fields(self) -> None:
        dash = Dashboard(title="Sales Dashboard")
        assert dash.title == "Sales Dashboard"

    def test_user_id_accepts_none(self) -> None:
        dash = Dashboard(title="Test", user_id=None)
        assert dash.user_id is None

    def test_has_items_relationship(self) -> None:
        assert hasattr(Dashboard, "items")

    def test_tablename(self) -> None:
        assert Dashboard.__tablename__ == "dashboards"


class TestDashboardItemModel:
    """Test DashboardItem ORM model definition."""

    def test_instantiate_with_required_fields(self) -> None:
        item = DashboardItem(
            dashboard_id=uuid.uuid4(),
            bookmark_id=uuid.uuid4(),
            position=0,
        )
        assert item.position == 0

    def test_has_dashboard_relationship(self) -> None:
        assert hasattr(DashboardItem, "dashboard")

    def test_has_bookmark_relationship(self) -> None:
        assert hasattr(DashboardItem, "bookmark")

    def test_foreign_key_to_dashboards(self) -> None:
        table = DashboardItem.__table__
        fk_targets = set()
        for fk in table.foreign_keys:
            fk_targets.add(fk.target_fullname)
        assert "dashboards.id" in fk_targets

    def test_foreign_key_to_bookmarks(self) -> None:
        table = DashboardItem.__table__
        fk_targets = set()
        for fk in table.foreign_keys:
            fk_targets.add(fk.target_fullname)
        assert "bookmarks.id" in fk_targets

    def test_tablename(self) -> None:
        assert DashboardItem.__tablename__ == "dashboard_items"


class TestDataProfileModel:
    """Test DataProfile ORM model definition."""

    def test_instantiate_with_required_fields(self) -> None:
        dp = DataProfile(
            dataset_id=uuid.uuid4(),
        )
        assert dp.summarize_results is None
        assert dp.sample_values is None

    def test_summarize_results_accepts_dict(self) -> None:
        results = {"columns": 5, "rows": 1000}
        dp = DataProfile(
            dataset_id=uuid.uuid4(),
            summarize_results=results,
        )
        assert dp.summarize_results == results

    def test_sample_values_accepts_dict(self) -> None:
        samples = {"col1": [1, 2, 3], "col2": ["a", "b", "c"]}
        dp = DataProfile(
            dataset_id=uuid.uuid4(),
            sample_values=samples,
        )
        assert dp.sample_values == samples

    def test_foreign_key_to_datasets(self) -> None:
        table = DataProfile.__table__
        fk_targets = set()
        for fk in table.foreign_keys:
            fk_targets.add(fk.target_fullname)
        assert "datasets.id" in fk_targets

    def test_has_dataset_relationship(self) -> None:
        assert hasattr(DataProfile, "dataset")

    def test_tablename(self) -> None:
        assert DataProfile.__tablename__ == "data_profiles"


class TestProviderConfigModel:
    """Test ProviderConfig ORM model definition."""

    def test_instantiate_with_required_fields(self) -> None:
        pc = ProviderConfig(
            provider_name="openai",
            model_name="gpt-4o",
            encrypted_api_key=b"encrypted_key_data",
        )
        assert pc.provider_name == "openai"
        assert pc.model_name == "gpt-4o"

    def test_encrypted_api_key_is_bytes(self) -> None:
        pc = ProviderConfig(
            provider_name="anthropic",
            model_name="claude-sonnet-4-20250514",
            encrypted_api_key=b"\x00\xff\xfe",
        )
        assert isinstance(pc.encrypted_api_key, bytes)

    def test_base_url_nullable(self) -> None:
        pc = ProviderConfig(
            provider_name="openai",
            model_name="gpt-4o",
            encrypted_api_key=b"key",
        )
        assert pc.base_url is None

    def test_user_id_accepts_none(self) -> None:
        pc = ProviderConfig(
            provider_name="openai",
            model_name="gpt-4o",
            encrypted_api_key=b"key",
            user_id=None,
        )
        assert pc.user_id is None

    def test_provider_name_unique_index(self) -> None:
        """ProviderConfig has a unique index on (provider_name, user_id)."""
        table = ProviderConfig.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "idx_provider_name_user" in index_names
        for idx in table.indexes:
            if idx.name == "idx_provider_name_user":
                assert idx.unique is True

    def test_tablename(self) -> None:
        assert ProviderConfig.__tablename__ == "provider_configs"


# ---------------------------------------------------------------------------
# Integration: Table creation and basic CRUD with in-memory SQLite
# ---------------------------------------------------------------------------


class TestTableCreation:
    """Verify all tables are created correctly in the database."""

    def test_all_tables_created(self, engine) -> None:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        expected = {
            "datasets",
            "connections",
            "schema_metadata",
            "conversations",
            "messages",
            "bookmarks",
            "dashboards",
            "dashboard_items",
            "data_profiles",
            "provider_configs",
        }
        assert expected.issubset(table_names)

    def test_dataset_columns(self, engine) -> None:
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("datasets")}
        expected = {
            "id",
            "user_id",
            "name",
            "file_path",
            "file_format",
            "duckdb_table_name",
            "status",
            "row_count",
            "data_stats",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(columns)

    def test_connection_columns(self, engine) -> None:
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("connections")}
        expected = {
            "id",
            "user_id",
            "name",
            "db_type",
            "host",
            "port",
            "database_name",
            "username",
            "encrypted_password",
            "created_at",
        }
        assert expected.issubset(columns)

    def test_message_columns(self, engine) -> None:
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("messages")}
        expected = {
            "id",
            "conversation_id",
            "role",
            "content",
            "sql",
            "chart_config",
            "query_result_summary",
            "execution_time_ms",
            "source_id",
            "source_type",
            "attempts",
            "correction_history",
            "created_at",
        }
        assert expected.issubset(columns)

    def test_bookmark_columns(self, engine) -> None:
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("bookmarks")}
        expected = {
            "id",
            "message_id",
            "title",
            "sql",
            "chart_config",
            "result_snapshot",
            "source_id",
            "source_type",
            "user_id",
            "created_at",
        }
        assert expected.issubset(columns)

    def test_dashboard_columns(self, engine) -> None:
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("dashboards")}
        expected = {
            "id",
            "title",
            "user_id",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(columns)

    def test_dashboard_item_columns(self, engine) -> None:
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("dashboard_items")}
        expected = {
            "id",
            "dashboard_id",
            "bookmark_id",
            "position",
            "created_at",
        }
        assert expected.issubset(columns)

    def test_data_profile_columns(self, engine) -> None:
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("data_profiles")}
        expected = {
            "id",
            "dataset_id",
            "summarize_results",
            "sample_values",
            "profiled_at",
        }
        assert expected.issubset(columns)

    def test_schema_metadata_columns(self, engine) -> None:
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("schema_metadata")}
        expected = {
            "id",
            "source_id",
            "source_type",
            "table_name",
            "column_name",
            "data_type",
            "is_nullable",
            "is_primary_key",
            "foreign_key_ref",
            "ordinal_position",
        }
        assert expected.issubset(columns)

    def test_conversation_columns(self, engine) -> None:
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("conversations")}
        expected = {
            "id",
            "user_id",
            "title",
            "analysis_context",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(columns)


class TestDatabaseCRUD:
    """Test basic CRUD operations using in-memory SQLite."""

    def test_create_and_read_dataset(self, session) -> None:
        dataset = Dataset(
            name="test.csv",
            file_path="/data/test.csv",
            file_format="csv",
            duckdb_table_name="ds_test_crud",
        )
        session.add(dataset)
        session.commit()

        result = session.get(Dataset, dataset.id)
        assert result is not None
        assert result.name == "test.csv"
        assert result.status == "uploading"

    def test_create_dataset_with_data_stats(self, session) -> None:
        stats = {"row_count": 500, "columns": ["a", "b"]}
        dataset = Dataset(
            name="stats.csv",
            file_path="/data/stats.csv",
            file_format="csv",
            duckdb_table_name="ds_stats",
            data_stats=stats,
        )
        session.add(dataset)
        session.commit()

        result = session.get(Dataset, dataset.id)
        assert result is not None
        assert result.data_stats is not None
        assert result.data_stats["row_count"] == 500

    def test_create_and_read_connection(self, session) -> None:
        conn = Connection(
            name="Test DB",
            db_type="postgresql",
            host="localhost",
            port=5432,
            database_name="testdb",
            username="user",
            encrypted_password=b"encrypted",
        )
        session.add(conn)
        session.commit()

        result = session.get(Connection, conn.id)
        assert result is not None
        assert result.db_type == "postgresql"

    def test_create_and_read_schema_metadata(self, session) -> None:
        source_id = uuid.uuid4()
        schema = SchemaMetadata(
            source_id=source_id,
            source_type="dataset",
            table_name="sales",
            column_name="amount",
            data_type="DECIMAL",
            ordinal_position=1,
        )
        session.add(schema)
        session.commit()

        result = session.get(SchemaMetadata, schema.id)
        assert result is not None
        assert result.data_type == "DECIMAL"
        assert result.is_nullable is True
        assert result.is_primary_key is False
        assert result.ordinal_position == 1

    def test_schema_metadata_polymorphic_connection(self, session) -> None:
        """SchemaMetadata works with source_type='connection'."""
        source_id = uuid.uuid4()
        schema = SchemaMetadata(
            source_id=source_id,
            source_type="connection",
            table_name="users",
            column_name="email",
            data_type="VARCHAR",
            ordinal_position=2,
        )
        session.add(schema)
        session.commit()

        result = session.get(SchemaMetadata, schema.id)
        assert result is not None
        assert result.source_type == "connection"

    def test_conversation_with_analysis_context(self, session) -> None:
        ctx = {"datasets": ["sales.csv"], "follow_up_count": 3}
        conv = Conversation(title="Analysis session", analysis_context=ctx)
        session.add(conv)
        session.commit()

        result = session.get(Conversation, conv.id)
        assert result is not None
        assert result.analysis_context["datasets"] == ["sales.csv"]

    def test_conversation_message_relationship(self, session) -> None:
        conv = Conversation(title="Test conversation")
        session.add(conv)
        session.flush()

        msg1 = Message(
            conversation_id=conv.id,
            role="user",
            content="Hello",
        )
        msg2 = Message(
            conversation_id=conv.id,
            role="assistant",
            content="Hi there!",
            sql="SELECT 1",
            chart_config={"type": "bar"},
            execution_time_ms=45.2,
            attempts=1,
        )
        session.add_all([msg1, msg2])
        session.commit()

        result = session.get(Conversation, conv.id)
        assert result is not None
        assert len(result.messages) == 2
        roles = [m.role for m in result.messages]
        assert "user" in roles
        assert "assistant" in roles

    def test_message_back_populates_conversation(self, session) -> None:
        conv = Conversation(title="Back-populate test")
        session.add(conv)
        session.flush()

        msg = Message(
            conversation_id=conv.id,
            role="user",
            content="Test message",
        )
        session.add(msg)
        session.commit()

        result = session.get(Message, msg.id)
        assert result is not None
        assert result.conversation is not None
        assert result.conversation.title == "Back-populate test"

    def test_message_structured_fields(self, session) -> None:
        """Message stores structured metadata in dedicated columns."""
        conv = Conversation(title="Structured test")
        session.add(conv)
        session.flush()

        msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content="Here are the results",
            sql="SELECT SUM(revenue) FROM sales",
            chart_config={"type": "bar", "x": "month", "y": "revenue"},
            query_result_summary={"rows": 12, "columns": 2},
            execution_time_ms=123.5,
            source_id="dataset-uuid",
            source_type="dataset",
            attempts=2,
            correction_history=[
                {"attempt": 1, "error": "column not found"},
                {"attempt": 2, "sql": "SELECT SUM(revenue) FROM sales"},
            ],
        )
        session.add(msg)
        session.commit()

        result = session.get(Message, msg.id)
        assert result is not None
        assert result.sql == "SELECT SUM(revenue) FROM sales"
        assert result.chart_config["type"] == "bar"
        assert result.query_result_summary["rows"] == 12
        assert result.execution_time_ms == 123.5
        assert result.source_id == "dataset-uuid"
        assert result.source_type == "dataset"
        assert result.attempts == 2
        assert len(result.correction_history) == 2

    def test_cascade_delete_conversation_removes_messages(self, session) -> None:
        conv = Conversation(title="Cascade test")
        session.add(conv)
        session.flush()

        msg = Message(
            conversation_id=conv.id,
            role="user",
            content="Will be deleted",
        )
        session.add(msg)
        session.commit()
        msg_id = msg.id

        session.delete(conv)
        session.commit()

        assert session.get(Message, msg_id) is None

    def test_bookmark_crud(self, session) -> None:
        """Create and read a bookmark linked to a message."""
        conv = Conversation(title="Bookmark test")
        session.add(conv)
        session.flush()

        msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content="Results",
            sql="SELECT * FROM sales",
        )
        session.add(msg)
        session.flush()

        bm = Bookmark(
            message_id=msg.id,
            title="Q4 Revenue",
            sql="SELECT * FROM sales",
            chart_config={"type": "bar"},
            result_snapshot={"data": [1, 2, 3]},
            source_type="dataset",
        )
        session.add(bm)
        session.commit()

        result = session.get(Bookmark, bm.id)
        assert result is not None
        assert result.title == "Q4 Revenue"
        assert result.sql == "SELECT * FROM sales"
        assert result.chart_config == {"type": "bar"}
        assert result.result_snapshot == {"data": [1, 2, 3]}

    def test_cascade_delete_message_removes_bookmark(self, session) -> None:
        """Deleting a message cascades to delete its bookmark."""
        conv = Conversation(title="Cascade bookmark test")
        session.add(conv)
        session.flush()

        msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content="Results",
        )
        session.add(msg)
        session.flush()

        bm = Bookmark(
            message_id=msg.id,
            title="To be deleted",
        )
        session.add(bm)
        session.commit()
        bm_id = bm.id

        session.delete(conv)
        session.commit()

        assert session.get(Bookmark, bm_id) is None

    def test_dashboard_with_items(self, session) -> None:
        """Create a dashboard with items linked to bookmarks."""
        conv = Conversation(title="Dashboard test")
        session.add(conv)
        session.flush()

        msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content="Results",
        )
        session.add(msg)
        session.flush()

        bm = Bookmark(message_id=msg.id, title="Bookmark 1")
        session.add(bm)
        session.flush()

        dash = Dashboard(title="Sales Dashboard")
        session.add(dash)
        session.flush()

        item = DashboardItem(
            dashboard_id=dash.id,
            bookmark_id=bm.id,
            position=0,
        )
        session.add(item)
        session.commit()

        result = session.get(Dashboard, dash.id)
        assert result is not None
        assert len(result.items) == 1
        assert result.items[0].bookmark.title == "Bookmark 1"

    def test_cascade_delete_dashboard_removes_items(self, session) -> None:
        """Deleting a dashboard cascades to delete its items."""
        conv = Conversation(title="Dashboard cascade")
        session.add(conv)
        session.flush()

        msg = Message(
            conversation_id=conv.id, role="assistant", content="R"
        )
        session.add(msg)
        session.flush()

        bm = Bookmark(message_id=msg.id, title="BM")
        session.add(bm)
        session.flush()

        dash = Dashboard(title="Delete me")
        session.add(dash)
        session.flush()

        item = DashboardItem(
            dashboard_id=dash.id, bookmark_id=bm.id, position=0
        )
        session.add(item)
        session.commit()
        item_id = item.id

        session.delete(dash)
        session.commit()

        assert session.get(DashboardItem, item_id) is None

    def test_data_profile_crud(self, session) -> None:
        """Create and read a data profile linked to a dataset."""
        dataset = Dataset(
            name="profile_test.csv",
            file_path="/data/profile_test.csv",
            file_format="csv",
            duckdb_table_name="ds_profile_test",
        )
        session.add(dataset)
        session.flush()

        profile = DataProfile(
            dataset_id=dataset.id,
            summarize_results={"columns": 5, "rows": 1000},
            sample_values={"col1": [1, 2, 3]},
        )
        session.add(profile)
        session.commit()

        result = session.get(DataProfile, profile.id)
        assert result is not None
        assert result.summarize_results["columns"] == 5
        assert result.sample_values["col1"] == [1, 2, 3]

    def test_cascade_delete_dataset_removes_profile(self, session) -> None:
        """Deleting a dataset cascades to delete its profile."""
        dataset = Dataset(
            name="cascade_profile.csv",
            file_path="/data/cascade.csv",
            file_format="csv",
            duckdb_table_name="ds_cascade_profile",
        )
        session.add(dataset)
        session.flush()

        profile = DataProfile(
            dataset_id=dataset.id,
            summarize_results={"test": True},
        )
        session.add(profile)
        session.commit()
        profile_id = profile.id

        session.delete(dataset)
        session.commit()

        assert session.get(DataProfile, profile_id) is None

    def test_dataset_profile_relationship(self, session) -> None:
        """Dataset.profile relationship returns the linked DataProfile."""
        dataset = Dataset(
            name="rel_test.csv",
            file_path="/data/rel.csv",
            file_format="csv",
            duckdb_table_name="ds_rel_test",
        )
        session.add(dataset)
        session.flush()

        profile = DataProfile(
            dataset_id=dataset.id,
            summarize_results={"ok": True},
        )
        session.add(profile)
        session.commit()

        result = session.get(Dataset, dataset.id)
        assert result is not None
        assert result.profile is not None
        assert result.profile.summarize_results == {"ok": True}

    def test_create_provider_config(self, session) -> None:
        pc = ProviderConfig(
            provider_name="openai",
            model_name="gpt-4o",
            encrypted_api_key=b"encrypted_key",
        )
        session.add(pc)
        session.commit()

        result = session.get(ProviderConfig, pc.id)
        assert result is not None
        assert result.provider_name == "openai"
        assert result.is_default is False
        assert result.is_active is True

    def test_uuid_primary_keys_auto_generate(self, session) -> None:
        """All models auto-generate UUID primary keys on insert."""
        dataset = Dataset(
            name="auto-uuid",
            file_path="/tmp/auto.csv",
            file_format="csv",
            duckdb_table_name="ds_auto_uuid",
        )
        conv = Conversation(title="auto-uuid")
        pc = ProviderConfig(
            provider_name="test_auto",
            model_name="test",
            encrypted_api_key=b"test",
        )

        session.add_all([dataset, conv, pc])
        session.commit()

        assert isinstance(dataset.id, uuid.UUID)
        assert isinstance(conv.id, uuid.UUID)
        assert isinstance(pc.id, uuid.UUID)

    def test_encrypted_fields_store_binary(self, session) -> None:
        """BYTEA fields (encrypted_password, encrypted_api_key) store binary data."""
        binary_data = bytes(range(256))

        conn = Connection(
            name="Binary test",
            db_type="postgresql",
            host="localhost",
            port=5432,
            database_name="test",
            username="user",
            encrypted_password=binary_data,
        )
        session.add(conn)
        session.commit()

        result = session.get(Connection, conn.id)
        assert result is not None
        assert result.encrypted_password == binary_data

    def test_duckdb_table_name_unique_violation(self, session) -> None:
        """Duplicate duckdb_table_name raises IntegrityError."""
        from sqlalchemy.exc import IntegrityError

        d1 = Dataset(
            name="first",
            file_path="/tmp/1.csv",
            file_format="csv",
            duckdb_table_name="ds_duplicate",
        )
        d2 = Dataset(
            name="second",
            file_path="/tmp/2.csv",
            file_format="csv",
            duckdb_table_name="ds_duplicate",
        )
        session.add(d1)
        session.commit()

        session.add(d2)
        with pytest.raises(IntegrityError):
            session.commit()
