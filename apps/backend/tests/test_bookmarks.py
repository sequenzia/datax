"""Tests for the Bookmark CRUD API endpoints.

Covers:
- Integration: CRUD operations for all bookmark endpoints
- Edge cases: bookmarking non-existent message
- Error handling: 404 not found, 400 invalid UUID
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
from app.models.orm import Conversation, Message


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
        "DATAX_DUCKDB_PATH": ":memory:",
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


def _create_message(db: Session) -> tuple[str, str]:
    """Helper: create a conversation and message, return (conversation_id, message_id)."""
    conv = Conversation(title="Test Conversation")
    db.add(conv)
    db.flush()

    msg = Message(
        conversation_id=conv.id,
        role="assistant",
        content="Here are the sales results.",
        sql="SELECT * FROM sales",
        chart_config={"chart_type": "bar", "data": [], "layout": {}},
        query_result_summary={"columns": ["id", "amount"], "rows": [[1, 100]]},
        source_id="source-123",
        source_type="dataset",
    )
    db.add(msg)
    db.commit()
    return str(conv.id), str(msg.id)


# ---------------------------------------------------------------------------
# Integration: Create Bookmark
# ---------------------------------------------------------------------------


class TestCreateBookmark:
    """Test POST /api/v1/bookmarks."""

    @pytest.mark.asyncio
    async def test_create_returns_201(self, client, db) -> None:
        """Creating a bookmark returns 201 status."""
        _, msg_id = _create_message(db)
        response = await client.post(
            "/api/v1/bookmarks",
            json={"message_id": msg_id, "title": "Sales Overview"},
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_returns_bookmark_with_fields(self, client, db) -> None:
        """Created bookmark contains all expected fields."""
        _, msg_id = _create_message(db)
        response = await client.post(
            "/api/v1/bookmarks",
            json={"message_id": msg_id, "title": "Sales Overview"},
        )
        body = response.json()
        assert body["title"] == "Sales Overview"
        assert body["message_id"] == msg_id
        assert body["sql"] == "SELECT * FROM sales"
        assert body["chart_config"] is not None
        assert body["result_snapshot"] is not None
        assert body["source_id"] == "source-123"
        assert body["source_type"] == "dataset"
        assert "id" in body
        assert "created_at" in body

    @pytest.mark.asyncio
    async def test_create_copies_sql_from_message(self, client, db) -> None:
        """Bookmark SQL is copied from the message."""
        _, msg_id = _create_message(db)
        response = await client.post(
            "/api/v1/bookmarks",
            json={"message_id": msg_id, "title": "Sales"},
        )
        assert response.json()["sql"] == "SELECT * FROM sales"

    @pytest.mark.asyncio
    async def test_create_copies_chart_config_from_message(self, client, db) -> None:
        """Bookmark chart_config is copied from the message."""
        _, msg_id = _create_message(db)
        response = await client.post(
            "/api/v1/bookmarks",
            json={"message_id": msg_id, "title": "Sales"},
        )
        assert response.json()["chart_config"]["chart_type"] == "bar"

    @pytest.mark.asyncio
    async def test_create_copies_result_snapshot_from_message(self, client, db) -> None:
        """Bookmark result_snapshot is copied from the message."""
        _, msg_id = _create_message(db)
        response = await client.post(
            "/api/v1/bookmarks",
            json={"message_id": msg_id, "title": "Sales"},
        )
        snapshot = response.json()["result_snapshot"]
        assert "columns" in snapshot
        assert "rows" in snapshot

    @pytest.mark.asyncio
    async def test_create_nonexistent_message_returns_404(self, client) -> None:
        """Bookmarking a non-existent message returns 404."""
        fake_msg_id = str(uuid.uuid4())
        response = await client.post(
            "/api/v1/bookmarks",
            json={"message_id": fake_msg_id, "title": "Test"},
        )
        assert response.status_code == 404
        body = response.json()
        assert "error" in body

    @pytest.mark.asyncio
    async def test_create_invalid_message_id_returns_400(self, client) -> None:
        """Invalid message_id format returns 400."""
        response = await client.post(
            "/api/v1/bookmarks",
            json={"message_id": "not-a-uuid", "title": "Test"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_empty_title_returns_422(self, client, db) -> None:
        """Empty title string is rejected."""
        _, msg_id = _create_message(db)
        response = await client.post(
            "/api/v1/bookmarks",
            json={"message_id": msg_id, "title": ""},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Integration: List Bookmarks
# ---------------------------------------------------------------------------


class TestListBookmarks:
    """Test GET /api/v1/bookmarks."""

    @pytest.mark.asyncio
    async def test_list_empty_returns_empty_array(self, client) -> None:
        """Listing bookmarks when none exist returns empty array."""
        response = await client.get("/api/v1/bookmarks")
        assert response.status_code == 200
        body = response.json()
        assert body["bookmarks"] == []

    @pytest.mark.asyncio
    async def test_list_returns_bookmarks(self, client, db) -> None:
        """Listing returns created bookmarks."""
        _, msg_id = _create_message(db)
        await client.post(
            "/api/v1/bookmarks",
            json={"message_id": msg_id, "title": "Bookmark 1"},
        )
        await client.post(
            "/api/v1/bookmarks",
            json={"message_id": msg_id, "title": "Bookmark 2"},
        )

        response = await client.get("/api/v1/bookmarks")
        body = response.json()
        assert len(body["bookmarks"]) == 2

    @pytest.mark.asyncio
    async def test_list_includes_all_fields(self, client, db) -> None:
        """Each bookmark in the list has required fields."""
        _, msg_id = _create_message(db)
        await client.post(
            "/api/v1/bookmarks",
            json={"message_id": msg_id, "title": "Test Bookmark"},
        )

        response = await client.get("/api/v1/bookmarks")
        body = response.json()
        bm = body["bookmarks"][0]
        assert "id" in bm
        assert "title" in bm
        assert "sql" in bm
        assert "chart_config" in bm
        assert "result_snapshot" in bm
        assert "source_id" in bm
        assert "source_type" in bm
        assert "created_at" in bm

    @pytest.mark.asyncio
    async def test_list_ordered_newest_first(self, client, db) -> None:
        """Bookmarks are ordered by creation date, newest first.

        SQLite server_default only has second-level precision, so we
        create bookmarks with explicit timestamps via the DB directly.
        """
        from datetime import UTC, datetime, timedelta

        from app.models.orm import Bookmark

        _, msg_id = _create_message(db)
        msg_uuid = uuid.UUID(msg_id)

        now = datetime.now(tz=UTC)

        b1 = Bookmark(
            message_id=msg_uuid,
            title="Older",
            sql="SELECT 1",
        )
        b1.created_at = now - timedelta(minutes=5)
        db.add(b1)

        b2 = Bookmark(
            message_id=msg_uuid,
            title="Newer",
            sql="SELECT 2",
        )
        b2.created_at = now
        db.add(b2)
        db.commit()

        response = await client.get("/api/v1/bookmarks")
        body = response.json()
        titles = [b["title"] for b in body["bookmarks"]]
        assert titles[0] == "Newer"
        assert titles[1] == "Older"


# ---------------------------------------------------------------------------
# Integration: Delete Bookmark
# ---------------------------------------------------------------------------


class TestDeleteBookmark:
    """Test DELETE /api/v1/bookmarks/{id}."""

    @pytest.mark.asyncio
    async def test_delete_returns_204(self, client, db) -> None:
        """Deleting a bookmark returns 204 No Content."""
        _, msg_id = _create_message(db)
        resp = await client.post(
            "/api/v1/bookmarks",
            json={"message_id": msg_id, "title": "To Delete"},
        )
        bm_id = resp.json()["id"]

        response = await client.delete(f"/api/v1/bookmarks/{bm_id}")
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_removes_bookmark(self, client, db) -> None:
        """Deleted bookmark is no longer in the list."""
        _, msg_id = _create_message(db)
        resp = await client.post(
            "/api/v1/bookmarks",
            json={"message_id": msg_id, "title": "To Delete"},
        )
        bm_id = resp.json()["id"]

        await client.delete(f"/api/v1/bookmarks/{bm_id}")

        # Verify it's gone from the list
        list_resp = await client.get("/api/v1/bookmarks")
        assert len(list_resp.json()["bookmarks"]) == 0

    @pytest.mark.asyncio
    async def test_delete_not_found_returns_404(self, client) -> None:
        """Deleting a non-existent bookmark returns 404."""
        fake_id = uuid.uuid4()
        response = await client.delete(f"/api/v1/bookmarks/{fake_id}")
        assert response.status_code == 404
        body = response.json()
        assert "error" in body

    @pytest.mark.asyncio
    async def test_delete_does_not_affect_other_bookmarks(self, client, db) -> None:
        """Deleting one bookmark does not affect others."""
        _, msg_id = _create_message(db)
        resp1 = await client.post(
            "/api/v1/bookmarks",
            json={"message_id": msg_id, "title": "Keep"},
        )
        resp2 = await client.post(
            "/api/v1/bookmarks",
            json={"message_id": msg_id, "title": "Delete"},
        )

        await client.delete(f"/api/v1/bookmarks/{resp2.json()['id']}")

        list_resp = await client.get("/api/v1/bookmarks")
        bookmarks = list_resp.json()["bookmarks"]
        assert len(bookmarks) == 1
        assert bookmarks[0]["title"] == "Keep"


# ---------------------------------------------------------------------------
# Integration: Get Single Bookmark
# ---------------------------------------------------------------------------


class TestGetBookmark:
    """Test GET /api/v1/bookmarks/{id}."""

    @pytest.mark.asyncio
    async def test_get_returns_bookmark(self, client, db) -> None:
        """Getting a bookmark by ID returns its details."""
        _, msg_id = _create_message(db)
        resp = await client.post(
            "/api/v1/bookmarks",
            json={"message_id": msg_id, "title": "Sales Chart"},
        )
        bm_id = resp.json()["id"]

        response = await client.get(f"/api/v1/bookmarks/{bm_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == bm_id
        assert body["title"] == "Sales Chart"

    @pytest.mark.asyncio
    async def test_get_not_found_returns_404(self, client) -> None:
        """Getting a non-existent bookmark returns 404."""
        fake_id = uuid.uuid4()
        response = await client.get(f"/api/v1/bookmarks/{fake_id}")
        assert response.status_code == 404
