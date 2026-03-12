"""AI provider settings API endpoints.

Provides CRUD operations for managing AI model provider configurations.
Supports both UI-configured and environment-variable-detected providers.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from app.encryption import EncryptionError
from app.errors import AppError
from app.logging import get_logger
from app.services.provider_service import (
    create_provider,
    delete_provider,
    list_providers,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/settings/providers", tags=["providers"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ProviderCreateRequest(BaseModel):
    """Request body for creating a provider configuration."""

    provider_name: str = Field(..., description="Provider identifier")
    model_name: str = Field(..., description="Model identifier string")
    api_key: str = Field(..., description="API key for the provider")
    base_url: str | None = Field(
        default=None, description="Base URL (required for openai_compatible)"
    )
    is_default: bool = Field(
        default=False, description="Whether this should be the default provider"
    )


class ProviderResponse(BaseModel):
    """Single provider in API responses. Never includes the actual API key."""

    id: UUID
    provider_name: str
    model_name: str
    base_url: str | None
    is_default: bool
    is_active: bool
    has_api_key: bool
    source: str
    created_at: datetime


class ProviderListResponse(BaseModel):
    """Response body for listing providers."""

    providers: list[ProviderResponse]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=ProviderListResponse)
async def list_providers_endpoint() -> ProviderListResponse:
    """List all configured AI providers.

    Returns both UI-configured providers and those detected from
    environment variables. API keys are never exposed; only a
    has_api_key boolean is included.
    """
    records = list_providers()
    return ProviderListResponse(
        providers=[
            ProviderResponse(
                id=r.id,
                provider_name=r.provider_name,
                model_name=r.model_name,
                base_url=r.base_url,
                is_default=r.is_default,
                is_active=r.is_active,
                has_api_key=r.has_api_key,
                source=r.source,
                created_at=r.created_at,
            )
            for r in records
        ]
    )


@router.post("", response_model=ProviderResponse, status_code=201)
async def create_provider_endpoint(body: ProviderCreateRequest) -> ProviderResponse:
    """Add a new AI provider configuration.

    Encrypts the API key using Fernet before storage. If is_default=true,
    all other providers have their default flag unset.
    """
    try:
        record = create_provider(
            provider_name=body.provider_name,
            model_name=body.model_name,
            api_key=body.api_key,
            base_url=body.base_url,
            is_default=body.is_default,
        )
    except ValueError as exc:
        raise AppError(
            code="INVALID_PROVIDER",
            message=str(exc),
            status_code=400,
        ) from exc
    except EncryptionError as exc:
        raise AppError(
            code="ENCRYPTION_ERROR",
            message=f"Failed to encrypt API key: {exc}",
            status_code=500,
        ) from exc

    return ProviderResponse(
        id=record.id,
        provider_name=record.provider_name,
        model_name=record.model_name,
        base_url=record.base_url,
        is_default=record.is_default,
        is_active=record.is_active,
        has_api_key=record.has_api_key,
        source=record.source,
        created_at=record.created_at,
    )


@router.delete("/{provider_id}", status_code=204)
async def delete_provider_endpoint(provider_id: UUID) -> Response:
    """Remove an AI provider configuration.

    Providers configured via environment variables cannot be deleted
    (returns 409 Conflict).
    """
    try:
        delete_provider(provider_id)
    except PermissionError as exc:
        raise AppError(
            code="ENV_VAR_PROVIDER",
            message=str(exc),
            status_code=409,
        ) from exc
    except KeyError as exc:
        raise AppError(
            code="PROVIDER_NOT_FOUND",
            message=str(exc),
            status_code=404,
        ) from exc

    return Response(status_code=204)
