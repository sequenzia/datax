"""Health and readiness probe endpoints.

Mounted at the application root (not under /api/v1/) so Kubernetes probes
can reach them without going through API versioning.

- ``GET /health`` -- liveness probe, always returns 200 if the process is alive.
- ``GET /ready``  -- readiness probe, checks PostgreSQL and DuckDB availability.
"""

from __future__ import annotations

from typing import Any

import duckdb
import sqlalchemy
from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe: returns 200 if the FastAPI process is running.

    No dependency checks -- purely confirms the process is alive.
    """
    return {"status": "ok"}


@router.get("/ready")
async def ready(response: Response) -> dict[str, Any]:
    """Readiness probe: checks PostgreSQL and DuckDB availability.

    Returns 200 when all dependencies are reachable, 503 otherwise.
    """
    checks: dict[str, str] = {}

    # --- PostgreSQL check ---
    checks["postgresql"] = await _check_postgresql()

    # --- DuckDB check ---
    checks["duckdb"] = _check_duckdb()

    all_ok = all(v == "ok" for v in checks.values())

    if all_ok:
        return {"status": "ready", "checks": checks}

    return JSONResponse(  # type: ignore[return-value]
        status_code=503,
        content={"status": "unavailable", "checks": checks},
    )


async def _check_postgresql() -> str:
    """Execute ``SELECT 1`` against PostgreSQL to verify connectivity.

    Creates a short-lived synchronous connection using the configured
    DATABASE_URL.  This avoids depending on an application-wide async
    session factory which may not be set up yet.
    """
    try:
        settings = get_settings()
        engine = sqlalchemy.create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return "ok"
    except Exception as exc:
        logger.warning("readiness_postgresql_failed", error=str(exc))
        return f"error: {exc}"


def _check_duckdb() -> str:
    """Verify DuckDB is available by opening an in-memory database."""
    try:
        conn = duckdb.connect(":memory:")
        conn.execute("SELECT 1")
        conn.close()
        return "ok"
    except Exception as exc:
        logger.warning("readiness_duckdb_failed", error=str(exc))
        return f"error: {exc}"
