"""AG-UI endpoint setup for the Pydantic AI agent.

Creates an ASGI application that handles AG-UI protocol requests by running
the Pydantic AI agent. The app is mounted at ``/api/agent`` inside the
FastAPI application so that CopilotKit can communicate with the agent.

CORS middleware is applied directly to the AG-UI sub-application because
FastAPI's CORS middleware does not propagate to mounted sub-apps.

The agent is configured with all 9 tools (run_query, get_schema, etc.)
and receives service references (DuckDB, QueryService) via AgentDeps.
"""

from __future__ import annotations

from typing import Any

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from app.logging import get_logger
from app.services.agent_service import (
    AgentDeps,
    NoProviderConfiguredError,
    create_agent,
)

logger = get_logger(__name__)


def _build_cors_middleware(cors_origins: list[str]) -> Middleware:
    """Build a CORS middleware instance matching the main app's policy."""
    return Middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


async def _no_provider_error_handler(request: Request, exc: Exception) -> Response:
    """Return an error response when no AI provider is configured."""
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "NO_PROVIDER_CONFIGURED",
                "message": "Configure AI provider in Settings",
            }
        },
    )


def create_agui_app(
    cors_origins: list[str],
    *,
    duckdb_manager: Any | None = None,
    connection_manager: Any | None = None,
    query_service: Any | None = None,
    session_factory: Any | None = None,
    max_query_timeout: int = 30,
    max_retries: int = 3,
) -> Starlette:
    """Create the AG-UI ASGI application.

    Uses the existing ``create_agent()`` factory to build a Pydantic AI agent
    with the user's configured provider, then calls ``agent.to_ag_ui()`` to
    produce an ASGI app.

    If no AI provider is configured, a fallback Starlette app is returned
    that responds with a 503 error and a message to configure a provider.

    Args:
        cors_origins: List of allowed CORS origins (same as the main app).
        duckdb_manager: DuckDB manager instance for dataset queries.
        connection_manager: Connection manager for external DB queries.
        query_service: QueryService instance for SQL execution routing.
        session_factory: SQLAlchemy session factory for DB operations.
        max_query_timeout: Maximum query timeout in seconds.
        max_retries: Maximum retry attempts for self-correction.

    Returns:
        An ASGI application ready to be mounted in FastAPI.
    """
    cors_middleware = _build_cors_middleware(cors_origins)

    try:
        agent = create_agent(session_factory=session_factory)
    except NoProviderConfiguredError:
        logger.warning(
            "agui_no_provider",
            message="No AI provider configured; AG-UI endpoint will return errors",
        )

        async def _error_endpoint(request: Request) -> Response:
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "NO_PROVIDER_CONFIGURED",
                        "message": "Configure AI provider in Settings",
                    }
                },
            )

        return Starlette(
            routes=[Route("/{path:path}", _error_endpoint, methods=["GET", "POST", "OPTIONS"])],
            middleware=[cors_middleware],
        )

    # Build AgentDeps with service references so tools can access data sources
    deps = AgentDeps(
        duckdb_manager=duckdb_manager,
        connection_manager=connection_manager,
        query_service=query_service,
        session_factory=session_factory,
        max_query_timeout=max_query_timeout,
        max_retries=max_retries,
    )

    agui_app = agent.to_ag_ui(
        deps=deps,
        middleware=[cors_middleware],
        exception_handlers={
            NoProviderConfiguredError: _no_provider_error_handler,
        },
    )

    logger.info("agui_app_created", agent_name=agent.name, tools_registered=9)
    return agui_app
