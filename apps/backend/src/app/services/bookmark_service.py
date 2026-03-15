"""Bookmark service for CRUD operations on saved insights.

Provides create, list, get, delete, and search operations for bookmarks.
Bookmarks capture SQL queries, chart configurations, and result snapshots
from chat messages for later re-execution and display.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.models.orm import Bookmark, Message

logger = get_logger(__name__)


class BookmarkService:
    """Service layer for bookmark CRUD operations."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_bookmarks(self) -> list[dict[str, Any]]:
        """List all bookmarks ordered by creation date (newest first)."""
        stmt = select(Bookmark).order_by(Bookmark.created_at.desc())
        bookmarks = list(self.session.execute(stmt).scalars().all())

        return [self._to_dict(b) for b in bookmarks]

    def create_bookmark(
        self,
        message_id: uuid.UUID,
        title: str,
    ) -> dict[str, Any]:
        """Create a bookmark from an existing message.

        Copies SQL, chart_config, and a result snapshot from the message
        into the bookmark record.

        Raises:
            ValueError: If the message does not exist.
        """
        message = self.session.get(Message, message_id)
        if message is None:
            raise ValueError(f"Message {message_id} not found")

        # Build result snapshot from message query_result_summary
        result_snapshot = message.query_result_summary

        bookmark = Bookmark(
            message_id=message_id,
            title=title,
            sql=message.sql,
            chart_config=message.chart_config,
            result_snapshot=result_snapshot,
            source_id=message.source_id,
            source_type=message.source_type,
        )
        self.session.add(bookmark)
        self.session.flush()

        logger.info(
            "bookmark_created",
            bookmark_id=str(bookmark.id),
            message_id=str(message_id),
            title=title,
        )

        return self._to_dict(bookmark)

    def get_bookmark(self, bookmark_id: uuid.UUID) -> dict[str, Any] | None:
        """Get a single bookmark by ID. Returns None if not found."""
        bookmark = self.session.get(Bookmark, bookmark_id)
        if bookmark is None:
            return None
        return self._to_dict(bookmark)

    def delete_bookmark(self, bookmark_id: uuid.UUID) -> bool:
        """Delete a bookmark by ID. Returns True if deleted, False if not found."""
        bookmark = self.session.get(Bookmark, bookmark_id)
        if bookmark is None:
            return False

        self.session.delete(bookmark)
        self.session.flush()

        logger.info("bookmark_deleted", bookmark_id=str(bookmark_id))
        return True

    def search_bookmarks(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search bookmarks by title or SQL content (case-insensitive)."""
        search_pattern = f"%{query}%"
        stmt = (
            select(Bookmark)
            .where(
                Bookmark.title.ilike(search_pattern)
                | Bookmark.sql.ilike(search_pattern)
            )
            .order_by(Bookmark.created_at.desc())
            .limit(limit)
        )
        bookmarks = list(self.session.execute(stmt).scalars().all())
        return [self._to_dict(b) for b in bookmarks]

    @staticmethod
    def _to_dict(bookmark: Bookmark) -> dict[str, Any]:
        """Convert a Bookmark ORM instance to a response dict."""
        return {
            "id": str(bookmark.id),
            "message_id": str(bookmark.message_id),
            "title": bookmark.title,
            "sql": bookmark.sql,
            "chart_config": bookmark.chart_config,
            "result_snapshot": bookmark.result_snapshot,
            "source_id": bookmark.source_id,
            "source_type": bookmark.source_type,
            "created_at": (
                bookmark.created_at.isoformat() if bookmark.created_at else None
            ),
        }
