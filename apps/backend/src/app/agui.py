"""AG-UI endpoint setup for the Pydantic AI agent.

Creates an ASGI application that handles AG-UI protocol requests by running
the Pydantic AI agent. The app is mounted at ``/api/agent`` inside the
FastAPI application so that CopilotKit can communicate with the agent.

CORS middleware is applied directly to the AG-UI sub-application because
FastAPI's CORS middleware does not propagate to mounted sub-apps.

CopilotKit v1.54+ sends ``{"method": "info"}`` to discover available agents
before starting a conversation. The pydantic-ai AG-UI adapter doesn't handle
this, so we intercept it before delegating to ``handle_ag_ui_request``.

CopilotKit v1.54+ also wraps AG-UI payloads in a nested envelope format::

    {"method": "agent/connect", "params": {...}, "body": {threadId, runId, ...}}

The ``_unwrap_envelope`` helper detects this format and replaces the cached
request JSON so that pydantic-ai sees the flat ``RunAgentInput`` fields.

The agent is configured with all 9 tools (run_query, get_schema, etc.)
and receives service references (DuckDB, QueryService) via AgentDeps.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai.ag_ui import handle_ag_ui_request
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


def _unwrap_envelope(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """Unwrap CopilotKit v1.54+ AG-UI envelope if detected.

    CopilotKit wraps payloads as ``{method, params, body: {threadId, ...}}``.
    ``RunAgentInput`` fields live inside ``body``.  When detected, replace the
    cached request JSON so pydantic-ai sees the flat format it expects.
    """
    if (
        "body" in body
        and isinstance(body["body"], dict)
        and "threadId" not in body
        and "thread_id" not in body
    ):
        inner = body["body"]
        request._json = inner  # type: ignore[attr-defined]
        logger.debug(
            "agui_envelope_unwrapped",
            method=body.get("method"),
            thread_id=inner.get("threadId"),
        )
        return inner
    return body


def _build_cors_middleware(cors_origins: list[str]) -> Middleware:
    """Build a CORS middleware instance matching the main app's policy."""
    return Middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


async def _health_endpoint(request: Request) -> Response:
    """Health probe for the AG-UI sub-app."""
    return JSONResponse({"status": "ok"})


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

        # Even without a provider, info requests should succeed so CopilotKit
        # can discover the agent and show an appropriate message.
        empty_info = {"agents": {}}

        async def _info_endpoint_no_provider(request: Request) -> Response:
            return JSONResponse(empty_info)

        async def _error_endpoint(request: Request) -> Response:
            body = await request.json()
            if body.get("method") == "info":
                return JSONResponse(empty_info)
            _unwrap_envelope(body, request)
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
            routes=[
                Route("/health", _health_endpoint, methods=["GET"]),
                Route("/info", _info_endpoint_no_provider, methods=["GET"]),
                Route("/", _error_endpoint, methods=["POST"]),
            ],
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

    agent_name = agent.name or "datax-analytics"
    agent_info_response = {
        "agents": {
            agent_name: {
                "description": "AI-powered data analytics assistant",
            }
        }
    }

    async def _info_endpoint(request: Request) -> Response:
        """Return agent info for CopilotKit discovery (GET /info)."""
        return JSONResponse(agent_info_response)

    async def _agent_endpoint(request: Request) -> Response:
        """Handle AG-UI POST requests, intercepting ``info`` before pydantic-ai."""
        body = await request.json()
        if body.get("method") == "info":
            return JSONResponse(agent_info_response)
        _unwrap_envelope(body, request)
        return await handle_ag_ui_request(agent, request, deps=deps)

    agui_app = Starlette(
        routes=[
            Route("/health", _health_endpoint, methods=["GET"]),
            Route("/info", _info_endpoint, methods=["GET"]),
            Route("/", _agent_endpoint, methods=["POST"]),
        ],
        middleware=[cors_middleware],
    )

    logger.info("agui_app_created", agent_name=agent_name, tools_registered=9)
    return agui_app
