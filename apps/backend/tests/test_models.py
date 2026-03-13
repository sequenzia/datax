"""Tests for SQLAlchemy ORM models.

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
    Connection,
    Conversation,
    Dataset,
    Message,
    ProviderConfig,
    SavedQuery,
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
            file_size_bytes=1024,
            duckdb_table_name="ds_sales",
        )
        assert dataset.name == "sales.csv"
        assert dataset.file_format == "csv"
        assert dataset.file_size_bytes == 1024

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
            file_size_bytes=100,
            duckdb_table_name="ds_test",
            user_id=None,
        )
        assert dataset.user_id is None

    def test_row_count_nullable(self) -> None:
        dataset = Dataset(
            name="test",
            file_path="/tmp/test.csv",
            file_format="csv",
            file_size_bytes=100,
            duckdb_table_name="ds_test",
        )
        assert dataset.row_count is None

    def test_tablename(self) -> None:
        assert Dataset.__tablename__ == "datasets"

    def test_duckdb_table_name_unique_constraint(self) -> None:
        table = Dataset.__table__
        duckdb_col = table.c.duckdb_table_name
        assert duckdb_col.unique is True


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

    def test_last_tested_at_nullable(self) -> None:
        conn = Connection(
            name="Test",
            db_type="postgresql",
            host="localhost",
            port=5432,
            database_name="testdb",
            username="user",
            encrypted_password=b"enc",
        )
        assert conn.last_tested_at is None

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

    def test_metadata_accepts_none(self) -> None:
        msg = Message(
            conversation_id=uuid.uuid4(),
            role="assistant",
            content="Here are the results.",
            metadata_=None,
        )
        assert msg.metadata_ is None

    def test_metadata_accepts_dict(self) -> None:
        meta = {"sql": "SELECT * FROM sales", "chart_type": "bar"}
        msg = Message(
            conversation_id=uuid.uuid4(),
            role="assistant",
            content="Results",
            metadata_=meta,
        )
        assert msg.metadata_ == meta

    def test_has_conversation_relationship(self) -> None:
        assert hasattr(Message, "conversation")

    def test_foreign_key_to_conversations(self) -> None:
        table = Message.__table__
        fk_targets = set()
        for fk in table.foreign_keys:
            fk_targets.add(fk.target_fullname)
        assert "conversations.id" in fk_targets

    def test_tablename(self) -> None:
        assert Message.__tablename__ == "messages"


class TestSavedQueryModel:
    """Test SavedQuery ORM model definition."""

    def test_instantiate_with_required_fields(self) -> None:
        sq = SavedQuery(
            name="Monthly Revenue",
            sql_content="SELECT SUM(revenue) FROM sales GROUP BY month",
        )
        assert sq.name == "Monthly Revenue"
        assert "SELECT" in sq.sql_content

    def test_source_fields_nullable(self) -> None:
        sq = SavedQuery(
            name="Test",
            sql_content="SELECT 1",
        )
        assert sq.source_id is None
        assert sq.source_type is None

    def test_user_id_accepts_none(self) -> None:
        sq = SavedQuery(
            name="Test",
            sql_content="SELECT 1",
            user_id=None,
        )
        assert sq.user_id is None

    def test_tablename(self) -> None:
        assert SavedQuery.__tablename__ == "saved_queries"


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
            "saved_queries",
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
            "file_size_bytes",
            "row_count",
            "duckdb_table_name",
            "status",
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
            "status",
            "last_tested_at",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(columns)

    def test_message_columns(self, engine) -> None:
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("messages")}
        expected = {"id", "conversation_id", "role", "content", "metadata", "created_at"}
        assert expected.issubset(columns)


class TestDatabaseCRUD:
    """Test basic CRUD operations using in-memory SQLite."""

    def test_create_and_read_dataset(self, session) -> None:
        dataset = Dataset(
            name="test.csv",
            file_path="/data/test.csv",
            file_format="csv",
            file_size_bytes=512,
            duckdb_table_name="ds_test_crud",
        )
        session.add(dataset)
        session.commit()

        result = session.get(Dataset, dataset.id)
        assert result is not None
        assert result.name == "test.csv"
        assert result.file_size_bytes == 512
        assert result.status == "uploading"

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
        assert result.status == "disconnected"

    def test_create_and_read_schema_metadata(self, session) -> None:
        source_id = uuid.uuid4()
        schema = SchemaMetadata(
            source_id=source_id,
            source_type="dataset",
            table_name="sales",
            column_name="amount",
            data_type="DECIMAL",
        )
        session.add(schema)
        session.commit()

        result = session.get(SchemaMetadata, schema.id)
        assert result is not None
        assert result.data_type == "DECIMAL"
        assert result.is_nullable is True
        assert result.is_primary_key is False

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

    def test_create_saved_query(self, session) -> None:
        sq = SavedQuery(
            name="Total Revenue",
            sql_content="SELECT SUM(revenue) FROM sales",
        )
        session.add(sq)
        session.commit()

        result = session.get(SavedQuery, sq.id)
        assert result is not None
        assert result.sql_content == "SELECT SUM(revenue) FROM sales"

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
            file_size_bytes=1,
            duckdb_table_name="ds_auto_uuid",
        )
        conv = Conversation(title="auto-uuid")
        sq = SavedQuery(name="auto-uuid", sql_content="SELECT 1")
        pc = ProviderConfig(
            provider_name="test",
            model_name="test",
            encrypted_api_key=b"test",
        )

        session.add_all([dataset, conv, sq, pc])
        session.commit()

        assert isinstance(dataset.id, uuid.UUID)
        assert isinstance(conv.id, uuid.UUID)
        assert isinstance(sq.id, uuid.UUID)
        assert isinstance(pc.id, uuid.UUID)

    def test_message_metadata_stores_json(self, session) -> None:
        """JSONB metadata field stores and retrieves arbitrary JSON."""
        conv = Conversation(title="JSON test")
        session.add(conv)
        session.flush()

        meta = {
            "sql": "SELECT * FROM users",
            "chart_config": {"type": "bar", "x": "name", "y": "count"},
            "nested": {"deep": [1, 2, 3]},
        }
        msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content="Here are the results",
            metadata_=meta,
        )
        session.add(msg)
        session.commit()

        result = session.get(Message, msg.id)
        assert result is not None
        assert result.metadata_ is not None
        assert result.metadata_["sql"] == "SELECT * FROM users"
        assert result.metadata_["nested"]["deep"] == [1, 2, 3]

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
            file_size_bytes=1,
            duckdb_table_name="ds_duplicate",
        )
        d2 = Dataset(
            name="second",
            file_path="/tmp/2.csv",
            file_format="csv",
            file_size_bytes=2,
            duckdb_table_name="ds_duplicate",
        )
        session.add(d1)
        session.commit()

        session.add(d2)
        with pytest.raises(IntegrityError):
            session.commit()
