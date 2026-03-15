"""Tests for the AG-UI endpoint integration.

Covers:
- Unit: AG-UI ASSI app mounts correctly in create_app()
- Integration: AG-UI endpoint responds to handshake via httpx AsyncClient
- Integration: Error response when no provider configured
- Integration: CopilotKit envelope unwrapping (422 fix)
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from starlette.responses import Response

from app.agui import _ensure_run_defaults, _unwrap_envelope, create_agui_app
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


# ---------------------------------------------------------------------------
# CopilotKit envelope unwrapping (422 fix)
# ---------------------------------------------------------------------------

# Minimal AG-UI envelope payload matching CopilotKit v1.54+ format.
_ENVELOPE_PAYLOAD: dict[str, Any] = {
    "method": "agent/connect",
    "params": {"agentId": "datax-analytics"},
    "body": {
        "threadId": "t-1",
        "runId": "r-1",
        "state": {},
        "messages": [{"id": "m1", "role": "user", "content": "hi"}],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    },
}

# Flat format — fields at the top level (no envelope).
_FLAT_PAYLOAD: dict[str, Any] = {
    "threadId": "t-1",
    "runId": "r-1",
    "state": {},
    "messages": [{"id": "m1", "role": "user", "content": "hi"}],
    "tools": [],
    "context": [],
    "forwardedProps": {},
}


class TestAGUIEnvelopeUnwrap:
    """Tests for CopilotKit envelope unwrapping logic."""

    # -- Unit tests for _unwrap_envelope ---------------------------------

    def test_unwrap_envelope_unit(self) -> None:
        """_unwrap_envelope extracts inner body and patches request._json."""

        class FakeRequest:
            _json: dict[str, Any] | None = None

        req = FakeRequest()
        result = _unwrap_envelope(dict(_ENVELOPE_PAYLOAD), req)  # type: ignore[arg-type]
        assert result["threadId"] == "t-1"
        assert req._json is result

    def test_unwrap_flat_passthrough(self) -> None:
        """_unwrap_envelope returns flat body unchanged."""

        class FakeRequest:
            _json: dict[str, Any] | None = None

        req = FakeRequest()
        original = dict(_FLAT_PAYLOAD)
        result = _unwrap_envelope(original, req)  # type: ignore[arg-type]
        assert result is original
        assert req._json is None  # untouched

    # -- Integration tests -----------------------------------------------

    @pytest.mark.asyncio
    async def test_envelope_format_not_422(self, session_factory) -> None:
        """Envelope-wrapped payload does NOT return 422.

        Mocks handle_ag_ui_request so we only test the unwrap layer,
        not the full agent pipeline (which needs a real API key).
        """
        from unittest.mock import AsyncMock

        mock_response = Response(status_code=200, content=b"ok")

        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test"})
        with (
            patch.dict(os.environ, env, clear=True),
            patch("app.agui.handle_ag_ui_request", new_callable=AsyncMock) as mock_handler,
        ):
            mock_handler.return_value = mock_response
            app = create_agui_app(
                cors_origins=["http://localhost:5173"],
                session_factory=session_factory,
            )
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    "/",
                    json=_ENVELOPE_PAYLOAD,
                    headers={"Content-Type": "application/json"},
                )
                assert response.status_code == 200
                # Verify handle_ag_ui_request was called (not short-circuited by 422)
                mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_flat_format_still_works(self, session_factory) -> None:
        """Flat (non-envelope) payload still works — regression guard."""
        from unittest.mock import AsyncMock

        mock_response = Response(status_code=200, content=b"ok")

        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test"})
        with (
            patch.dict(os.environ, env, clear=True),
            patch("app.agui.handle_ag_ui_request", new_callable=AsyncMock) as mock_handler,
        ):
            mock_handler.return_value = mock_response
            app = create_agui_app(
                cors_origins=["http://localhost:5173"],
                session_factory=session_factory,
            )
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    "/",
                    json=_FLAT_PAYLOAD,
                    headers={"Content-Type": "application/json"},
                )
                assert response.status_code == 200
                mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_info_in_envelope_still_works(self, session_factory) -> None:
        """Info method in envelope format returns 200 with agents."""
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
                    json={"method": "info", "params": {"agentId": "datax-analytics"}},
                    headers={"Content-Type": "application/json"},
                )
                assert response.status_code == 200
                body = response.json()
                assert "agents" in body


# ---------------------------------------------------------------------------
# Tool schema validity (stream crash prevention)
# ---------------------------------------------------------------------------


class TestToolSchemaValidity:
    """Ensure tool parameter schemas are valid for LLM function calling APIs.

    OpenAI (and compatible providers) require every JSON Schema element to have
    an explicit ``type`` key. Using ``Any`` in tool parameter annotations
    generates ``{"items": {}}`` which is rejected mid-stream, crashing the
    SSE connection.
    """

    def test_no_empty_schema_in_tool_params(self) -> None:
        """No tool generates an empty {} schema node (missing 'type' key).

        Walks every tool's parameter JSON schema tree and asserts there are
        no empty ``{}`` dicts, which would cause OpenAI to reject the tool
        definition with: "schema must have a 'type' key".
        """
        from pydantic_ai import Agent

        from app.services.agent_tools import AgentDeps, register_tools

        agent: Agent[AgentDeps, str] = Agent(
            "test",
            deps_type=AgentDeps,
        )
        register_tools(agent)

        def _find_empty_schemas(obj: Any, path: str = "") -> list[str]:
            """Walk a JSON schema tree and collect paths to empty {} nodes."""
            found: list[str] = []
            if isinstance(obj, dict):
                if obj == {}:
                    found.append(path or "(root)")
                else:
                    for k, v in obj.items():
                        found.extend(_find_empty_schemas(v, f"{path}.{k}"))
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    found.extend(_find_empty_schemas(item, f"{path}[{i}]"))
            return found

        tools = agent._function_toolset.tools
        assert len(tools) > 0, "Expected at least one tool to be registered"

        for name, tool in tools.items():
            schema = tool.function_schema.json_schema
            issues = _find_empty_schemas(schema)
            assert not issues, (
                f"Tool '{name}' has empty {{}} schema (no 'type' key) at: "
                f"{', '.join(issues)}. "
                f"Replace Any with explicit types (e.g., str | int | float | bool | None)."
            )


class TestAGUIEnvelopeNoProvider:
    """Test CopilotKit envelope with no provider configured."""

    @pytest.mark.asyncio
    async def test_no_provider_envelope_returns_503(self, session_factory) -> None:
        """No-provider path returns 503 (not 422) for envelope format."""
        with patch.dict(os.environ, _test_env(), clear=True):
            app = create_agui_app(
                cors_origins=["http://localhost:5173"],
                session_factory=session_factory,
            )
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    "/",
                    json=_ENVELOPE_PAYLOAD,
                    headers={"Content-Type": "application/json"},
                )
                assert response.status_code == 503
                body = response.json()
                assert body["error"]["code"] == "NO_PROVIDER_CONFIGURED"


# ---------------------------------------------------------------------------
# RunAgentInput defaults injection (422 fix for CopilotKit v1.54 + pydantic-ai 0.8.1)
# ---------------------------------------------------------------------------

# Payload missing the four required RunAgentInput fields.
_PAYLOAD_MISSING_DEFAULTS: dict[str, Any] = {
    "threadId": "t-1",
    "runId": "r-1",
    "messages": [{"id": "m1", "role": "user", "content": "hi"}],
}

# Envelope wrapping a body that also lacks the four fields.
_ENVELOPE_MISSING_DEFAULTS: dict[str, Any] = {
    "method": "agent/connect",
    "params": {"agentId": "datax-analytics"},
    "body": {
        "threadId": "t-1",
        "runId": "r-1",
        "messages": [{"id": "m1", "role": "user", "content": "hi"}],
    },
}


class TestAGUIRunDefaults:
    """Tests for _ensure_run_defaults injection logic."""

    # -- Unit tests ----------------------------------------------------------

    def test_injects_missing_fields(self) -> None:
        """_ensure_run_defaults adds missing required fields."""

        class FakeRequest:
            _json: dict[str, Any] | None = None

        req = FakeRequest()
        body: dict[str, Any] = {"threadId": "t-1", "runId": "r-1", "messages": []}
        result = _ensure_run_defaults(body, req)  # type: ignore[arg-type]
        assert result["state"] == {}
        assert result["tools"] == []
        assert result["context"] == []
        assert result["forwardedProps"] == {}
        # Should have patched request._json since fields were added
        assert req._json is result

    def test_preserves_existing_values(self) -> None:
        """_ensure_run_defaults does NOT overwrite existing values."""

        class FakeRequest:
            _json: dict[str, Any] | None = None

        req = FakeRequest()
        existing_state = {"counter": 42}
        existing_tools = [{"name": "my_tool"}]
        body: dict[str, Any] = {
            "threadId": "t-1",
            "runId": "r-1",
            "messages": [],
            "state": existing_state,
            "tools": existing_tools,
            "context": [],
            "forwardedProps": {},
        }
        result = _ensure_run_defaults(body, req)  # type: ignore[arg-type]
        assert result["state"] is existing_state
        assert result["tools"] is existing_tools
        # No fields were added, so request._json should be untouched
        assert req._json is None

    # -- Integration tests ---------------------------------------------------

    @pytest.mark.asyncio
    async def test_missing_defaults_returns_200(self, session_factory) -> None:
        """Flat payload missing the four fields returns 200, not 422."""
        from unittest.mock import AsyncMock

        mock_response = Response(status_code=200, content=b"ok")

        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test"})
        with (
            patch.dict(os.environ, env, clear=True),
            patch("app.agui.handle_ag_ui_request", new_callable=AsyncMock) as mock_handler,
        ):
            mock_handler.return_value = mock_response
            app = create_agui_app(
                cors_origins=["http://localhost:5173"],
                session_factory=session_factory,
            )
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    "/",
                    json=_PAYLOAD_MISSING_DEFAULTS,
                    headers={"Content-Type": "application/json"},
                )
                assert response.status_code == 200
                mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_envelope_missing_defaults_returns_200(self, session_factory) -> None:
        """Envelope payload with inner body missing fields returns 200, not 422."""
        from unittest.mock import AsyncMock

        mock_response = Response(status_code=200, content=b"ok")

        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test"})
        with (
            patch.dict(os.environ, env, clear=True),
            patch("app.agui.handle_ag_ui_request", new_callable=AsyncMock) as mock_handler,
        ):
            mock_handler.return_value = mock_response
            app = create_agui_app(
                cors_origins=["http://localhost:5173"],
                session_factory=session_factory,
            )
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    "/",
                    json=_ENVELOPE_MISSING_DEFAULTS,
                    headers={"Content-Type": "application/json"},
                )
                assert response.status_code == 200
                mock_handler.assert_called_once()
