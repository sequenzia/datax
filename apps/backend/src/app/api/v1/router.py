from fastapi import APIRouter

from app.api.v1.connections import router as connections_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.datasets import router as datasets_router
from app.api.v1.messages import router as messages_router
from app.api.v1.providers import router as providers_router
from app.api.v1.queries import router as queries_router
from app.api.v1.schema import router as schema_router

router = APIRouter(prefix="/api/v1")

router.include_router(connections_router)
router.include_router(conversations_router)
router.include_router(datasets_router)
router.include_router(messages_router)
router.include_router(providers_router)
router.include_router(queries_router)
router.include_router(schema_router)


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe: returns 200 if the process is running."""
    return {"status": "ok"}
