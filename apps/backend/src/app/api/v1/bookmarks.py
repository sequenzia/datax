"""Bookmark REST API endpoints.

Provides CRUD endpoints for managing bookmarks (saved insights).
Supports two creation modes:
  1. From a message_id (copies data from the persisted message)
  2. Direct data (SQL, chart_config, etc.) for mid-turn pinning
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.errors import AppError
from app.logging import get_logger
from app.services.bookmark_service import BookmarkService

logger = get_logger(__name__)

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])


class CreateBookmarkRequest(BaseModel):
    """Request body for creating a bookmark.

    Supports two modes:
    - message_id mode: copies data from a persisted message
    - direct mode: accepts sql/chart_config/result_snapshot directly
    """

    message_id: str | None = Field(None, description="UUID of the message to bookmark")
    title: str = Field(
        ..., min_length=1, max_length=255, description="Bookmark title"
    )
    sql: str | None = Field(None, description="SQL query for direct-data bookmarks")
    chart_config: dict[str, Any] | None = Field(None, description="Plotly chart config")
    result_snapshot: dict[str, Any] | None = Field(None, description="Query result snapshot")
    source_id: str | None = Field(None, description="UUID of the data source")
    source_type: str | None = Field(None, description="Source type: dataset or connection")

    @model_validator(mode="after")
    def require_message_or_data(self) -> CreateBookmarkRequest:
        has_message = self.message_id is not None
        has_data = any([self.sql, self.source_id])
        if not has_message and not has_data:
            raise ValueError(
                "Either message_id or at least one data field (sql, source_id) is required"
            )
        return self


@router.get("")
def list_bookmarks(db: Session = Depends(get_db)) -> dict:
    """List all bookmarks ordered by creation date (newest first)."""
    service = BookmarkService(db)
    bookmarks = service.list_bookmarks()
    return {"bookmarks": bookmarks}


@router.post("", status_code=201)
def create_bookmark(
    body: CreateBookmarkRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Create a bookmark from a message or from direct data.

    When message_id is provided, copies SQL, chart_config, and result
    snapshot from the message. Otherwise, uses the directly provided fields.
    """
    service = BookmarkService(db)

    if body.message_id is not None:
        try:
            message_uuid = UUID(body.message_id)
        except ValueError:
            raise AppError(
                code="INVALID_UUID",
                message=f"Invalid message_id format: {body.message_id}",
                status_code=400,
            )

        try:
            bookmark = service.create_bookmark(
                message_id=message_uuid,
                title=body.title,
            )
        except ValueError as exc:
            raise AppError(
                code="NOT_FOUND",
                message=str(exc),
                status_code=404,
            )
    else:
        bookmark = service.create_bookmark_direct(
            title=body.title,
            sql=body.sql,
            chart_config=body.chart_config,
            result_snapshot=body.result_snapshot,
            source_id=body.source_id,
            source_type=body.source_type,
        )

    return bookmark


@router.get("/{bookmark_id}")
def get_bookmark(bookmark_id: UUID, db: Session = Depends(get_db)) -> dict:
    """Get a single bookmark by ID."""
    service = BookmarkService(db)
    bookmark = service.get_bookmark(bookmark_id)
    if bookmark is None:
        raise AppError(
            code="NOT_FOUND",
            message=f"Bookmark {bookmark_id} not found",
            status_code=404,
        )
    return bookmark


@router.delete("/{bookmark_id}", status_code=204)
def delete_bookmark(
    bookmark_id: UUID, db: Session = Depends(get_db)
) -> Response:
    """Delete a bookmark by ID."""
    service = BookmarkService(db)
    deleted = service.delete_bookmark(bookmark_id)
    if not deleted:
        raise AppError(
            code="NOT_FOUND",
            message=f"Bookmark {bookmark_id} not found",
            status_code=404,
        )
    return Response(status_code=204)
