"""Bookmark REST API endpoints.

Provides CRUD endpoints for managing bookmarks (saved insights).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.errors import AppError
from app.logging import get_logger
from app.services.bookmark_service import BookmarkService

logger = get_logger(__name__)

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])


class CreateBookmarkRequest(BaseModel):
    """Request body for creating a bookmark."""

    message_id: str = Field(..., description="UUID of the message to bookmark")
    title: str = Field(
        ..., min_length=1, max_length=255, description="Bookmark title"
    )


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
    """Create a bookmark from a chat message.

    Copies SQL, chart_config, and result snapshot from the message
    into a new bookmark record.
    """
    try:
        message_uuid = UUID(body.message_id)
    except ValueError:
        raise AppError(
            code="INVALID_UUID",
            message=f"Invalid message_id format: {body.message_id}",
            status_code=400,
        )

    service = BookmarkService(db)
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
