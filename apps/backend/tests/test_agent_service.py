"""Tests for the Pydantic AI agent service.

Covers:
- Unit: Agent factory for each provider type (openai, anthropic, gemini, openai_compatible)
- Unit: Config loading from DB + env var override
- Unit: Error handling (no provider, invalid provider, invalid API key)
- Integration: Agent responds to basic prompt (using TestModel)
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.models.test import TestModel
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base
from app.services.agent_service import (
    AgentDeps,
    InvalidProviderError,
    NoProviderConfiguredError,
    _resolve_api_key,
    create_agent,
    create_model,
    resolve_provider_config,
)
from app.services.provider_service import (
    ProviderRecord,
    create_provider,
)

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


# ---------------------------------------------------------------------------
# DB-backed fixtures
# ---------------------------------------------------------------------------


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


@pytest.fixture
def db_session(session_factory) -> Session:
    """Yield a DB session for service-layer tests, with rollback on teardown."""
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# ---------------------------------------------------------------------------
# Unit: create_model for each provider type
# ---------------------------------------------------------------------------


class TestCreateModelOpenAI:
    """Test model creation for the OpenAI provider."""

    def test_creates_openai_responses_model(self) -> None:
        """create_model with 'openai' returns an OpenAIResponsesModel."""
        model = create_model(
            provider_name="openai",
            model_name="gpt-4o",
            api_key="sk-test-key",
        )
        assert isinstance(model, OpenAIResponsesModel)

    def test_openai_model_with_custom_model_name(self) -> None:
        """create_model supports custom OpenAI model names."""
        model = create_model(
            provider_name="openai",
            model_name="gpt-4o-mini",
            api_key="sk-test-key",
        )
        assert isinstance(model, OpenAIResponsesModel)


class TestCreateModelAnthropic:
    """Test model creation for the Anthropic provider."""

    def test_creates_anthropic_model(self) -> None:
        """create_model with 'anthropic' returns a valid model."""
        model = create_model(
            provider_name="anthropic",
            model_name="claude-sonnet-4-20250514",
            api_key="sk-ant-test-key",
        )
        # Should be either AnthropicModel or a fallback model
        assert model is not None


class TestCreateModelGemini:
    """Test model creation for the Gemini provider."""

    def test_creates_gemini_model(self) -> None:
        """create_model with 'gemini' returns a valid model."""
        model = create_model(
            provider_name="gemini",
            model_name="gemini-2.0-flash",
            api_key="AIzaSy-test-key",
        )
        assert model is not None


class TestCreateModelOpenAICompatible:
    """Test model creation for the OpenAI-compatible provider."""

    def test_creates_openai_compatible_model(self) -> None:
        """create_model with 'openai_compatible' and base_url returns OpenAIChatModel."""
        model = create_model(
            provider_name="openai_compatible",
            model_name="local-llm",
            api_key="sk-test-key",
            base_url="http://localhost:8080/v1",
        )
        assert isinstance(model, OpenAIChatModel)

    def test_openai_compatible_without_base_url_raises(self) -> None:
        """create_model with 'openai_compatible' without base_url raises InvalidProviderError."""
        with pytest.raises(InvalidProviderError, match="base_url is required"):
            create_model(
                provider_name="openai_compatible",
                model_name="local-llm",
                api_key="sk-test-key",
            )


class TestCreateModelInvalid:
    """Test error handling for invalid provider names."""

    def test_unsupported_provider_raises(self) -> None:
        """create_model with unknown provider raises InvalidProviderError."""
        with pytest.raises(InvalidProviderError, match="Unsupported provider"):
            create_model(
                provider_name="invalid_provider",
                model_name="model",
                api_key="key",
            )


# ---------------------------------------------------------------------------
# Unit: API key resolution (env var override + DB)
# ---------------------------------------------------------------------------


class TestResolveApiKey:
    """Test API key resolution with env var override."""

    def test_env_var_overrides_db_key(self, db_session) -> None:
        """Env var API key takes precedence over DB-stored key."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-env-key"})
        with patch.dict(os.environ, env, clear=True):
            record = create_provider(
                db_session,
                provider_name="openai",
                model_name="gpt-4o",
                api_key="sk-db-key",
            )
            resolved = _resolve_api_key("openai", record)
            assert resolved == "sk-env-key"

    def test_db_key_used_when_no_env_var(self, db_session) -> None:
        """DB-stored key used when no env var is set."""
        with patch.dict(os.environ, _test_env(), clear=True):
            record = create_provider(
                db_session,
                provider_name="openai",
                model_name="gpt-4o",
                api_key="sk-db-key",
            )
            resolved = _resolve_api_key("openai", record)
            assert resolved == "sk-db-key"

    def test_no_key_available_raises(self) -> None:
        """Missing API key raises InvalidProviderError."""
        with patch.dict(os.environ, _test_env(), clear=True):
            record = ProviderRecord(
                id=uuid.uuid4(),
                provider_name="openai",
                model_name="gpt-4o",
                base_url=None,
                is_default=True,
                is_active=True,
                has_api_key=False,
                source="ui",
                created_at=None,  # type: ignore[arg-type]
                encrypted_api_key=None,
            )
            with pytest.raises(InvalidProviderError, match="No API key available"):
                _resolve_api_key("openai", record)

    def test_env_var_whitespace_only_falls_through(self, db_session) -> None:
        """Whitespace-only env var falls through to DB key."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "   "})
        with patch.dict(os.environ, env, clear=True):
            record = create_provider(
                db_session,
                provider_name="openai",
                model_name="gpt-4o",
                api_key="sk-db-key",
            )
            resolved = _resolve_api_key("openai", record)
            assert resolved == "sk-db-key"


# ---------------------------------------------------------------------------
# Unit: Provider resolution
# ---------------------------------------------------------------------------


class TestResolveProviderConfig:
    """Test provider config resolution logic."""

    def test_no_providers_raises(self, db_session) -> None:
        """No providers configured raises NoProviderConfiguredError."""
        with patch.dict(os.environ, _test_env(), clear=True):
            with pytest.raises(NoProviderConfiguredError, match="No AI provider"):
                resolve_provider_config(db_session)

    def test_default_provider_selected(self, db_session) -> None:
        """Default provider is selected when no ID given."""
        with patch.dict(os.environ, _test_env(), clear=True):
            create_provider(
                db_session,
                provider_name="openai",
                model_name="gpt-4o",
                api_key="sk-test",
                is_default=False,
            )
            create_provider(
                db_session,
                provider_name="anthropic",
                model_name="claude-sonnet-4-20250514",
                api_key="sk-test-2",
                is_default=True,
            )
            result = resolve_provider_config(db_session)
            assert result.provider_name == "anthropic"
            assert result.is_default is True

    def test_first_active_used_when_no_default(self, db_session) -> None:
        """First active provider used when none is marked as default."""
        with patch.dict(os.environ, _test_env(), clear=True):
            create_provider(
                db_session,
                provider_name="openai",
                model_name="gpt-4o",
                api_key="sk-test",
                is_default=False,
            )
            result = resolve_provider_config(db_session)
            assert result.provider_name == "openai"

    def test_env_var_provider_used_when_only_env(self, db_session) -> None:
        """Env var provider is resolved when it's the only provider."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-env-key"})
        with patch.dict(os.environ, env, clear=True):
            result = resolve_provider_config(db_session)
            assert result.provider_name == "openai"
            assert result.source == "env_var"

    def test_specific_provider_id(self, db_session) -> None:
        """Specific provider ID is resolved correctly."""
        with patch.dict(os.environ, _test_env(), clear=True):
            record = create_provider(
                db_session,
                provider_name="openai",
                model_name="gpt-4o",
                api_key="sk-test",
            )
            result = resolve_provider_config(db_session, provider_id=str(record.id))
            assert result.id == record.id

    def test_invalid_provider_id_raises(self, db_session) -> None:
        """Invalid provider ID format raises InvalidProviderError."""
        with pytest.raises(InvalidProviderError, match="Invalid provider ID"):
            resolve_provider_config(db_session, provider_id="not-a-uuid")

    def test_nonexistent_provider_id_raises(self, db_session) -> None:
        """Non-existent provider ID raises InvalidProviderError."""
        fake_id = str(uuid.uuid4())
        with patch.dict(os.environ, _test_env(), clear=True):
            with pytest.raises(InvalidProviderError, match="not found"):
                resolve_provider_config(db_session, provider_id=fake_id)


# ---------------------------------------------------------------------------
# Unit: Agent factory
# ---------------------------------------------------------------------------


class TestCreateAgent:
    """Test the create_agent factory function."""

    def test_creates_agent_with_openai(self, session_factory) -> None:
        """create_agent creates an agent with OpenAI provider."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test-openai"})
        with patch.dict(os.environ, env, clear=True):
            agent = create_agent(session_factory=session_factory)
            assert agent is not None
            assert agent.name == "datax-analytics"

    def test_creates_agent_with_anthropic(self, session_factory) -> None:
        """create_agent creates an agent with Anthropic provider."""
        env = _test_env({"DATAX_ANTHROPIC_API_KEY": "sk-ant-test"})
        with patch.dict(os.environ, env, clear=True):
            agent = create_agent(session_factory=session_factory)
            assert agent is not None
            assert agent.name == "datax-analytics"

    def test_creates_agent_with_gemini(self, session_factory) -> None:
        """create_agent creates an agent with Gemini provider."""
        env = _test_env({"DATAX_GEMINI_API_KEY": "AIzaSy-test"})
        with patch.dict(os.environ, env, clear=True):
            agent = create_agent(session_factory=session_factory)
            assert agent is not None
            assert agent.name == "datax-analytics"

    def test_creates_agent_with_openai_compatible(self, db_session, session_factory) -> None:
        """create_agent creates an agent with OpenAI-compatible provider."""
        with patch.dict(os.environ, _test_env(), clear=True):
            create_provider(
                db_session,
                provider_name="openai_compatible",
                model_name="local-llm",
                api_key="sk-test",
                base_url="http://localhost:8080/v1",
                is_default=True,
            )
            db_session.commit()
            agent = create_agent(session_factory=session_factory)
            assert agent is not None
            assert agent.name == "datax-analytics"

    def test_no_provider_raises_clear_error(self, session_factory) -> None:
        """create_agent with no configured provider raises NoProviderConfiguredError."""
        with patch.dict(os.environ, _test_env(), clear=True):
            with pytest.raises(NoProviderConfiguredError, match="No AI provider"):
                create_agent(session_factory=session_factory)

    def test_provider_switchable_without_restart(self, db_session, session_factory) -> None:
        """Different providers can be used by different create_agent calls."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-openai"})
        with patch.dict(os.environ, env, clear=True):
            # Create agent with env var openai
            agent1 = create_agent(session_factory=session_factory)
            assert agent1 is not None

            # Create another provider and use it specifically
            record = create_provider(
                db_session,
                provider_name="openai",
                model_name="gpt-4o-mini",
                api_key="sk-other",
            )
            db_session.commit()
            agent2 = create_agent(provider_id=str(record.id), session_factory=session_factory)
            assert agent2 is not None
            # They should be different agent instances
            assert agent1 is not agent2

    def test_agent_has_system_prompt(self, session_factory) -> None:
        """Created agent has the analytics system prompt."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test"})
        with patch.dict(os.environ, env, clear=True):
            agent = create_agent(session_factory=session_factory)
            # Check that instructions contain the system prompt
            assert agent._instructions is not None
            assert "DataX" in agent._instructions


class TestAgentDeps:
    """Test the AgentDeps dataclass."""

    def test_default_deps(self) -> None:
        """AgentDeps has sensible defaults."""
        deps = AgentDeps()
        assert deps.schema_context == ""
        assert deps.conversation_id is None
        assert deps.available_tables == []

    def test_deps_with_values(self) -> None:
        """AgentDeps can be created with custom values."""
        deps = AgentDeps(
            schema_context="table: users (id, name, email)",
            conversation_id="conv-123",
            available_tables=["users", "orders"],
        )
        assert deps.schema_context == "table: users (id, name, email)"
        assert deps.conversation_id == "conv-123"
        assert deps.available_tables == ["users", "orders"]


# ---------------------------------------------------------------------------
# Integration: Agent responds to basic prompt
# ---------------------------------------------------------------------------


class TestAgentIntegration:
    """Integration tests using pydantic-ai's TestModel."""

    @pytest.mark.asyncio
    async def test_agent_responds_to_basic_prompt(self, session_factory) -> None:
        """Agent created via factory can respond to a basic prompt using TestModel."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test"})
        with patch.dict(os.environ, env, clear=True):
            agent = create_agent(session_factory=session_factory)

            # Override the model with TestModel for testing.
            # call_tools=[] prevents TestModel from trying to invoke
            # registered tools with dummy args.
            test_model = TestModel(
                custom_output_text="Here are the top 10 users by order count.",
                call_tools=[],
            )

            result = await agent.run(
                "Show me the top 10 users by order count",
                deps=AgentDeps(
                    schema_context="table: users (id, name), orders (id, user_id, amount)",
                    available_tables=["users", "orders"],
                ),
                model=test_model,
            )

            assert result.output is not None
            assert isinstance(result.output, str)
            assert len(result.output) > 0

    @pytest.mark.asyncio
    async def test_agent_with_empty_deps(self, session_factory) -> None:
        """Agent works with default empty deps."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test"})
        with patch.dict(os.environ, env, clear=True):
            agent = create_agent(session_factory=session_factory)
            test_model = TestModel(
                custom_output_text="I need more context about your data.",
                call_tools=[],
            )

            result = await agent.run(
                "What data do I have?",
                deps=AgentDeps(),
                model=test_model,
            )

            assert result.output is not None
            assert "context" in result.output.lower()
