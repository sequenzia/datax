"""Tests for the Dashboard CRUD API endpoints.

Covers:
- Integration: Dashboard and DashboardItem CRUD operations
- Edge cases: empty dashboard, pinning non-existent bookmark
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
from app.models.orm import Bookmark, Conversation, Message


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


def _create_bookmark(db: Session) -> tuple[str, str, str]:
    """Helper: create a conversation, message, and bookmark. Return IDs."""
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
    db.flush()

    bookmark = Bookmark(
        message_id=msg.id,
        title="Sales Overview",
        sql=msg.sql,
        chart_config=msg.chart_config,
        result_snapshot=msg.query_result_summary,
        source_id=msg.source_id,
        source_type=msg.source_type,
    )
    db.add(bookmark)
    db.commit()
    return str(conv.id), str(msg.id), str(bookmark.id)


# ---------------------------------------------------------------------------
# Integration: Dashboard CRUD
# ---------------------------------------------------------------------------


class TestCreateDashboard:
    """Test POST /api/v1/dashboards."""

    @pytest.mark.asyncio
    async def test_create_returns_201(self, client) -> None:
        """Creating a dashboard returns 201 status."""
        response = await client.post(
            "/api/v1/dashboards",
            json={"title": "My Dashboard"},
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_returns_dashboard_with_fields(self, client) -> None:
        """Created dashboard contains all expected fields."""
        response = await client.post(
            "/api/v1/dashboards",
            json={"title": "Sales Dashboard"},
        )
        body = response.json()
        assert body["title"] == "Sales Dashboard"
        assert "id" in body
        assert "items" in body
        assert body["items"] == []
        assert "created_at" in body
        assert "updated_at" in body

    @pytest.mark.asyncio
    async def test_create_empty_title_returns_422(self, client) -> None:
        """Empty title is rejected."""
        response = await client.post(
            "/api/v1/dashboards",
            json={"title": ""},
        )
        assert response.status_code == 422


class TestListDashboards:
    """Test GET /api/v1/dashboards."""

    @pytest.mark.asyncio
    async def test_list_empty_returns_empty_array(self, client) -> None:
        """Listing dashboards when none exist returns empty array."""
        response = await client.get("/api/v1/dashboards")
        assert response.status_code == 200
        body = response.json()
        assert body["dashboards"] == []

    @pytest.mark.asyncio
    async def test_list_returns_created_dashboards(self, client) -> None:
        """Listing returns created dashboards."""
        await client.post(
            "/api/v1/dashboards", json={"title": "Dashboard 1"}
        )
        await client.post(
            "/api/v1/dashboards", json={"title": "Dashboard 2"}
        )

        response = await client.get("/api/v1/dashboards")
        body = response.json()
        assert len(body["dashboards"]) == 2


class TestGetDashboard:
    """Test GET /api/v1/dashboards/{id}."""

    @pytest.mark.asyncio
    async def test_get_returns_dashboard(self, client) -> None:
        """Getting a dashboard by ID returns its details."""
        resp = await client.post(
            "/api/v1/dashboards", json={"title": "Test Dashboard"}
        )
        dash_id = resp.json()["id"]

        response = await client.get(f"/api/v1/dashboards/{dash_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == dash_id
        assert body["title"] == "Test Dashboard"

    @pytest.mark.asyncio
    async def test_get_not_found_returns_404(self, client) -> None:
        """Getting a non-existent dashboard returns 404."""
        fake_id = uuid.uuid4()
        response = await client.get(f"/api/v1/dashboards/{fake_id}")
        assert response.status_code == 404


class TestUpdateDashboard:
    """Test PUT /api/v1/dashboards/{id}."""

    @pytest.mark.asyncio
    async def test_update_title(self, client) -> None:
        """Updating a dashboard title works."""
        resp = await client.post(
            "/api/v1/dashboards", json={"title": "Old Title"}
        )
        dash_id = resp.json()["id"]

        response = await client.put(
            f"/api/v1/dashboards/{dash_id}",
            json={"title": "New Title"},
        )
        assert response.status_code == 200
        assert response.json()["title"] == "New Title"

    @pytest.mark.asyncio
    async def test_update_not_found_returns_404(self, client) -> None:
        """Updating a non-existent dashboard returns 404."""
        fake_id = uuid.uuid4()
        response = await client.put(
            f"/api/v1/dashboards/{fake_id}",
            json={"title": "New Title"},
        )
        assert response.status_code == 404


class TestDeleteDashboard:
    """Test DELETE /api/v1/dashboards/{id}."""

    @pytest.mark.asyncio
    async def test_delete_returns_204(self, client) -> None:
        """Deleting a dashboard returns 204 No Content."""
        resp = await client.post(
            "/api/v1/dashboards", json={"title": "To Delete"}
        )
        dash_id = resp.json()["id"]

        response = await client.delete(f"/api/v1/dashboards/{dash_id}")
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_removes_dashboard(self, client) -> None:
        """Deleted dashboard is no longer in the list."""
        resp = await client.post(
            "/api/v1/dashboards", json={"title": "To Delete"}
        )
        dash_id = resp.json()["id"]

        await client.delete(f"/api/v1/dashboards/{dash_id}")

        list_resp = await client.get("/api/v1/dashboards")
        assert len(list_resp.json()["dashboards"]) == 0

    @pytest.mark.asyncio
    async def test_delete_not_found_returns_404(self, client) -> None:
        """Deleting a non-existent dashboard returns 404."""
        fake_id = uuid.uuid4()
        response = await client.delete(f"/api/v1/dashboards/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_cascade_removes_items(self, client, db) -> None:
        """Deleting a dashboard also removes its items."""
        _, _, bm_id = _create_bookmark(db)

        # Create dashboard + add item
        resp = await client.post(
            "/api/v1/dashboards", json={"title": "With Items"}
        )
        dash_id = resp.json()["id"]
        await client.post(
            f"/api/v1/dashboards/{dash_id}/items",
            json={"bookmark_id": bm_id, "position": 0},
        )

        # Delete dashboard
        await client.delete(f"/api/v1/dashboards/{dash_id}")

        # Dashboard gone
        get_resp = await client.get(f"/api/v1/dashboards/{dash_id}")
        assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# Integration: Dashboard Items (Pin/Unpin)
# ---------------------------------------------------------------------------


class TestAddDashboardItem:
    """Test POST /api/v1/dashboards/{id}/items."""

    @pytest.mark.asyncio
    async def test_add_item_returns_201(self, client, db) -> None:
        """Pinning a bookmark returns 201."""
        _, _, bm_id = _create_bookmark(db)
        resp = await client.post(
            "/api/v1/dashboards", json={"title": "My Dashboard"}
        )
        dash_id = resp.json()["id"]

        response = await client.post(
            f"/api/v1/dashboards/{dash_id}/items",
            json={"bookmark_id": bm_id, "position": 0},
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_add_item_returns_item_with_bookmark(self, client, db) -> None:
        """Pinned item includes bookmark details."""
        _, _, bm_id = _create_bookmark(db)
        resp = await client.post(
            "/api/v1/dashboards", json={"title": "My Dashboard"}
        )
        dash_id = resp.json()["id"]

        response = await client.post(
            f"/api/v1/dashboards/{dash_id}/items",
            json={"bookmark_id": bm_id, "position": 0},
        )
        body = response.json()
        assert body["bookmark_id"] == bm_id
        assert body["dashboard_id"] == dash_id
        assert body["position"] == 0
        assert body["bookmark"] is not None
        assert body["bookmark"]["title"] == "Sales Overview"
        assert body["bookmark"]["sql"] == "SELECT * FROM sales"

    @pytest.mark.asyncio
    async def test_add_item_with_position(self, client, db) -> None:
        """Item is created with the specified position."""
        _, _, bm_id = _create_bookmark(db)
        resp = await client.post(
            "/api/v1/dashboards", json={"title": "Dashboard"}
        )
        dash_id = resp.json()["id"]

        response = await client.post(
            f"/api/v1/dashboards/{dash_id}/items",
            json={"bookmark_id": bm_id, "position": 5},
        )
        assert response.json()["position"] == 5

    @pytest.mark.asyncio
    async def test_add_item_nonexistent_dashboard_returns_404(self, client, db) -> None:
        """Pinning to a non-existent dashboard returns 404."""
        _, _, bm_id = _create_bookmark(db)
        fake_id = uuid.uuid4()
        response = await client.post(
            f"/api/v1/dashboards/{fake_id}/items",
            json={"bookmark_id": bm_id, "position": 0},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_add_item_nonexistent_bookmark_returns_404(self, client) -> None:
        """Pinning a non-existent bookmark returns 404."""
        resp = await client.post(
            "/api/v1/dashboards", json={"title": "Dashboard"}
        )
        dash_id = resp.json()["id"]
        fake_bm_id = str(uuid.uuid4())

        response = await client.post(
            f"/api/v1/dashboards/{dash_id}/items",
            json={"bookmark_id": fake_bm_id, "position": 0},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_add_item_invalid_bookmark_id_returns_400(self, client) -> None:
        """Invalid bookmark_id format returns 400."""
        resp = await client.post(
            "/api/v1/dashboards", json={"title": "Dashboard"}
        )
        dash_id = resp.json()["id"]

        response = await client.post(
            f"/api/v1/dashboards/{dash_id}/items",
            json={"bookmark_id": "not-a-uuid", "position": 0},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_items_appear_in_dashboard_get(self, client, db) -> None:
        """Pinned items appear when getting the dashboard."""
        _, _, bm_id = _create_bookmark(db)
        resp = await client.post(
            "/api/v1/dashboards", json={"title": "Dashboard"}
        )
        dash_id = resp.json()["id"]

        await client.post(
            f"/api/v1/dashboards/{dash_id}/items",
            json={"bookmark_id": bm_id, "position": 0},
        )

        get_resp = await client.get(f"/api/v1/dashboards/{dash_id}")
        body = get_resp.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["bookmark"]["title"] == "Sales Overview"


class TestRemoveDashboardItem:
    """Test DELETE /api/v1/dashboards/{id}/items/{item_id}."""

    @pytest.mark.asyncio
    async def test_remove_item_returns_204(self, client, db) -> None:
        """Removing an item returns 204."""
        _, _, bm_id = _create_bookmark(db)
        resp = await client.post(
            "/api/v1/dashboards", json={"title": "Dashboard"}
        )
        dash_id = resp.json()["id"]

        item_resp = await client.post(
            f"/api/v1/dashboards/{dash_id}/items",
            json={"bookmark_id": bm_id, "position": 0},
        )
        item_id = item_resp.json()["id"]

        response = await client.delete(
            f"/api/v1/dashboards/{dash_id}/items/{item_id}"
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_remove_does_not_delete_bookmark(self, client, db) -> None:
        """Removing item from dashboard does not delete the underlying bookmark."""
        _, _, bm_id = _create_bookmark(db)
        resp = await client.post(
            "/api/v1/dashboards", json={"title": "Dashboard"}
        )
        dash_id = resp.json()["id"]

        item_resp = await client.post(
            f"/api/v1/dashboards/{dash_id}/items",
            json={"bookmark_id": bm_id, "position": 0},
        )
        item_id = item_resp.json()["id"]

        await client.delete(f"/api/v1/dashboards/{dash_id}/items/{item_id}")

        # Bookmark still exists
        bm_resp = await client.get(f"/api/v1/bookmarks/{bm_id}")
        assert bm_resp.status_code == 200
        assert bm_resp.json()["title"] == "Sales Overview"

    @pytest.mark.asyncio
    async def test_remove_item_not_found_returns_404(self, client) -> None:
        """Removing a non-existent item returns 404."""
        resp = await client.post(
            "/api/v1/dashboards", json={"title": "Dashboard"}
        )
        dash_id = resp.json()["id"]
        fake_item_id = uuid.uuid4()

        response = await client.delete(
            f"/api/v1/dashboards/{dash_id}/items/{fake_item_id}"
        )
        assert response.status_code == 404
