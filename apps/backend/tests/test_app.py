import os
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


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


class TestAppStartup:
    """Test FastAPI application startup and configuration."""

    def test_app_creates_successfully(self, app) -> None:
        """FastAPI app can be created with valid settings."""
        assert app.title == "DataX"
        assert app.version == "0.1.0"

    def test_app_has_v1_router(self, app) -> None:
        """API v1 router is included in the app."""
        route_paths = [route.path for route in app.routes]
        assert "/api/v1/health" in route_paths


class TestHealthEndpoint:
    """Test the health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client) -> None:
        """GET /api/v1/health returns 200 with status ok."""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestOpenAPIDocs:
    """Test OpenAPI documentation serving."""

    @pytest.mark.asyncio
    async def test_docs_page_serves(self, client) -> None:
        """/docs serves the Swagger UI page."""
        response = await client.get("/docs")
        assert response.status_code == 200
        assert "swagger-ui" in response.text.lower()

    @pytest.mark.asyncio
    async def test_openapi_json_serves(self, client) -> None:
        """/openapi.json serves the OpenAPI schema."""
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert data["info"]["title"] == "DataX"
        assert data["info"]["version"] == "0.1.0"


class TestErrorHandling:
    """Test global exception handlers."""

    @pytest.mark.asyncio
    async def test_404_returns_structured_error(self, client) -> None:
        """Non-existent routes return structured JSON error."""
        response = await client.get("/api/v1/nonexistent")
        assert response.status_code == 404
        body = response.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]

    @pytest.mark.asyncio
    async def test_error_response_format(self, client) -> None:
        """Error responses follow the { error: { code, message } } format."""
        response = await client.get("/api/v1/nonexistent")
        body = response.json()
        assert body["error"]["code"] == "HTTP_ERROR"
        assert body["error"]["message"] == "Not Found"


class TestCORS:
    """Test CORS configuration."""

    @pytest.mark.asyncio
    async def test_cors_allows_configured_origin(self, client) -> None:
        """CORS headers are set for the configured frontend origin."""
        response = await client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"

    @pytest.mark.asyncio
    async def test_cors_blocks_unconfigured_origin(self, client) -> None:
        """CORS does not allow origins not in the configuration."""
        response = await client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.headers.get("access-control-allow-origin") != "http://evil.example.com"
