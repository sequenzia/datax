"""Dashboard REST API endpoints.

Provides CRUD endpoints for managing dashboards and their pinned bookmark items.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.errors import AppError
from app.logging import get_logger
from app.services.dashboard_service import DashboardService

logger = get_logger(__name__)

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


class CreateDashboardRequest(BaseModel):
    """Request body for creating a dashboard."""

    title: str = Field(
        ..., min_length=1, max_length=255, description="Dashboard title"
    )


class UpdateDashboardRequest(BaseModel):
    """Request body for updating a dashboard title."""

    title: str = Field(
        ..., min_length=1, max_length=255, description="New dashboard title"
    )


class AddDashboardItemRequest(BaseModel):
    """Request body for pinning a bookmark to a dashboard."""

    bookmark_id: str = Field(..., description="UUID of the bookmark to pin")
    position: int = Field(default=0, ge=0, description="Grid position (0-indexed)")


@router.get("")
def list_dashboards(db: Session = Depends(get_db)) -> dict:
    """List all dashboards ordered by updated_at (newest first)."""
    service = DashboardService(db)
    dashboards = service.list_dashboards()
    return {"dashboards": dashboards}


@router.post("", status_code=201)
def create_dashboard(
    body: CreateDashboardRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Create a new dashboard."""
    service = DashboardService(db)
    dashboard = service.create_dashboard(title=body.title)
    return dashboard


@router.get("/{dashboard_id}")
def get_dashboard(dashboard_id: UUID, db: Session = Depends(get_db)) -> dict:
    """Get a single dashboard by ID with its items."""
    service = DashboardService(db)
    dashboard = service.get_dashboard(dashboard_id)
    if dashboard is None:
        raise AppError(
            code="NOT_FOUND",
            message=f"Dashboard {dashboard_id} not found",
            status_code=404,
        )
    return dashboard


@router.put("/{dashboard_id}")
def update_dashboard(
    dashboard_id: UUID,
    body: UpdateDashboardRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Update a dashboard's title."""
    service = DashboardService(db)
    dashboard = service.update_dashboard(dashboard_id, title=body.title)
    if dashboard is None:
        raise AppError(
            code="NOT_FOUND",
            message=f"Dashboard {dashboard_id} not found",
            status_code=404,
        )
    return dashboard


@router.delete("/{dashboard_id}", status_code=204)
def delete_dashboard(
    dashboard_id: UUID, db: Session = Depends(get_db)
) -> Response:
    """Delete a dashboard and all its items."""
    service = DashboardService(db)
    deleted = service.delete_dashboard(dashboard_id)
    if not deleted:
        raise AppError(
            code="NOT_FOUND",
            message=f"Dashboard {dashboard_id} not found",
            status_code=404,
        )
    return Response(status_code=204)


@router.post("/{dashboard_id}/items", status_code=201)
def add_dashboard_item(
    dashboard_id: UUID,
    body: AddDashboardItemRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Pin a bookmark to a dashboard."""
    try:
        bookmark_uuid = UUID(body.bookmark_id)
    except ValueError:
        raise AppError(
            code="INVALID_UUID",
            message=f"Invalid bookmark_id format: {body.bookmark_id}",
            status_code=400,
        )

    service = DashboardService(db)
    try:
        item = service.add_item(
            dashboard_id=dashboard_id,
            bookmark_id=bookmark_uuid,
            position=body.position,
        )
    except ValueError as exc:
        raise AppError(
            code="NOT_FOUND",
            message=str(exc),
            status_code=404,
        )

    return item


@router.delete("/{dashboard_id}/items/{item_id}", status_code=204)
def remove_dashboard_item(
    dashboard_id: UUID,
    item_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    """Remove an item from a dashboard without deleting the bookmark."""
    service = DashboardService(db)
    removed = service.remove_item(dashboard_id, item_id)
    if not removed:
        raise AppError(
            code="NOT_FOUND",
            message=f"Dashboard item {item_id} not found in dashboard {dashboard_id}",
            status_code=404,
        )
    return Response(status_code=204)
