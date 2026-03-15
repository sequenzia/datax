"""Dashboard service for CRUD operations on dashboards and dashboard items.

Provides create, list, get, update, delete operations for dashboards,
and pin/unpin bookmark items to dashboards with positioning.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.logging import get_logger
from app.models.orm import Bookmark, Dashboard, DashboardItem

logger = get_logger(__name__)


class DashboardService:
    """Service layer for dashboard and dashboard item CRUD operations."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_dashboards(self) -> list[dict[str, Any]]:
        """List all dashboards ordered by updated_at (newest first)."""
        stmt = (
            select(Dashboard)
            .options(joinedload(Dashboard.items).joinedload(DashboardItem.bookmark))
            .order_by(Dashboard.updated_at.desc())
        )
        dashboards = list(self.session.execute(stmt).unique().scalars().all())
        return [self._dashboard_to_dict(d) for d in dashboards]

    def create_dashboard(self, title: str) -> dict[str, Any]:
        """Create a new dashboard.

        Args:
            title: Dashboard title.

        Returns:
            Dict representation of the created dashboard.
        """
        dashboard = Dashboard(title=title)
        self.session.add(dashboard)
        self.session.flush()

        logger.info(
            "dashboard_created",
            dashboard_id=str(dashboard.id),
            title=title,
        )

        return self._dashboard_to_dict(dashboard)

    def get_dashboard(self, dashboard_id: uuid.UUID) -> dict[str, Any] | None:
        """Get a single dashboard by ID with its items. Returns None if not found."""
        stmt = (
            select(Dashboard)
            .options(joinedload(Dashboard.items).joinedload(DashboardItem.bookmark))
            .where(Dashboard.id == dashboard_id)
        )
        dashboard = self.session.execute(stmt).unique().scalars().first()
        if dashboard is None:
            return None
        return self._dashboard_to_dict(dashboard)

    def update_dashboard(
        self, dashboard_id: uuid.UUID, title: str
    ) -> dict[str, Any] | None:
        """Update a dashboard's title. Returns None if not found."""
        dashboard = self.session.get(Dashboard, dashboard_id)
        if dashboard is None:
            return None

        dashboard.title = title
        self.session.flush()

        logger.info(
            "dashboard_updated",
            dashboard_id=str(dashboard_id),
            title=title,
        )

        # Re-fetch with items loaded
        return self.get_dashboard(dashboard_id)

    def delete_dashboard(self, dashboard_id: uuid.UUID) -> bool:
        """Delete a dashboard and its items. Returns True if deleted, False if not found."""
        dashboard = self.session.get(Dashboard, dashboard_id)
        if dashboard is None:
            return False

        self.session.delete(dashboard)
        self.session.flush()

        logger.info("dashboard_deleted", dashboard_id=str(dashboard_id))
        return True

    def add_item(
        self,
        dashboard_id: uuid.UUID,
        bookmark_id: uuid.UUID,
        position: int = 0,
    ) -> dict[str, Any]:
        """Pin a bookmark to a dashboard at the specified position.

        Args:
            dashboard_id: The dashboard to add the item to.
            bookmark_id: The bookmark to pin.
            position: Grid position (0-indexed).

        Returns:
            Dict representation of the created dashboard item.

        Raises:
            ValueError: If the dashboard or bookmark does not exist.
        """
        dashboard = self.session.get(Dashboard, dashboard_id)
        if dashboard is None:
            raise ValueError(f"Dashboard {dashboard_id} not found")

        bookmark = self.session.get(Bookmark, bookmark_id)
        if bookmark is None:
            raise ValueError(f"Bookmark {bookmark_id} not found")

        item = DashboardItem(
            dashboard_id=dashboard_id,
            bookmark_id=bookmark_id,
            position=position,
        )
        self.session.add(item)
        self.session.flush()

        logger.info(
            "dashboard_item_added",
            dashboard_id=str(dashboard_id),
            bookmark_id=str(bookmark_id),
            item_id=str(item.id),
            position=position,
        )

        return self._item_to_dict(item)

    def remove_item(
        self, dashboard_id: uuid.UUID, item_id: uuid.UUID
    ) -> bool:
        """Remove an item from a dashboard without deleting the bookmark.

        Returns True if removed, False if not found.
        """
        stmt = select(DashboardItem).where(
            DashboardItem.id == item_id,
            DashboardItem.dashboard_id == dashboard_id,
        )
        item = self.session.execute(stmt).scalars().first()
        if item is None:
            return False

        self.session.delete(item)
        self.session.flush()

        logger.info(
            "dashboard_item_removed",
            dashboard_id=str(dashboard_id),
            item_id=str(item_id),
        )
        return True

    @staticmethod
    def _dashboard_to_dict(dashboard: Dashboard) -> dict[str, Any]:
        """Convert a Dashboard ORM instance to a response dict."""
        items = []
        if dashboard.items:
            items = [DashboardService._item_to_dict(item) for item in dashboard.items]

        return {
            "id": str(dashboard.id),
            "title": dashboard.title,
            "items": items,
            "created_at": (
                dashboard.created_at.isoformat() if dashboard.created_at else None
            ),
            "updated_at": (
                dashboard.updated_at.isoformat() if dashboard.updated_at else None
            ),
        }

    @staticmethod
    def _item_to_dict(item: DashboardItem) -> dict[str, Any]:
        """Convert a DashboardItem ORM instance to a response dict."""
        bookmark_dict = None
        if item.bookmark:
            bookmark_dict = {
                "id": str(item.bookmark.id),
                "message_id": str(item.bookmark.message_id),
                "title": item.bookmark.title,
                "sql": item.bookmark.sql,
                "chart_config": item.bookmark.chart_config,
                "result_snapshot": item.bookmark.result_snapshot,
                "source_id": item.bookmark.source_id,
                "source_type": item.bookmark.source_type,
                "created_at": (
                    item.bookmark.created_at.isoformat()
                    if item.bookmark.created_at
                    else None
                ),
            }

        return {
            "id": str(item.id),
            "dashboard_id": str(item.dashboard_id),
            "bookmark_id": str(item.bookmark_id),
            "position": item.position,
            "bookmark": bookmark_dict,
            "created_at": (
                item.created_at.isoformat() if item.created_at else None
            ),
        }
