"""Tests for the conversation CRUD API endpoints.

Covers:
- Integration: CRUD operations for all endpoints
- Integration: Cursor-based pagination correctness
- Integration: Message count accuracy
- Integration: Delete cascade removes messages
- Edge cases: empty list, invalid cursor, invalid UUID
- Error handling: 404 not found, 400 invalid format
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.main import create_app
from app.models.base import Base
from app.models.orm import Message


@pytest.fixture
def db_path():
    """Create a temporary file for SQLite database."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d) / "test.db"


def _test_settings(db_path: Path) -> Settings:
    """Create test settings with required fields."""
    env = {
        "DATABASE_URL": f"sqlite:///{db_path}",
        "DATAX_ENCRYPTION_KEY": "test-encryption-key",
    }
    with patch.dict(os.environ, env, clear=True):
        return Settings()  # type: ignore[call-arg]


@pytest.fixture
def db_engine(db_path):
    """Create a SQLite engine backed by a temp file with foreign key support."""
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    """Create a sessionmaker bound to the test engine."""
    return sessionmaker(bind=db_engine, autocommit=False, autoflush=False)


@pytest.fixture
def app(db_path, db_engine, session_factory):
    """Create a FastAPI app with a test SQLite database."""
    application = create_app(settings=_test_settings(db_path))
    application.state.db_engine = db_engine
    application.state.session_factory = session_factory
    return application


@pytest.fixture
async def client(app):
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.fixture
def db(session_factory) -> Session:
    """Create a database session for test setup/teardown."""
    session = session_factory()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# Integration: Create Conversation
# ---------------------------------------------------------------------------


class TestCreateConversation:
    """Test POST /api/v1/conversations."""

    @pytest.mark.asyncio
    async def test_create_returns_201(self, client) -> None:
        """Creating a conversation returns 201 status."""
        response = await client.post("/api/v1/conversations")
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_returns_valid_uuid(self, client) -> None:
        """Created conversation has a valid UUID id."""
        response = await client.post("/api/v1/conversations")
        body = response.json()
        parsed = uuid.UUID(body["id"])
        assert str(parsed) == body["id"]

    @pytest.mark.asyncio
    async def test_create_returns_default_title(self, client) -> None:
        """Created conversation has default title 'New Conversation'."""
        response = await client.post("/api/v1/conversations")
        body = response.json()
        assert body["title"] == "New Conversation"

    @pytest.mark.asyncio
    async def test_create_returns_created_at(self, client) -> None:
        """Created conversation includes a created_at timestamp."""
        response = await client.post("/api/v1/conversations")
        body = response.json()
        assert "created_at" in body
        assert body["created_at"] is not None


# ---------------------------------------------------------------------------
# Integration: List Conversations
# ---------------------------------------------------------------------------


class TestListConversations:
    """Test GET /api/v1/conversations."""

    @pytest.mark.asyncio
    async def test_list_empty_returns_empty_array(self, client) -> None:
        """Listing conversations when none exist returns empty array."""
        response = await client.get("/api/v1/conversations")
        assert response.status_code == 200
        body = response.json()
        assert body["conversations"] == []
        assert body["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_list_returns_conversations(self, client) -> None:
        """Listing conversations returns created conversations."""
        # Create two conversations
        await client.post("/api/v1/conversations")
        await client.post("/api/v1/conversations")

        response = await client.get("/api/v1/conversations")
        body = response.json()
        assert len(body["conversations"]) == 2

    @pytest.mark.asyncio
    async def test_list_includes_message_count(self, client, db) -> None:
        """List includes accurate message count per conversation."""
        # Create a conversation
        resp = await client.post("/api/v1/conversations")
        conv_id = uuid.UUID(resp.json()["id"])

        # Add messages directly to the database
        for i in range(3):
            msg = Message(
                conversation_id=conv_id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"Message {i}",
            )
            db.add(msg)
        db.commit()

        response = await client.get("/api/v1/conversations")
        body = response.json()
        assert len(body["conversations"]) == 1
        assert body["conversations"][0]["message_count"] == 3

    @pytest.mark.asyncio
    async def test_list_sorted_by_updated_at_desc(self, client, db) -> None:
        """Conversations are sorted by updated_at descending (most recent first)."""
        from datetime import UTC, datetime, timedelta

        from app.models.orm import Conversation

        # Create conversations with explicit different timestamps to ensure ordering
        now = datetime.now(tz=UTC)
        conv_ids = []
        for i in range(3):
            conv = Conversation(title=f"Conv {i}")
            conv.created_at = now - timedelta(minutes=10 - i)
            conv.updated_at = now - timedelta(minutes=10 - i)
            db.add(conv)
            db.flush()
            conv_ids.append(str(conv.id))
        db.commit()

        response = await client.get("/api/v1/conversations")
        body = response.json()
        ids = [c["id"] for c in body["conversations"]]

        # Most recently updated should be first (conv_ids[2] has latest timestamp)
        assert ids[0] == conv_ids[2]
        assert ids[1] == conv_ids[1]
        assert ids[2] == conv_ids[0]

    @pytest.mark.asyncio
    async def test_list_conversation_fields(self, client) -> None:
        """Each conversation in the list has required fields."""
        await client.post("/api/v1/conversations")

        response = await client.get("/api/v1/conversations")
        body = response.json()
        conv = body["conversations"][0]
        assert "id" in conv
        assert "title" in conv
        assert "created_at" in conv
        assert "updated_at" in conv
        assert "message_count" in conv


# ---------------------------------------------------------------------------
# Integration: Cursor-based Pagination
# ---------------------------------------------------------------------------


class TestPagination:
    """Test cursor-based pagination for listing conversations."""

    @pytest.mark.asyncio
    async def test_pagination_with_limit(self, client) -> None:
        """Limiting results returns correct count with next_cursor."""
        # Create 5 conversations
        for _ in range(5):
            await client.post("/api/v1/conversations")

        response = await client.get("/api/v1/conversations?limit=3")
        body = response.json()
        assert len(body["conversations"]) == 3
        assert body["next_cursor"] is not None

    @pytest.mark.asyncio
    async def test_pagination_second_page(self, client) -> None:
        """Using cursor returns the next page of results."""
        # Create 5 conversations
        for _ in range(5):
            await client.post("/api/v1/conversations")

        # Get first page
        resp1 = await client.get("/api/v1/conversations?limit=3")
        body1 = resp1.json()
        cursor = body1["next_cursor"]

        # Get second page
        resp2 = await client.get(f"/api/v1/conversations?cursor={cursor}&limit=3")
        body2 = resp2.json()
        assert len(body2["conversations"]) == 2
        assert body2["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_pagination_no_overlap(self, client) -> None:
        """Pages do not overlap — all IDs are unique across pages."""
        for _ in range(5):
            await client.post("/api/v1/conversations")

        # Get first page
        resp1 = await client.get("/api/v1/conversations?limit=3")
        body1 = resp1.json()
        page1_ids = {c["id"] for c in body1["conversations"]}

        # Get second page
        resp2 = await client.get(
            f"/api/v1/conversations?cursor={body1['next_cursor']}&limit=3"
        )
        body2 = resp2.json()
        page2_ids = {c["id"] for c in body2["conversations"]}

        assert page1_ids.isdisjoint(page2_ids)
        assert len(page1_ids) + len(page2_ids) == 5

    @pytest.mark.asyncio
    async def test_next_cursor_null_on_last_page(self, client) -> None:
        """next_cursor is null when there are no more results."""
        # Create 2 conversations
        await client.post("/api/v1/conversations")
        await client.post("/api/v1/conversations")

        response = await client.get("/api/v1/conversations?limit=20")
        body = response.json()
        assert body["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_invalid_cursor_uuid_returns_400(self, client) -> None:
        """Invalid cursor UUID format returns 400."""
        response = await client.get("/api/v1/conversations?cursor=not-a-valid-uuid")
        assert response.status_code == 400
        body = response.json()
        assert "error" in body

    @pytest.mark.asyncio
    async def test_nonexistent_cursor_returns_400(self, client) -> None:
        """Cursor pointing to non-existent conversation returns 400."""
        fake_cursor = str(uuid.uuid4())
        response = await client.get(f"/api/v1/conversations?cursor={fake_cursor}")
        assert response.status_code == 400
        body = response.json()
        assert "error" in body


# ---------------------------------------------------------------------------
# Integration: Get Conversation with Messages
# ---------------------------------------------------------------------------


class TestGetConversation:
    """Test GET /api/v1/conversations/{id}."""

    @pytest.mark.asyncio
    async def test_get_returns_conversation(self, client) -> None:
        """Getting a conversation returns its details."""
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        response = await client.get(f"/api/v1/conversations/{conv_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == conv_id
        assert body["title"] == "New Conversation"
        assert "created_at" in body

    @pytest.mark.asyncio
    async def test_get_returns_empty_messages_initially(self, client) -> None:
        """Newly created conversation has empty messages array."""
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        response = await client.get(f"/api/v1/conversations/{conv_id}")
        body = response.json()
        assert body["messages"] == []

    @pytest.mark.asyncio
    async def test_get_returns_messages_chronologically(self, client, db) -> None:
        """Messages are returned in chronological order (oldest first)."""
        import time

        resp = await client.post("/api/v1/conversations")
        conv_id = uuid.UUID(resp.json()["id"])

        # Add messages with different timestamps
        for i in range(3):
            msg = Message(
                conversation_id=conv_id,
                role="user",
                content=f"Message {i}",
            )
            db.add(msg)
            db.flush()
            # Small delay to ensure different timestamps (SQLite has limited precision)
            time.sleep(0.01)
        db.commit()

        response = await client.get(f"/api/v1/conversations/{conv_id}")
        body = response.json()
        assert len(body["messages"]) == 3
        assert body["messages"][0]["content"] == "Message 0"
        assert body["messages"][1]["content"] == "Message 1"
        assert body["messages"][2]["content"] == "Message 2"

    @pytest.mark.asyncio
    async def test_get_message_fields(self, client, db) -> None:
        """Each message has required fields: id, role, content, metadata, created_at."""
        resp = await client.post("/api/v1/conversations")
        conv_id = uuid.UUID(resp.json()["id"])

        msg = Message(
            conversation_id=conv_id,
            role="user",
            content="Hello",
            metadata_={"key": "value"},
        )
        db.add(msg)
        db.commit()

        response = await client.get(f"/api/v1/conversations/{conv_id}")
        body = response.json()
        message = body["messages"][0]
        assert "id" in message
        assert message["role"] == "user"
        assert message["content"] == "Hello"
        assert message["metadata"] == {"key": "value"}
        assert "created_at" in message

    @pytest.mark.asyncio
    async def test_get_not_found_returns_404(self, client) -> None:
        """Getting a non-existent conversation returns 404."""
        fake_id = uuid.uuid4()
        response = await client.get(f"/api/v1/conversations/{fake_id}")
        assert response.status_code == 404
        body = response.json()
        assert "error" in body

    @pytest.mark.asyncio
    async def test_get_invalid_uuid_returns_422(self, client) -> None:
        """Getting with invalid UUID format returns 422."""
        response = await client.get("/api/v1/conversations/not-a-uuid")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Integration: Delete Conversation
# ---------------------------------------------------------------------------


class TestDeleteConversation:
    """Test DELETE /api/v1/conversations/{id}."""

    @pytest.mark.asyncio
    async def test_delete_returns_204(self, client) -> None:
        """Deleting a conversation returns 204 No Content."""
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        response = await client.delete(f"/api/v1/conversations/{conv_id}")
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_removes_conversation(self, client) -> None:
        """Deleted conversation is no longer accessible."""
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        await client.delete(f"/api/v1/conversations/{conv_id}")

        response = await client.get(f"/api/v1/conversations/{conv_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_cascades_to_messages(self, client, db) -> None:
        """Deleting a conversation removes all associated messages."""
        resp = await client.post("/api/v1/conversations")
        conv_id = uuid.UUID(resp.json()["id"])

        # Add messages
        for i in range(5):
            msg = Message(
                conversation_id=conv_id,
                role="user",
                content=f"Message {i}",
            )
            db.add(msg)
        db.commit()

        # Verify messages exist
        from sqlalchemy import select
        count_before = db.execute(
            select(Message).where(Message.conversation_id == conv_id)
        ).scalars().all()
        assert len(count_before) == 5

        # Delete the conversation
        await client.delete(f"/api/v1/conversations/{conv_id}")

        # Verify messages are gone
        db.expire_all()
        count_after = db.execute(
            select(Message).where(Message.conversation_id == conv_id)
        ).scalars().all()
        assert len(count_after) == 0

    @pytest.mark.asyncio
    async def test_delete_not_found_returns_404(self, client) -> None:
        """Deleting a non-existent conversation returns 404."""
        fake_id = uuid.uuid4()
        response = await client.delete(f"/api/v1/conversations/{fake_id}")
        assert response.status_code == 404
        body = response.json()
        assert "error" in body

    @pytest.mark.asyncio
    async def test_delete_does_not_affect_other_conversations(self, client) -> None:
        """Deleting one conversation does not affect others."""
        resp1 = await client.post("/api/v1/conversations")
        resp2 = await client.post("/api/v1/conversations")
        id1 = resp1.json()["id"]
        id2 = resp2.json()["id"]

        await client.delete(f"/api/v1/conversations/{id1}")

        # Second conversation should still exist
        response = await client.get(f"/api/v1/conversations/{id2}")
        assert response.status_code == 200

        # List should show only one conversation
        list_resp = await client.get("/api/v1/conversations")
        assert len(list_resp.json()["conversations"]) == 1


# ---------------------------------------------------------------------------
# Integration: Message Count Accuracy
# ---------------------------------------------------------------------------


class TestMessageCount:
    """Test message count accuracy in list response."""

    @pytest.mark.asyncio
    async def test_zero_messages_count(self, client) -> None:
        """New conversation shows 0 message count."""
        await client.post("/api/v1/conversations")

        response = await client.get("/api/v1/conversations")
        body = response.json()
        assert body["conversations"][0]["message_count"] == 0

    @pytest.mark.asyncio
    async def test_multiple_conversations_different_counts(self, client, db) -> None:
        """Different conversations show correct individual message counts."""
        resp1 = await client.post("/api/v1/conversations")
        resp2 = await client.post("/api/v1/conversations")
        id1 = uuid.UUID(resp1.json()["id"])
        id2 = uuid.UUID(resp2.json()["id"])

        # Add 2 messages to first, 5 to second
        for i in range(2):
            db.add(Message(conversation_id=id1, role="user", content=f"Msg {i}"))
        for i in range(5):
            db.add(Message(conversation_id=id2, role="user", content=f"Msg {i}"))
        db.commit()

        response = await client.get("/api/v1/conversations")
        body = response.json()
        counts = {c["id"]: c["message_count"] for c in body["conversations"]}
        assert counts[str(id1)] == 2
        assert counts[str(id2)] == 5


# ---------------------------------------------------------------------------
# Integration: Update Conversation Title
# ---------------------------------------------------------------------------


class TestUpdateConversation:
    """Test PATCH /api/v1/conversations/{id}."""

    @pytest.mark.asyncio
    async def test_update_title_returns_200(self, client) -> None:
        """Updating a conversation title returns 200."""
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        response = await client.patch(
            f"/api/v1/conversations/{conv_id}",
            json={"title": "Updated Title"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_title_persists(self, client) -> None:
        """Updated title is returned in subsequent get."""
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        await client.patch(
            f"/api/v1/conversations/{conv_id}",
            json={"title": "My Analysis"},
        )

        get_resp = await client.get(f"/api/v1/conversations/{conv_id}")
        assert get_resp.json()["title"] == "My Analysis"

    @pytest.mark.asyncio
    async def test_update_title_in_response(self, client) -> None:
        """Patch response contains updated title."""
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        response = await client.patch(
            f"/api/v1/conversations/{conv_id}",
            json={"title": "Revenue Q1"},
        )
        body = response.json()
        assert body["title"] == "Revenue Q1"
        assert body["id"] == conv_id
        assert "updated_at" in body

    @pytest.mark.asyncio
    async def test_update_not_found_returns_404(self, client) -> None:
        """Updating a non-existent conversation returns 404."""
        fake_id = uuid.uuid4()
        response = await client.patch(
            f"/api/v1/conversations/{fake_id}",
            json={"title": "Test"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_empty_title_returns_422(self, client) -> None:
        """Empty title string is rejected."""
        resp = await client.post("/api/v1/conversations")
        conv_id = resp.json()["id"]

        response = await client.patch(
            f"/api/v1/conversations/{conv_id}",
            json={"title": ""},
        )
        assert response.status_code == 422
