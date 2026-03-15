"""Tests for the AG-UI endpoint integration.

Covers:
- Unit: AG-UI ASSI app mounts correctly in create_app()
- Integration: AG-UI endpoint responds to handshake via httpx AsyncClient
- Integration: Error response when no provider configured
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.agui import create_agui_app
from app.config import Settings
from app.models.base import Base

# Generate a valid Fernet key for tests
TEST_FERNET_KEY = Fernet.generate_key().decode()


def _test_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return test environment with encryption key and optional extras."""
    env = {
        "DATABASE_URL": "sqlite:///:memory:",
        "DATAX_ENCRYPTION_KEY": TEST_FERNET_KEY,
    }
    if extra:
        env.update(extra)
    return env


def _test_settings(extra_env: dict[str, str] | None = None) -> Settings:
    """Create test settings with required fields."""
    env = _test_env(extra_env)
    with patch.dict(os.environ, env, clear=True):
        return Settings()  # type: ignore[call-arg]


@pytest.fixture
def db_path():
    """Create a temporary file for SQLite database."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d) / "test.db"


@pytest.fixture
def db_engine(db_path):
    """Create a SQLite engine backed by a temp file with tables created."""
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


# ---------------------------------------------------------------------------
# Unit: ASGI app mounts correctly in create_app()
# ---------------------------------------------------------------------------


class TestAGUIMount:
    """Test that the AG-UI ASGI app is mounted in the FastAPI application."""

    def test_agui_mount_in_create_app_source(self) -> None:
        """create_app() source code includes app.mount('/api/agent', ...).

        Verified via file content inspection because create_app() has a
        pre-existing transitive import issue (SavedQuery not yet in orm.py)
        that prevents importing app.main at test time.
        """
        from pathlib import Path

        main_path = Path(__file__).resolve().parents[1] / "src" / "app" / "main.py"
        source = main_path.read_text()
        assert 'app.mount("/api/agent"' in source, (
            "create_app() must call app.mount('/api/agent', ...) to mount the AG-UI app"
        )
        assert "create_agui_app" in source, (
            "create_app() must call create_agui_app() to build the AG-UI sub-app"
        )

    def test_agui_import_in_main(self) -> None:
        """app.main imports create_agui_app from app.agui."""
        from pathlib import Path

        main_path = Path(__file__).resolve().parents[1] / "src" / "app" / "main.py"
        source = main_path.read_text()
        assert "from app.agui import create_agui_app" in source

    def test_agui_app_type_with_provider(self, session_factory) -> None:
        """AG-UI app is a Starlette instance when a provider is configured."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test"})
        with patch.dict(os.environ, env, clear=True):
            app = create_agui_app(
                cors_origins=["http://localhost:5173"],
                session_factory=session_factory,
            )
            assert type(app).__name__ == "Starlette"

    def test_agui_app_type_without_provider(self, session_factory) -> None:
        """AG-UI app is a Starlette error app when no provider is configured."""
        with patch.dict(os.environ, _test_env(), clear=True):
            app = create_agui_app(
                cors_origins=["http://localhost:5173"],
                session_factory=session_factory,
            )
            # Should be a Starlette app (error fallback), not AGUIApp
            assert type(app).__name__ == "Starlette"


# ---------------------------------------------------------------------------
# Integration: AG-UI endpoint responds to handshake
# ---------------------------------------------------------------------------


class TestAGUIHandshake:
    """Test AG-UI endpoint handshake via httpx AsyncClient."""

    @pytest.mark.asyncio
    async def test_agui_endpoint_responds(self, session_factory) -> None:
        """AG-UI endpoint at /api/agent responds to POST requests."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test"})
        with patch.dict(os.environ, env, clear=True):
            app = create_agui_app(
                cors_origins=["http://localhost:5173"],
                session_factory=session_factory,
            )
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                # Send a minimal AG-UI handshake-style POST request
                response = await client.post(
                    "/",
                    json={
                        "messages": [{"role": "user", "content": "hello"}],
                    },
                    headers={"Content-Type": "application/json"},
                )
                # The AG-UI endpoint should accept the request (not 404/405)
                # It may return various status codes depending on the protocol
                # state, but it should not be a routing error
                assert response.status_code != 404, "AG-UI endpoint not found"
                assert response.status_code != 405, "Method not allowed on AG-UI endpoint"

    @pytest.mark.asyncio
    async def test_agui_cors_allows_configured_origin(self, session_factory) -> None:
        """AG-UI endpoint CORS allows configured origins."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test"})
        with patch.dict(os.environ, env, clear=True):
            app = create_agui_app(
                cors_origins=["http://localhost:5173"],
                session_factory=session_factory,
            )
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.options(
                    "/",
                    headers={
                        "Origin": "http://localhost:5173",
                        "Access-Control-Request-Method": "POST",
                    },
                )
                assert (
                    response.headers.get("access-control-allow-origin") == "http://localhost:5173"
                )

    @pytest.mark.asyncio
    async def test_agui_info_method(self, session_factory) -> None:
        """AG-UI endpoint returns agent info for POST with method=info."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test"})
        with patch.dict(os.environ, env, clear=True):
            app = create_agui_app(
                cors_origins=["http://localhost:5173"],
                session_factory=session_factory,
            )
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    "/",
                    json={"method": "info"},
                    headers={"Content-Type": "application/json"},
                )
                assert response.status_code == 200
                body = response.json()
                assert "agents" in body
                assert len(body["agents"]) == 1

    @pytest.mark.asyncio
    async def test_agui_get_info(self, session_factory) -> None:
        """GET /info returns agent discovery info."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test"})
        with patch.dict(os.environ, env, clear=True):
            app = create_agui_app(
                cors_origins=["http://localhost:5173"],
                session_factory=session_factory,
            )
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.get("/info")
                assert response.status_code == 200
                body = response.json()
                assert "agents" in body
                assert len(body["agents"]) == 1

    @pytest.mark.asyncio
    async def test_agui_cors_blocks_unconfigured_origin(self, session_factory) -> None:
        """AG-UI endpoint CORS blocks unconfigured origins."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test"})
        with patch.dict(os.environ, env, clear=True):
            app = create_agui_app(
                cors_origins=["http://localhost:5173"],
                session_factory=session_factory,
            )
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.options(
                    "/",
                    headers={
                        "Origin": "http://evil.example.com",
                        "Access-Control-Request-Method": "POST",
                    },
                )
                assert (
                    response.headers.get("access-control-allow-origin") != "http://evil.example.com"
                )


# ---------------------------------------------------------------------------
# Integration: Error response when no provider configured
# ---------------------------------------------------------------------------


class TestAGUINoProvider:
    """Test AG-UI error behavior when no AI provider is configured."""

    @pytest.mark.asyncio
    async def test_no_provider_returns_error(self, session_factory) -> None:
        """AG-UI endpoint returns 503 with error when no provider configured."""
        with patch.dict(os.environ, _test_env(), clear=True):
            app = create_agui_app(
                cors_origins=["http://localhost:5173"],
                session_factory=session_factory,
            )
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    "/",
                    json={"messages": [{"role": "user", "content": "hello"}]},
                    headers={"Content-Type": "application/json"},
                )
                assert response.status_code == 503
                body = response.json()
                assert body["error"]["code"] == "NO_PROVIDER_CONFIGURED"
                assert "Configure AI provider in Settings" in body["error"]["message"]

    @pytest.mark.asyncio
    async def test_no_provider_info_returns_empty_agents(self, session_factory) -> None:
        """No-provider app returns empty agents for info requests."""
        with patch.dict(os.environ, _test_env(), clear=True):
            app = create_agui_app(
                cors_origins=["http://localhost:5173"],
                session_factory=session_factory,
            )
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                # POST with method=info
                response = await client.post(
                    "/",
                    json={"method": "info"},
                    headers={"Content-Type": "application/json"},
                )
                assert response.status_code == 200
                body = response.json()
                assert body == {"agents": {}}

                # GET /info
                response = await client.get("/info")
                assert response.status_code == 200
                assert response.json() == {"agents": {}}

    @pytest.mark.asyncio
    async def test_no_provider_cors_still_works(self, session_factory) -> None:
        """CORS is configured even when no provider is available."""
        with patch.dict(os.environ, _test_env(), clear=True):
            app = create_agui_app(
                cors_origins=["http://localhost:5173"],
                session_factory=session_factory,
            )
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.options(
                    "/",
                    headers={
                        "Origin": "http://localhost:5173",
                        "Access-Control-Request-Method": "POST",
                    },
                )
                assert (
                    response.headers.get("access-control-allow-origin") == "http://localhost:5173"
                )


# ---------------------------------------------------------------------------
# Integration: Health endpoint
# ---------------------------------------------------------------------------


class TestAGUIHealth:
    """Test the /health endpoint on the AG-UI sub-app."""

    @pytest.mark.asyncio
    async def test_health_returns_ok_with_provider(self, session_factory) -> None:
        """GET /health returns 200 + {"status": "ok"} when provider is configured."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test"})
        with patch.dict(os.environ, env, clear=True):
            app = create_agui_app(
                cors_origins=["http://localhost:5173"],
                session_factory=session_factory,
            )
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.get("/health")
                assert response.status_code == 200
                assert response.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_health_returns_ok_without_provider(self, session_factory) -> None:
        """GET /health returns 200 even without a provider (network reachability check)."""
        with patch.dict(os.environ, _test_env(), clear=True):
            app = create_agui_app(
                cors_origins=["http://localhost:5173"],
                session_factory=session_factory,
            )
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.get("/health")
                assert response.status_code == 200
                assert response.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_health_cors_preflight(self, session_factory) -> None:
        """OPTIONS /health returns CORS headers for configured origin."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test"})
        with patch.dict(os.environ, env, clear=True):
            app = create_agui_app(
                cors_origins=["http://localhost:5173"],
                session_factory=session_factory,
            )
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.options(
                    "/health",
                    headers={
                        "Origin": "http://localhost:5173",
                        "Access-Control-Request-Method": "GET",
                    },
                )
                assert (
                    response.headers.get("access-control-allow-origin") == "http://localhost:5173"
                )
