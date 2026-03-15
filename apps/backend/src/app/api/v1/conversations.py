"""Conversation CRUD API endpoints.

Provides REST endpoints for managing conversations and retrieving message history.
"""

from __future__ import annotations

import re
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, literal, select
from sqlalchemy.orm import Session, selectinload

from app.dependencies import get_db
from app.errors import AppError
from app.logging import get_logger
from app.models.orm import Conversation, Message

logger = get_logger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


class UpdateConversationRequest(BaseModel):
    """Request body for updating a conversation."""

    title: str = Field(..., min_length=1, max_length=255, description="New conversation title")

_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _validate_uuid(value: str, field_name: str = "id") -> UUID:
    """Validate and parse a UUID string, raising 400 on invalid format."""
    if not _UUID_PATTERN.match(value):
        raise AppError(
            code="INVALID_UUID",
            message=f"Invalid UUID format for {field_name}: {value}",
            status_code=400,
        )
    return UUID(value)


@router.post("", status_code=201)
def create_conversation(db: Session = Depends(get_db)) -> dict:
    """Start a new conversation with a default title."""
    conversation = Conversation(title="New Conversation")
    db.add(conversation)
    db.flush()

    logger.info("conversation_created", conversation_id=str(conversation.id))

    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
    }


@router.get("")
def list_conversations(
    cursor: str | None = Query(default=None, description="Cursor UUID for pagination"),
    limit: int = Query(default=20, ge=1, le=100, description="Max conversations to return"),
    search: str | None = Query(
        default=None, description="Filter by title (case-insensitive)"
    ),
    db: Session = Depends(get_db),
) -> dict:
    """List conversations with cursor-based pagination, sorted by updated_at descending."""
    if cursor is not None:
        cursor_uuid = _validate_uuid(cursor, "cursor")
        cursor_exists = db.execute(
            select(literal(1)).where(
                select(Conversation.id).where(Conversation.id == cursor_uuid).exists()
            )
        ).scalar()
        if not cursor_exists:
            raise AppError(
                code="INVALID_CURSOR",
                message=f"Cursor conversation not found: {cursor}",
                status_code=400,
            )
        # Use a subquery to get the cursor's updated_at for consistent DB-level comparison
        cursor_updated_at_subq = (
            select(Conversation.updated_at)
            .where(Conversation.id == cursor_uuid)
            .scalar_subquery()
        )
    else:
        cursor_uuid = None
        cursor_updated_at_subq = None

    # Build query: conversations sorted by updated_at DESC, id DESC (for tie-breaking)
    stmt = (
        select(Conversation)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    )

    # Apply search filter (case-insensitive title contains)
    if search is not None and search.strip():
        stmt = stmt.where(Conversation.title.ilike(f"%{search.strip()}%"))

    if cursor_updated_at_subq is not None:
        # Cursor-based pagination: get conversations that come after the cursor
        # in the sort order (updated_at DESC, id DESC)
        stmt = stmt.where(
            (Conversation.updated_at < cursor_updated_at_subq)
            | (
                (Conversation.updated_at == cursor_updated_at_subq)
                & (Conversation.id < cursor_uuid)
            )
        )

    # Fetch limit + 1 to determine if there's a next page
    stmt = stmt.limit(limit + 1)
    conversations = list(db.execute(stmt).scalars().all())

    has_next = len(conversations) > limit
    if has_next:
        conversations = conversations[:limit]

    # Build message counts in a single query
    conv_ids = [c.id for c in conversations]
    message_counts: dict[str, int] = {}
    if conv_ids:
        count_stmt = (
            select(Message.conversation_id, func.count(Message.id))
            .where(Message.conversation_id.in_(conv_ids))
            .group_by(Message.conversation_id)
        )
        for conv_id, count in db.execute(count_stmt).all():
            message_counts[str(conv_id)] = count

    next_cursor = str(conversations[-1].id) if has_next and conversations else None

    return {
        "conversations": [
            {
                "id": str(c.id),
                "title": c.title,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                "message_count": message_counts.get(str(c.id), 0),
            }
            for c in conversations
        ],
        "next_cursor": next_cursor,
    }


@router.get("/{conversation_id}")
def get_conversation(conversation_id: UUID, db: Session = Depends(get_db)) -> dict:
    """Get a conversation with its full message history in chronological order."""
    conversation = db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
    ).scalar_one_or_none()

    if conversation is None:
        raise AppError(
            code="NOT_FOUND",
            message=f"Conversation {conversation_id} not found",
            status_code=404,
        )

    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "metadata": None,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in conversation.messages
        ],
    }


class CreateMessageRequest(BaseModel):
    """Request body for creating a message in a conversation."""

    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1)


@router.post("/{conversation_id}/messages", status_code=201)
def create_message(
    conversation_id: UUID,
    body: CreateMessageRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Persist a single message (user or assistant) to a conversation."""
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise AppError(
            code="NOT_FOUND",
            message=f"Conversation {conversation_id} not found",
            status_code=404,
        )

    message = Message(conversation_id=conversation_id, role=body.role, content=body.content)
    db.add(message)
    db.flush()

    logger.info(
        "message_created",
        conversation_id=str(conversation_id),
        message_id=str(message.id),
        role=body.role,
    )

    return {
        "id": str(message.id),
        "role": message.role,
        "content": message.content,
        "metadata": None,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: UUID, db: Session = Depends(get_db)) -> Response:
    """Delete a conversation and all its messages (cascade)."""
    conversation = db.get(Conversation, conversation_id)

    if conversation is None:
        raise AppError(
            code="NOT_FOUND",
            message=f"Conversation {conversation_id} not found",
            status_code=404,
        )

    db.delete(conversation)
    db.flush()

    logger.info("conversation_deleted", conversation_id=str(conversation_id))

    return Response(status_code=204)


@router.patch("/{conversation_id}")
def update_conversation(
    conversation_id: UUID,
    body: UpdateConversationRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Update a conversation's title."""
    conversation = db.get(Conversation, conversation_id)

    if conversation is None:
        raise AppError(
            code="NOT_FOUND",
            message=f"Conversation {conversation_id} not found",
            status_code=404,
        )

    conversation.title = body.title
    db.flush()

    logger.info(
        "conversation_updated",
        conversation_id=str(conversation_id),
        title=body.title,
    )

    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
        "updated_at": conversation.updated_at.isoformat() if conversation.updated_at else None,
    }
