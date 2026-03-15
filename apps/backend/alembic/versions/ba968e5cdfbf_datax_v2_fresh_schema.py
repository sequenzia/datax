"""datax-v2 fresh schema

Revision ID: ba968e5cdfbf
Revises:
Create Date: 2026-03-14 23:30:58.650150

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "ba968e5cdfbf"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Use JSONB on PostgreSQL, plain JSON on other databases (e.g., SQLite for tests)
JSONVariant = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    """Create all datax-v2 tables."""
    # --- Independent tables (no foreign keys) ---

    op.create_table(
        "connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("db_type", sa.String(length=50), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("database_name", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("encrypted_password", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("analysis_context", JSONVariant, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "dashboards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_format", sa.String(length=50), nullable=False),
        sa.Column(
            "duckdb_table_name", sa.String(length=255), nullable=False, unique=True
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="uploading",
            nullable=False,
        ),
        sa.Column("row_count", sa.BigInteger(), nullable=True),
        sa.Column("data_stats", JSONVariant, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "provider_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("provider_name", sa.String(length=50), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("encrypted_api_key", sa.LargeBinary(), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column(
            "is_default",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_provider_name_user",
        "provider_configs",
        ["provider_name", "user_id"],
        unique=True,
    )

    op.create_table(
        "schema_metadata",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("table_name", sa.String(length=255), nullable=False),
        sa.Column("column_name", sa.String(length=255), nullable=False),
        sa.Column("data_type", sa.String(length=100), nullable=False),
        sa.Column(
            "is_nullable",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "is_primary_key",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("foreign_key_ref", sa.String(length=255), nullable=True),
        sa.Column("ordinal_position", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_schema_source",
        "schema_metadata",
        ["source_id", "source_type"],
        unique=False,
    )
    op.create_index(
        "idx_schema_table", "schema_metadata", ["table_name"], unique=False
    )

    # --- Tables with foreign keys to independent tables ---

    op.create_table(
        "data_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("summarize_results", JSONVariant, nullable=True),
        sa.Column("sample_values", JSONVariant, nullable=True),
        sa.Column(
            "profiled_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_data_profiles_dataset_id",
        "data_profiles",
        ["dataset_id"],
        unique=False,
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sql", sa.Text(), nullable=True),
        sa.Column("chart_config", JSONVariant, nullable=True),
        sa.Column("query_result_summary", JSONVariant, nullable=True),
        sa.Column("execution_time_ms", sa.Float(), nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("source_type", sa.String(length=20), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=True),
        sa.Column("correction_history", JSONVariant, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_messages_conversation_id",
        "messages",
        ["conversation_id"],
        unique=False,
    )

    # --- Tables with foreign keys to tables above ---

    op.create_table(
        "bookmarks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("sql", sa.Text(), nullable=True),
        sa.Column("chart_config", JSONVariant, nullable=True),
        sa.Column("result_snapshot", JSONVariant, nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("source_type", sa.String(length=20), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "dashboard_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dashboard_id", sa.Uuid(), nullable=False),
        sa.Column("bookmark_id", sa.Uuid(), nullable=False),
        sa.Column(
            "position", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["bookmark_id"], ["bookmarks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["dashboard_id"], ["dashboards.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_dashboard_items_dashboard_id",
        "dashboard_items",
        ["dashboard_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop all datax-v2 tables in reverse dependency order."""
    op.drop_table("dashboard_items")
    op.drop_table("bookmarks")
    op.drop_index("idx_messages_conversation_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("idx_data_profiles_dataset_id", table_name="data_profiles")
    op.drop_table("data_profiles")
    op.drop_index("idx_schema_table", table_name="schema_metadata")
    op.drop_index("idx_schema_source", table_name="schema_metadata")
    op.drop_table("schema_metadata")
    op.drop_index("idx_provider_name_user", table_name="provider_configs")
    op.drop_table("provider_configs")
    op.drop_table("datasets")
    op.drop_table("dashboards")
    op.drop_table("conversations")
    op.drop_table("connections")
