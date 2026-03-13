"""SQLAlchemy declarative base and shared mixins."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


class TimestampMixin:
    """Mixin providing created_at and updated_at timestamp columns.

    Both columns use server_default for automatic population on INSERT.
    updated_at also uses onupdate for automatic refresh on UPDATE.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CreatedAtMixin:
    """Mixin providing only a created_at timestamp column.

    Used by entities that are immutable after creation (e.g., Message, SchemaMetadata).
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


def generate_uuid() -> uuid.UUID:
    """Generate a new UUID4 for use as a primary key default."""
    return uuid.uuid4()
