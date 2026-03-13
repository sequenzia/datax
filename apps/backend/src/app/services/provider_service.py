"""Service layer for AI provider configuration management.

Handles business logic for provider CRUD operations, environment variable
detection, API key encryption, and default provider uniqueness enforcement.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.encryption import encrypt_value
from app.logging import get_logger

logger = get_logger(__name__)


class ProviderName(StrEnum):
    """Supported AI model provider identifiers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OPENAI_COMPATIBLE = "openai_compatible"


# Maps provider names to their corresponding environment variable names.
PROVIDER_ENV_VARS: dict[str, str] = {
    ProviderName.OPENAI: "DATAX_OPENAI_API_KEY",
    ProviderName.ANTHROPIC: "DATAX_ANTHROPIC_API_KEY",
    ProviderName.GEMINI: "DATAX_GEMINI_API_KEY",
}

VALID_PROVIDER_NAMES: list[str] = [p.value for p in ProviderName]


@dataclass
class ProviderRecord:
    """In-memory representation of a provider configuration.

    Used both for database-stored providers and env-var-detected providers.
    """

    id: uuid.UUID
    provider_name: str
    model_name: str
    base_url: str | None
    is_default: bool
    is_active: bool
    has_api_key: bool
    source: str  # "ui" or "env_var"
    created_at: datetime
    # Internal: only set for DB providers, never exposed via API
    encrypted_api_key: bytes | None = None


# ---------------------------------------------------------------------------
# In-memory store (will be replaced with PostgreSQL once DB sessions are wired)
# ---------------------------------------------------------------------------

_providers: dict[uuid.UUID, ProviderRecord] = {}


def _reset_store() -> None:
    """Reset the in-memory store. Used by tests only."""
    _providers.clear()


# ---------------------------------------------------------------------------
# Environment variable detection
# ---------------------------------------------------------------------------


def _detect_env_providers() -> list[ProviderRecord]:
    """Detect AI providers configured via environment variables.

    Returns a list of ProviderRecords with source="env_var" for each
    provider whose API key environment variable is set and non-empty.
    """
    env_providers: list[ProviderRecord] = []

    default_models: dict[str, str] = {
        ProviderName.OPENAI: "gpt-4o",
        ProviderName.ANTHROPIC: "claude-sonnet-4-20250514",
        ProviderName.GEMINI: "gemini-2.0-flash",
    }

    for provider_name, env_var in PROVIDER_ENV_VARS.items():
        value = os.environ.get(env_var)
        if value and value.strip():
            env_providers.append(
                ProviderRecord(
                    id=uuid.uuid5(uuid.NAMESPACE_DNS, f"env-{provider_name}"),
                    provider_name=provider_name,
                    model_name=default_models.get(provider_name, "default"),
                    base_url=None,
                    is_default=False,
                    is_active=True,
                    has_api_key=True,
                    source="env_var",
                    created_at=datetime.now(UTC),
                )
            )

    return env_providers


def _is_env_var_provider(provider_id: uuid.UUID) -> bool:
    """Check if a provider ID belongs to an env-var-detected provider."""
    for provider_name in PROVIDER_ENV_VARS:
        expected_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"env-{provider_name}")
        if provider_id == expected_id:
            env_var = PROVIDER_ENV_VARS[provider_name]
            value = os.environ.get(env_var)
            if value and value.strip():
                return True
    return False


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


def list_providers() -> list[ProviderRecord]:
    """List all configured providers (both DB and env-var detected).

    Env-var providers are merged with DB providers. If an env-var provider
    has the same provider_name as a DB provider, both appear (env-var takes
    precedence for actual usage, but both are shown so the UI can differentiate).
    """
    # Start with env-var providers
    env_providers = _detect_env_providers()

    # Add all DB providers
    db_providers = list(_providers.values())

    return env_providers + db_providers


def create_provider(
    provider_name: str,
    model_name: str,
    api_key: str,
    base_url: str | None = None,
    is_default: bool = False,
) -> ProviderRecord:
    """Create a new provider configuration.

    Args:
        provider_name: Provider identifier (must be in VALID_PROVIDER_NAMES).
        model_name: Model identifier string.
        api_key: Plain-text API key to encrypt before storage.
        base_url: Optional base URL (required for openai_compatible).
        is_default: Whether this provider should be the default.

    Returns:
        The created ProviderRecord (without encrypted_api_key exposed).

    Raises:
        ValueError: If provider_name is invalid or required fields are missing.
        EncryptionError: If API key encryption fails.
    """
    if provider_name not in VALID_PROVIDER_NAMES:
        raise ValueError(
            f"Invalid provider_name '{provider_name}'. "
            f"Valid providers: {VALID_PROVIDER_NAMES}"
        )

    if provider_name == ProviderName.OPENAI_COMPATIBLE and not base_url:
        raise ValueError(
            "base_url is required for openai_compatible provider"
        )

    if not api_key or not api_key.strip():
        raise ValueError("api_key must be a non-empty string")

    # Encrypt the API key
    encrypted_key = encrypt_value(api_key)

    # If setting as default, unset all other defaults
    if is_default:
        _unset_all_defaults()

    provider_id = uuid.uuid4()
    now = datetime.now(UTC)

    record = ProviderRecord(
        id=provider_id,
        provider_name=provider_name,
        model_name=model_name,
        base_url=base_url,
        is_default=is_default,
        is_active=True,
        has_api_key=True,
        source="ui",
        created_at=now,
        encrypted_api_key=encrypted_key,
    )

    _providers[provider_id] = record
    logger.info(
        "provider_created",
        provider_id=str(provider_id),
        provider_name=provider_name,
        model_name=model_name,
        is_default=is_default,
    )

    return record


def delete_provider(provider_id: uuid.UUID) -> bool:
    """Delete a provider configuration by ID.

    Args:
        provider_id: UUID of the provider to delete.

    Returns:
        True if successfully deleted.

    Raises:
        KeyError: If provider not found.
        PermissionError: If provider is configured via environment variable.
    """
    if _is_env_var_provider(provider_id):
        raise PermissionError(
            "Cannot delete a provider configured via environment variable. "
            "Remove the environment variable to unconfigure this provider."
        )

    if provider_id not in _providers:
        raise KeyError(f"Provider {provider_id} not found")

    del _providers[provider_id]
    logger.info("provider_deleted", provider_id=str(provider_id))
    return True


def get_provider(provider_id: uuid.UUID) -> ProviderRecord | None:
    """Get a single provider by ID (checks both DB and env-var)."""
    # Check DB first
    if provider_id in _providers:
        return _providers[provider_id]

    # Check env-var providers
    for p in _detect_env_providers():
        if p.id == provider_id:
            return p

    return None


def _unset_all_defaults() -> None:
    """Unset is_default on all existing DB providers."""
    for record in _providers.values():
        record.is_default = False
