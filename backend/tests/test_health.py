"""Tests for health, readiness, and graceful shutdown."""

import asyncio
import os
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app
from app.shutdown import ShutdownManager


def _test_settings() -> Settings:
    """Create test settings with required fields."""
    env = {
        "DATABASE_URL": "sqlite:///:memory:",
        "DATAX_ENCRYPTION_KEY": "test-encryption-key",
    }
    with patch.dict(os.environ, env, clear=True):
        return Settings()  # type: ignore[call-arg]


@pytest.fixture
def app():
    """Create a test FastAPI app instance."""
    return create_app(settings=_test_settings())


@pytest.fixture
async def client(app):
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ---------------------------------------------------------------------------
# Integration: Health endpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """Test the /health liveness probe."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client) -> None:
        """GET /health returns 200 with status ok."""
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_health_has_no_dependency_checks(self, client) -> None:
        """Liveness probe response contains only status, no dependency info."""
        response = await client.get("/health")
        body = response.json()
        assert "checks" not in body


# ---------------------------------------------------------------------------
# Integration: Ready endpoint
# ---------------------------------------------------------------------------


class TestReadyEndpoint:
    """Test the /ready readiness probe."""

    @pytest.mark.asyncio
    async def test_ready_returns_200_when_all_ok(self, client) -> None:
        """GET /ready returns 200 when PostgreSQL and DuckDB are available."""
        with (
            patch("app.api.health._check_postgresql", return_value="ok"),
            patch("app.api.health._check_duckdb", return_value="ok"),
        ):
            response = await client.get("/ready")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["checks"]["postgresql"] == "ok"
        assert body["checks"]["duckdb"] == "ok"

    @pytest.mark.asyncio
    async def test_ready_returns_503_when_postgresql_down(self, client) -> None:
        """GET /ready returns 503 with details when PostgreSQL is unreachable."""
        with (
            patch("app.api.health._check_postgresql", return_value="error: connection refused"),
            patch("app.api.health._check_duckdb", return_value="ok"),
        ):
            response = await client.get("/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "unavailable"
        assert "error" in body["checks"]["postgresql"]
        assert body["checks"]["duckdb"] == "ok"

    @pytest.mark.asyncio
    async def test_ready_returns_503_when_duckdb_unavailable(self, client) -> None:
        """GET /ready returns 503 when DuckDB is not available."""
        with (
            patch("app.api.health._check_postgresql", return_value="ok"),
            patch("app.api.health._check_duckdb", return_value="error: duckdb not initialized"),
        ):
            response = await client.get("/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "unavailable"
        assert body["checks"]["postgresql"] == "ok"
        assert "error" in body["checks"]["duckdb"]

    @pytest.mark.asyncio
    async def test_ready_returns_503_when_both_down(self, client) -> None:
        """GET /ready returns 503 when both PostgreSQL and DuckDB fail."""
        with (
            patch("app.api.health._check_postgresql", return_value="error: pg down"),
            patch("app.api.health._check_duckdb", return_value="error: duckdb down"),
        ):
            response = await client.get("/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "unavailable"
        assert "error" in body["checks"]["postgresql"]
        assert "error" in body["checks"]["duckdb"]

    @pytest.mark.asyncio
    async def test_ready_checks_postgresql_connectivity(self, client) -> None:
        """Ready endpoint actually invokes the PostgreSQL check function."""
        with (
            patch("app.api.health._check_postgresql", return_value="ok") as pg_mock,
            patch("app.api.health._check_duckdb", return_value="ok"),
        ):
            await client.get("/ready")

        pg_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_returns_200_even_when_postgres_down(self, client) -> None:
        """Liveness probe is independent of dependency status."""
        # Readiness is down ...
        with (
            patch("app.api.health._check_postgresql", return_value="error: connection refused"),
            patch("app.api.health._check_duckdb", return_value="ok"),
        ):
            ready_resp = await client.get("/ready")
            assert ready_resp.status_code == 503

        # ... but health is always 200.
        health_resp = await client.get("/health")
        assert health_resp.status_code == 200
        assert health_resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Unit: ShutdownManager
# ---------------------------------------------------------------------------


class TestShutdownManager:
    """Unit tests for the graceful shutdown manager."""

    @pytest.mark.asyncio
    async def test_initial_state(self) -> None:
        """Manager starts in non-shutdown state with zero active tasks."""
        mgr = ShutdownManager()
        assert not mgr.is_shutting_down
        assert mgr.active_count == 0

    @pytest.mark.asyncio
    async def test_track_and_untrack(self) -> None:
        """Tracking and un-tracking adjusts the active count."""
        mgr = ShutdownManager()
        token1 = await mgr.track("sse")
        assert mgr.active_count == 1
        token2 = await mgr.track("query")
        assert mgr.active_count == 2

        await mgr.untrack(token1)
        assert mgr.active_count == 1
        await mgr.untrack(token2)
        assert mgr.active_count == 0

    @pytest.mark.asyncio
    async def test_untrack_unknown_token_is_noop(self) -> None:
        """Un-tracking a token that was never tracked does not raise."""
        mgr = ShutdownManager()
        await mgr.untrack(999)
        assert mgr.active_count == 0

    @pytest.mark.asyncio
    async def test_shutdown_event_set(self) -> None:
        """Calling _handle_signal sets the shutdown event."""
        mgr = ShutdownManager()
        assert not mgr.is_shutting_down
        mgr._handle_signal(15)  # SIGTERM
        assert mgr.is_shutting_down

    @pytest.mark.asyncio
    async def test_wait_for_drain_no_active(self) -> None:
        """Drain completes immediately when there are no active tasks."""
        mgr = ShutdownManager(drain_timeout=1)
        await mgr.wait_for_drain()  # should return instantly

    @pytest.mark.asyncio
    async def test_wait_for_drain_with_active_tasks(self) -> None:
        """Drain waits for tracked tasks to finish."""
        mgr = ShutdownManager(drain_timeout=5)
        token = await mgr.track("sse")

        async def finish_task():
            await asyncio.sleep(0.3)
            await mgr.untrack(token)

        asyncio.create_task(finish_task())
        await mgr.wait_for_drain()
        assert mgr.active_count == 0

    @pytest.mark.asyncio
    async def test_wait_for_drain_timeout_enforced(self) -> None:
        """Drain does not block longer than the configured timeout."""
        mgr = ShutdownManager(drain_timeout=1)
        await mgr.track("sse")  # never untracked

        # Should return within ~1s + tolerance, not hang.
        await asyncio.wait_for(mgr.wait_for_drain(), timeout=3)
        assert mgr.active_count == 1  # task was NOT drained

    @pytest.mark.asyncio
    async def test_shutdown_manager_attached_to_app(self, app) -> None:
        """ShutdownManager is accessible on app.state after create_app."""
        assert hasattr(app.state, "shutdown_manager")
        assert isinstance(app.state.shutdown_manager, ShutdownManager)
