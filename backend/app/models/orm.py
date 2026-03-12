"""SQLAlchemy ORM models for all DataX entities.

Defines the 7 core entities using SQLAlchemy 2.0 declarative style:
- Dataset: uploaded file metadata
- Connection: external database credentials
- SchemaMetadata: column-level schema for datasets and connections
- Conversation: chat conversation container
- Message: individual chat message within a conversation
- SavedQuery: user-saved SQL queries
- ProviderConfig: AI provider API keys and model selection
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    Uuid,
)
from sqlalchemy import (
    false as sa_false,
)
from sqlalchemy import (
    true as sa_true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, TimestampMixin, generate_uuid

# Use JSONB on PostgreSQL, plain JSON on other databases (e.g., SQLite for tests)
JSONVariant = JSON().with_variant(JSONB, "postgresql")


class Dataset(TimestampMixin, Base):
    """Uploaded file dataset metadata and DuckDB virtual table reference."""

    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=generate_uuid
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_format: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    row_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duckdb_table_name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="uploading"
    )


class Connection(TimestampMixin, Base):
    """External database connection credentials."""

    __tablename__ = "connections"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=generate_uuid
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    db_type: Mapped[str] = mapped_column(String(50), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(nullable=False)
    database_name: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_password: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="disconnected"
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(nullable=True)


class SchemaMetadata(CreatedAtMixin, Base):
    """Column-level schema metadata for datasets and connections (polymorphic)."""

    __tablename__ = "schema_metadata"
    __table_args__ = (
        Index("idx_schema_source", "source_id", "source_type"),
        Index("idx_schema_table", "table_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=generate_uuid
    )
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    column_name: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str] = mapped_column(String(100), nullable=False)
    is_nullable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true()
    )
    is_primary_key: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false()
    )
    foreign_key_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Conversation(TimestampMixin, Base):
    """Chat conversation container."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=generate_uuid
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(CreatedAtMixin, Base):
    """Individual chat message within a conversation."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=generate_uuid
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONVariant, nullable=True
    )

    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )


class SavedQuery(TimestampMixin, Base):
    """User-saved SQL query."""

    __tablename__ = "saved_queries"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=generate_uuid
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sql_content: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(20), nullable=True)


class ProviderConfig(TimestampMixin, Base):
    """AI provider configuration with encrypted API key."""

    __tablename__ = "provider_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=generate_uuid
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    encrypted_api_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false()
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true()
    )
