"""Service layer for Pydantic AI agent creation and provider management.

Provides the agent factory that instantiates a Pydantic AI Agent with the
user's selected (or default) provider. Supports OpenAI, Anthropic, Gemini,
and OpenAI-compatible providers.

Provider resolution order:
1. Env var API keys override UI-configured keys (same provider_name)
2. If no env var, uses the encrypted API key from ProviderConfig
3. If no provider configured at all, raises NoProviderConfiguredError
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from sqlalchemy.orm import Session

from app.encryption import decrypt_value
from app.logging import get_logger
from app.services.provider_service import (
    PROVIDER_ENV_VARS,
    ProviderName,
    ProviderRecord,
    get_provider,
    list_providers,
)
from app.services.schema_context import (
    build_schema_context,
    inject_schema_into_prompt,
)

logger = get_logger(__name__)

_anthropic_patched = False


def _patch_anthropic_compat() -> None:
    """Apply compatibility patches for anthropic SDK version mismatches.

    pydantic-ai 0.8.x may expect names that differ between anthropic SDK
    versions (e.g., UserLocation vs BetaUserLocationParam). This function
    applies the necessary aliases so the import chain succeeds.
    """
    global _anthropic_patched
    if _anthropic_patched:
        return
    try:
        import anthropic.types.beta.beta_web_search_tool_20250305_param as ws_module

        if not hasattr(ws_module, "UserLocation"):
            from anthropic.types.beta.beta_user_location_param import (
                BetaUserLocationParam,
            )

            ws_module.UserLocation = BetaUserLocationParam  # type: ignore[attr-defined]
    except (ImportError, AttributeError):
        pass
    _anthropic_patched = True


# ---------------------------------------------------------------------------
# System prompt for data analytics context
# ---------------------------------------------------------------------------

ANALYTICS_SYSTEM_PROMPT = """\
You are DataX, an AI data analytics assistant. \
Your role is to help users explore and understand their data \
through natural language conversation.

Your capabilities:
- Generate SQL queries based on user questions
- Analyze query results and provide clear explanations
- Suggest appropriate visualizations for data
- Help users refine their questions for better results

Guidelines:
- Always generate valid SQL for the target database dialect
- Explain your reasoning when generating queries
- When results are ambiguous, ask clarifying questions
- Suggest chart types based on data shape: single numeric for KPIs, \
time series for line charts, categories for bar charts, \
proportions for pie charts, two numerics for scatter plots
- If a query fails, analyze the error and suggest corrections
- Never modify data unless explicitly asked — default to read-only queries

Available schema context will be provided with each conversation."""

# ---------------------------------------------------------------------------
# Default models per provider
# ---------------------------------------------------------------------------

DEFAULT_MODELS: dict[str, str] = {
    ProviderName.OPENAI: "gpt-4o",
    ProviderName.ANTHROPIC: "claude-sonnet-4-20250514",
    ProviderName.GEMINI: "gemini-2.0-flash",
    ProviderName.OPENAI_COMPATIBLE: "default",
}

# Maps provider names to their pydantic-ai model string prefix
PROVIDER_MODEL_PREFIXES: dict[str, str] = {
    ProviderName.OPENAI: "openai",
    ProviderName.ANTHROPIC: "anthropic",
    ProviderName.GEMINI: "google-gla",
    ProviderName.OPENAI_COMPATIBLE: "openai",
}


# ---------------------------------------------------------------------------
# Agent dependencies
# ---------------------------------------------------------------------------


@dataclass
class AgentDeps:
    """Dependencies injected into the Pydantic AI agent at runtime.

    These are passed to tool functions and system prompt functions to provide
    context about the current conversation and available data sources.
    """

    schema_context: str = ""
    conversation_id: str | None = None
    available_tables: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class NoProviderConfiguredError(Exception):
    """No AI provider is configured — cannot create an agent."""


class InvalidProviderError(Exception):
    """The configured provider is invalid or cannot be used."""


class ProviderConnectionError(Exception):
    """Failed to connect to the AI provider."""


# ---------------------------------------------------------------------------
# Model creation
# ---------------------------------------------------------------------------


def _resolve_api_key(provider_name: str, record: ProviderRecord | None) -> str:
    """Resolve the API key for a provider, with env var override.

    Args:
        provider_name: The provider identifier.
        record: The provider record (may be None for env-var-only providers).

    Returns:
        The resolved API key as plaintext.

    Raises:
        InvalidProviderError: If no API key is available.
    """
    # Check env var first (env var overrides DB-stored key)
    env_var_name = PROVIDER_ENV_VARS.get(provider_name)
    if env_var_name:
        env_value = os.environ.get(env_var_name)
        if env_value and env_value.strip():
            return env_value.strip()

    # Fall back to encrypted key from DB record
    if record and record.encrypted_api_key:
        return decrypt_value(record.encrypted_api_key)

    raise InvalidProviderError(
        f"No API key available for provider '{provider_name}'. "
        f"Set the {env_var_name or 'API key'} environment variable "
        f"or configure it in the UI."
    )


def create_model(
    provider_name: str,
    model_name: str,
    api_key: str,
    base_url: str | None = None,
    timeout: float = 30.0,
) -> Model:
    """Create a pydantic-ai Model instance for the given provider.

    Args:
        provider_name: Provider identifier (openai, anthropic, gemini, openai_compatible).
        model_name: The model name to use (e.g., 'gpt-4o', 'claude-sonnet-4-20250514').
        api_key: The API key for authentication.
        base_url: Optional base URL for OpenAI-compatible providers.
        timeout: Request timeout in seconds.

    Returns:
        A pydantic-ai Model instance ready for use with an Agent.

    Raises:
        InvalidProviderError: If the provider_name is not supported.
    """
    if provider_name == ProviderName.OPENAI:
        provider = OpenAIProvider(api_key=api_key)
        return OpenAIResponsesModel(model_name, provider=provider)

    if provider_name == ProviderName.ANTHROPIC:
        from pydantic_ai.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key=api_key)
        _patch_anthropic_compat()
        from pydantic_ai.models.anthropic import AnthropicModel

        return AnthropicModel(model_name, provider=provider)

    if provider_name == ProviderName.GEMINI:
        try:
            from pydantic_ai.models.google import GoogleModel
            from pydantic_ai.providers.google import GoogleProvider

            provider = GoogleProvider(api_key=api_key)
            return GoogleModel(model_name, provider=provider)
        except ImportError:
            # Fallback to older API
            from pydantic_ai.models.gemini import GeminiModel
            from pydantic_ai.providers.google_gla import GoogleGLAProvider

            provider = GoogleGLAProvider(api_key=api_key)
            return GeminiModel(model_name, provider=provider)

    if provider_name == ProviderName.OPENAI_COMPATIBLE:
        if not base_url:
            raise InvalidProviderError(
                "base_url is required for openai_compatible provider"
            )
        provider = OpenAIProvider(api_key=api_key, base_url=base_url)
        return OpenAIChatModel(model_name, provider=provider)

    raise InvalidProviderError(
        f"Unsupported provider '{provider_name}'. "
        f"Supported providers: openai, anthropic, gemini, openai_compatible"
    )


# ---------------------------------------------------------------------------
# Provider resolution
# ---------------------------------------------------------------------------


def resolve_provider_config(
    provider_id: str | None = None,
) -> ProviderRecord:
    """Resolve which provider to use for the agent.

    Resolution order:
    1. If provider_id is given, use that specific provider
    2. Otherwise, find the default provider
    3. Otherwise, use the first active provider

    Args:
        provider_id: Optional UUID string of a specific provider to use.

    Returns:
        The resolved ProviderRecord.

    Raises:
        NoProviderConfiguredError: If no provider is available.
        InvalidProviderError: If the specified provider_id is not found.
    """
    import uuid

    # If specific provider requested
    if provider_id:
        try:
            pid = uuid.UUID(provider_id)
        except ValueError:
            raise InvalidProviderError(f"Invalid provider ID format: {provider_id}")

        record = get_provider(pid)
        if record is None:
            raise InvalidProviderError(f"Provider '{provider_id}' not found")
        if not record.is_active:
            raise InvalidProviderError(f"Provider '{provider_id}' is not active")
        return record

    # Find from all providers
    all_providers = list_providers()
    if not all_providers:
        raise NoProviderConfiguredError(
            "No AI provider is configured. Please configure at least one provider "
            "in Settings, or set a DATAX_*_API_KEY environment variable."
        )

    # Prefer the default provider
    for p in all_providers:
        if p.is_default and p.is_active:
            return p

    # Fall back to first active provider
    for p in all_providers:
        if p.is_active:
            return p

    raise NoProviderConfiguredError(
        "No active AI provider found. All configured providers are inactive."
    )


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------


def create_agent(
    provider_id: str | None = None,
    timeout: float = 30.0,
    max_retries: int = 3,
    session: Session | None = None,
) -> Agent[AgentDeps, str]:
    """Create a Pydantic AI Agent with the resolved provider configuration.

    This is the main entry point for creating an agent. It resolves the
    provider configuration, builds the model, and creates the agent with
    the analytics system prompt. When a database session is provided,
    schema context is queried and injected into the system prompt.

    Args:
        provider_id: Optional UUID string of a specific provider to use.
            If not given, the default or first active provider is used.
        timeout: Request timeout in seconds.
        max_retries: Maximum number of retries for failed model calls.
        session: Optional SQLAlchemy session for querying schema metadata.
            When provided, schema context is dynamically injected into the
            system prompt. When None, only the base prompt is used.

    Returns:
        A configured Pydantic AI Agent ready for use.

    Raises:
        NoProviderConfiguredError: If no provider is configured.
        InvalidProviderError: If the provider is invalid or misconfigured.
    """
    record = resolve_provider_config(provider_id)

    api_key = _resolve_api_key(record.provider_name, record)

    model = create_model(
        provider_name=record.provider_name,
        model_name=record.model_name,
        api_key=api_key,
        base_url=record.base_url,
        timeout=timeout,
    )

    # Build the system prompt with optional schema context
    system_prompt = ANALYTICS_SYSTEM_PROMPT
    if session is not None:
        schema_result = build_schema_context(session)
        system_prompt = inject_schema_into_prompt(
            ANALYTICS_SYSTEM_PROMPT, schema_result.context_text
        )
        logger.info(
            "schema_context_injected",
            table_count=schema_result.table_count,
            total_columns=schema_result.total_columns,
            truncated=schema_result.truncated,
            has_error=schema_result.error is not None,
        )

    agent: Agent[AgentDeps, str] = Agent(
        model,
        instructions=system_prompt,
        deps_type=AgentDeps,
        retries=max_retries,
        model_settings={"timeout": timeout},
        name="datax-analytics",
    )

    logger.info(
        "agent_created",
        provider=record.provider_name,
        model=record.model_name,
        provider_source=record.source,
    )

    return agent


def build_agent_deps(session: Session) -> AgentDeps:
    """Build AgentDeps with schema context from the database.

    Queries all available schema metadata and constructs an ``AgentDeps``
    instance with the formatted schema context and available table names.

    This is the primary entry point for per-request schema injection:
    callers should create deps via this function and pass them to
    ``agent.run()``.

    Args:
        session: An active SQLAlchemy session.

    Returns:
        An AgentDeps instance populated with schema context.
    """
    schema_result = build_schema_context(session)

    # Collect available table names from the schema result
    available_tables: list[str] = []
    if not schema_result.error and schema_result.table_count > 0:
        # Re-query just the distinct table names for the tables list
        from sqlalchemy import distinct
        from sqlalchemy import select as sa_select

        from app.models.orm import SchemaMetadata as SchemaM

        stmt = sa_select(distinct(SchemaM.table_name)).order_by(SchemaM.table_name)
        available_tables = [
            row[0] for row in session.execute(stmt).all()
        ]

    return AgentDeps(
        schema_context=schema_result.context_text,
        available_tables=available_tables,
    )
