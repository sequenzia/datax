"""SQLAlchemy ORM models for all DataX v2 entities.

Defines the 10 core entities using SQLAlchemy 2.0 declarative style:
- Dataset: uploaded file metadata with data_stats
- Connection: external database credentials
- SchemaMetadata: column-level schema for datasets and connections (polymorphic)
- Conversation: chat conversation container with analysis_context
- Message: individual chat message with structured metadata columns
- Bookmark: saved insights with SQL + chart config + result snapshot
- Dashboard: user dashboard container
- DashboardItem: positioned bookmark within a dashboard
- DataProfile: cached data profiling results for datasets
- ProviderConfig: AI provider API keys and model selection
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    Uuid,
    func,
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
    duckdb_table_name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="uploading"
    )
    row_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    data_stats: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)

    # Relationships
    profile: Mapped["DataProfile | None"] = relationship(
        "DataProfile",
        back_populates="dataset",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Connection(CreatedAtMixin, Base):
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


class SchemaMetadata(CreatedAtMixin, Base):
    """Column-level schema metadata for datasets and connections (polymorphic).

    Uses source_id + source_type pattern to reference either a Dataset or
    Connection without a strict foreign key, enabling polymorphic lookups.
    """

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
    ordinal_position: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Conversation(TimestampMixin, Base):
    """Chat conversation container with analysis context."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=generate_uuid
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    analysis_context: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)

    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(CreatedAtMixin, Base):
    """Individual chat message within a conversation.

    v2 replaces the monolithic metadata_ JSONB column with structured columns
    for sql, chart_config, query_result_summary, execution_time_ms, etc.
    """

    __tablename__ = "messages"
    __table_args__ = (
        Index("idx_messages_conversation_id", "conversation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=generate_uuid
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    chart_config: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    query_result_summary: Mapped[dict | None] = mapped_column(
        JSONVariant, nullable=True
    )
    execution_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correction_history: Mapped[list | None] = mapped_column(JSONVariant, nullable=True)

    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )
    bookmark: Mapped["Bookmark | None"] = relationship(
        "Bookmark",
        back_populates="message",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Bookmark(CreatedAtMixin, Base):
    """Saved insight with SQL, chart config, and result snapshot."""

    __tablename__ = "bookmarks"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=generate_uuid
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    chart_config: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    result_snapshot: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    # Relationships
    message: Mapped["Message | None"] = relationship("Message", back_populates="bookmark")
    dashboard_items: Mapped[list["DashboardItem"]] = relationship(
        "DashboardItem",
        back_populates="bookmark",
        cascade="all, delete-orphan",
    )


class Dashboard(TimestampMixin, Base):
    """User dashboard container for pinned bookmarks."""

    __tablename__ = "dashboards"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=generate_uuid
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    # Relationships
    items: Mapped[list["DashboardItem"]] = relationship(
        "DashboardItem",
        back_populates="dashboard",
        cascade="all, delete-orphan",
        order_by="DashboardItem.position",
    )


class DashboardItem(CreatedAtMixin, Base):
    """Positioned bookmark within a dashboard."""

    __tablename__ = "dashboard_items"
    __table_args__ = (
        Index("idx_dashboard_items_dashboard_id", "dashboard_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=generate_uuid
    )
    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False
    )
    bookmark_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("bookmarks.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # Relationships
    dashboard: Mapped["Dashboard"] = relationship(
        "Dashboard", back_populates="items"
    )
    bookmark: Mapped["Bookmark"] = relationship(
        "Bookmark", back_populates="dashboard_items"
    )


class DataProfile(Base):
    """Cached data profiling results for a dataset.

    Uses profiled_at timestamp instead of the standard created_at/updated_at
    mixins, as profiling is a specific point-in-time operation.
    """

    __tablename__ = "data_profiles"
    __table_args__ = (
        Index("idx_data_profiles_dataset_id", "dataset_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=generate_uuid
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    summarize_results: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    sample_values: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    profiled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="profile")


class ProviderConfig(CreatedAtMixin, Base):
    """AI provider configuration with encrypted API key."""

    __tablename__ = "provider_configs"
    __table_args__ = (
        Index(
            "idx_provider_name_user",
            "provider_name",
            "user_id",
            unique=True,
        ),
    )

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
