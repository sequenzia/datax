"""Tests for the AI provider settings API endpoints.

Covers:
- Unit: API key encryption/decryption round-trip
- Unit: Env var detection for each provider
- Integration: Provider CRUD operations
- Integration: Default provider uniqueness constraint
- Edge cases: env var providers, openai_compatible base_url, invalid provider names
- Error handling: invalid provider, encryption failures, env var deletion
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.encryption import decrypt_value, encrypt_value
from app.main import create_app
from app.models.base import Base
from app.services.provider_service import (
    VALID_PROVIDER_NAMES,
    _detect_env_providers,
    _is_env_var_provider,
    create_provider,
    delete_provider,
    list_providers,
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
# DB-backed fixtures for service-layer and integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path():
    """Create a temporary file for SQLite database."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d) / "test.db"


def _test_settings(db_path: Path) -> Settings:
    """Create test settings with required fields."""
    env = {
        "DATABASE_URL": f"sqlite:///{db_path}",
        "DATAX_ENCRYPTION_KEY": TEST_FERNET_KEY,
        "DATAX_DUCKDB_PATH": ":memory:",
    }
    with patch.dict(os.environ, env, clear=True):
        return Settings()  # type: ignore[call-arg]


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


@pytest.fixture
def app(db_path, db_engine, session_factory):
    """Create a FastAPI app with a test SQLite database."""
    application = create_app(settings=_test_settings(db_path))
    application.state.db_engine = db_engine
    application.state.session_factory = session_factory
    return application


@pytest.fixture
async def client(app):
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


# ---------------------------------------------------------------------------
# Unit: API key encryption/decryption round-trip
# ---------------------------------------------------------------------------


class TestEncryptionRoundTrip:
    """Verify API key encryption/decryption works end-to-end."""

    def test_api_key_encrypt_decrypt_round_trip(self) -> None:
        """Encrypting an API key and decrypting it returns the original."""
        with patch.dict(os.environ, _test_env(), clear=True):
            api_key = "sk-test-key-1234567890abcdef"
            encrypted = encrypt_value(api_key)
            decrypted = decrypt_value(encrypted)
            assert decrypted == api_key

    def test_different_keys_produce_different_ciphertexts(self) -> None:
        """Two different API keys produce different encrypted outputs."""
        with patch.dict(os.environ, _test_env(), clear=True):
            ct1 = encrypt_value("sk-key-one")
            ct2 = encrypt_value("sk-key-two")
            assert ct1 != ct2

    def test_encrypted_api_key_stored_on_provider(self, db_session) -> None:
        """Creating a provider stores the encrypted API key internally."""
        with patch.dict(os.environ, _test_env(), clear=True):
            api_key = "sk-stored-test-key"
            record = create_provider(
                db_session,
                provider_name="openai",
                model_name="gpt-4o",
                api_key=api_key,
            )
            # encrypted_api_key should be set (bytes)
            assert record.encrypted_api_key is not None
            assert isinstance(record.encrypted_api_key, bytes)
            # Round-trip: decrypt should recover original
            decrypted = decrypt_value(record.encrypted_api_key)
            assert decrypted == api_key


# ---------------------------------------------------------------------------
# Unit: Env var detection for each provider
# ---------------------------------------------------------------------------


class TestEnvVarDetection:
    """Verify environment variable detection for each supported provider."""

    def test_detect_openai_env_var(self) -> None:
        """DATAX_OPENAI_API_KEY env var detected as openai provider."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test-openai"})
        with patch.dict(os.environ, env, clear=True):
            providers = _detect_env_providers()
            names = [p.provider_name for p in providers]
            assert "openai" in names
            openai = next(p for p in providers if p.provider_name == "openai")
            assert openai.source == "env_var"
            assert openai.has_api_key is True

    def test_detect_anthropic_env_var(self) -> None:
        """DATAX_ANTHROPIC_API_KEY env var detected as anthropic provider."""
        env = _test_env({"DATAX_ANTHROPIC_API_KEY": "sk-ant-test"})
        with patch.dict(os.environ, env, clear=True):
            providers = _detect_env_providers()
            names = [p.provider_name for p in providers]
            assert "anthropic" in names
            anthropic = next(p for p in providers if p.provider_name == "anthropic")
            assert anthropic.source == "env_var"

    def test_detect_gemini_env_var(self) -> None:
        """DATAX_GEMINI_API_KEY env var detected as gemini provider."""
        env = _test_env({"DATAX_GEMINI_API_KEY": "AIzaSy-test"})
        with patch.dict(os.environ, env, clear=True):
            providers = _detect_env_providers()
            names = [p.provider_name for p in providers]
            assert "gemini" in names

    def test_no_env_vars_returns_empty(self) -> None:
        """No provider env vars set returns empty list."""
        with patch.dict(os.environ, _test_env(), clear=True):
            providers = _detect_env_providers()
            assert providers == []

    def test_empty_env_var_not_detected(self) -> None:
        """Empty string env var is not detected as a provider."""
        env = _test_env({"DATAX_OPENAI_API_KEY": ""})
        with patch.dict(os.environ, env, clear=True):
            providers = _detect_env_providers()
            assert len(providers) == 0

    def test_whitespace_only_env_var_not_detected(self) -> None:
        """Whitespace-only env var is not detected as a provider."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "   "})
        with patch.dict(os.environ, env, clear=True):
            providers = _detect_env_providers()
            assert len(providers) == 0

    def test_multiple_env_vars_detected(self) -> None:
        """Multiple provider env vars are all detected."""
        env = _test_env({
            "DATAX_OPENAI_API_KEY": "sk-openai",
            "DATAX_ANTHROPIC_API_KEY": "sk-anthropic",
            "DATAX_GEMINI_API_KEY": "AIzaSy-gemini",
        })
        with patch.dict(os.environ, env, clear=True):
            providers = _detect_env_providers()
            assert len(providers) == 3

    def test_env_var_provider_has_deterministic_id(self) -> None:
        """Env var providers produce a deterministic UUID based on provider name."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test"})
        with patch.dict(os.environ, env, clear=True):
            providers1 = _detect_env_providers()
            providers2 = _detect_env_providers()
            assert providers1[0].id == providers2[0].id

    def test_is_env_var_provider_returns_true(self) -> None:
        """_is_env_var_provider returns True for detected env var provider IDs."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-test"})
        with patch.dict(os.environ, env, clear=True):
            providers = _detect_env_providers()
            assert _is_env_var_provider(providers[0].id) is True

    def test_is_env_var_provider_returns_false_for_db_provider(self) -> None:
        """_is_env_var_provider returns False for a random UUID."""
        with patch.dict(os.environ, _test_env(), clear=True):
            assert _is_env_var_provider(uuid.uuid4()) is False


# ---------------------------------------------------------------------------
# Integration: Provider CRUD operations
# ---------------------------------------------------------------------------


class TestProviderCRUD:
    """Integration tests for provider CRUD via the API."""

    @pytest.mark.asyncio
    async def test_list_providers_empty(self, client) -> None:
        """GET /settings/providers returns empty list when none configured."""
        with patch.dict(os.environ, _test_env(), clear=True):
            response = await client.get("/api/v1/settings/providers")

        assert response.status_code == 200
        body = response.json()
        assert body["providers"] == []

    @pytest.mark.asyncio
    async def test_create_provider(self, client) -> None:
        """POST /settings/providers creates a new provider (201)."""
        with patch.dict(os.environ, _test_env(), clear=True):
            response = await client.post(
                "/api/v1/settings/providers",
                json={
                    "provider_name": "openai",
                    "model_name": "gpt-4o",
                    "api_key": "sk-test-create-key",
                    "is_default": True,
                },
            )

        assert response.status_code == 201
        body = response.json()
        assert body["provider_name"] == "openai"
        assert body["model_name"] == "gpt-4o"
        assert body["is_default"] is True
        assert body["is_active"] is True
        assert body["has_api_key"] is True
        assert body["source"] == "ui"
        assert "api_key" not in body
        assert "encrypted_api_key" not in body
        assert "id" in body
        assert "created_at" in body

    @pytest.mark.asyncio
    async def test_create_and_list_provider(self, client) -> None:
        """Created provider appears in the list endpoint."""
        with patch.dict(os.environ, _test_env(), clear=True):
            create_resp = await client.post(
                "/api/v1/settings/providers",
                json={
                    "provider_name": "anthropic",
                    "model_name": "claude-sonnet-4-20250514",
                    "api_key": "sk-ant-test-key",
                },
            )
            assert create_resp.status_code == 201
            created_id = create_resp.json()["id"]

            list_resp = await client.get("/api/v1/settings/providers")

        assert list_resp.status_code == 200
        providers = list_resp.json()["providers"]
        ids = [p["id"] for p in providers]
        assert created_id in ids

    @pytest.mark.asyncio
    async def test_delete_provider(self, client) -> None:
        """DELETE /settings/providers/{id} removes the provider (204)."""
        with patch.dict(os.environ, _test_env(), clear=True):
            create_resp = await client.post(
                "/api/v1/settings/providers",
                json={
                    "provider_name": "openai",
                    "model_name": "gpt-4o",
                    "api_key": "sk-test-delete-key",
                },
            )
            provider_id = create_resp.json()["id"]

            del_resp = await client.delete(
                f"/api/v1/settings/providers/{provider_id}"
            )
            assert del_resp.status_code == 204

            # Verify it's gone
            list_resp = await client.get("/api/v1/settings/providers")

        providers = list_resp.json()["providers"]
        ids = [p["id"] for p in providers]
        assert provider_id not in ids

    @pytest.mark.asyncio
    async def test_delete_nonexistent_provider_returns_404(self, client) -> None:
        """DELETE for a non-existent provider returns 404."""
        fake_id = uuid.uuid4()
        with patch.dict(os.environ, _test_env(), clear=True):
            response = await client.delete(
                f"/api/v1/settings/providers/{fake_id}"
            )

        assert response.status_code == 404
        body = response.json()
        assert body["error"]["code"] == "PROVIDER_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_api_key_never_in_response(self, client) -> None:
        """Neither api_key nor encrypted_api_key appear in any response."""
        with patch.dict(os.environ, _test_env(), clear=True):
            create_resp = await client.post(
                "/api/v1/settings/providers",
                json={
                    "provider_name": "openai",
                    "model_name": "gpt-4o",
                    "api_key": "sk-secret-value",
                },
            )

        create_body = create_resp.json()
        assert "api_key" not in create_body
        assert "encrypted_api_key" not in create_body

        with patch.dict(os.environ, _test_env(), clear=True):
            list_resp = await client.get("/api/v1/settings/providers")

        for provider in list_resp.json()["providers"]:
            assert "api_key" not in provider
            assert "encrypted_api_key" not in provider


# ---------------------------------------------------------------------------
# Integration: Default provider uniqueness
# ---------------------------------------------------------------------------


class TestDefaultProviderUniqueness:
    """Only one provider can be the default at a time."""

    @pytest.mark.asyncio
    async def test_setting_new_default_unsets_previous(self, client) -> None:
        """Creating a new default provider unsets the previous one."""
        with patch.dict(os.environ, _test_env(), clear=True):
            # Create first default provider
            resp1 = await client.post(
                "/api/v1/settings/providers",
                json={
                    "provider_name": "openai",
                    "model_name": "gpt-4o",
                    "api_key": "sk-first-default",
                    "is_default": True,
                },
            )
            assert resp1.status_code == 201
            assert resp1.json()["is_default"] is True
            first_id = resp1.json()["id"]

            # Create second default provider
            resp2 = await client.post(
                "/api/v1/settings/providers",
                json={
                    "provider_name": "anthropic",
                    "model_name": "claude-sonnet-4-20250514",
                    "api_key": "sk-second-default",
                    "is_default": True,
                },
            )
            assert resp2.status_code == 201
            assert resp2.json()["is_default"] is True

            # List all and verify only the second is default
            list_resp = await client.get("/api/v1/settings/providers")

        providers = list_resp.json()["providers"]
        defaults = [p for p in providers if p["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["provider_name"] == "anthropic"

        # First provider should no longer be default
        first = next(p for p in providers if p["id"] == first_id)
        assert first["is_default"] is False

    @pytest.mark.asyncio
    async def test_non_default_does_not_affect_existing_default(self, client) -> None:
        """Creating a non-default provider does not change the existing default."""
        with patch.dict(os.environ, _test_env(), clear=True):
            # Create default provider
            resp1 = await client.post(
                "/api/v1/settings/providers",
                json={
                    "provider_name": "openai",
                    "model_name": "gpt-4o",
                    "api_key": "sk-default-stays",
                    "is_default": True,
                },
            )
            assert resp1.json()["is_default"] is True
            first_id = resp1.json()["id"]

            # Create non-default provider
            await client.post(
                "/api/v1/settings/providers",
                json={
                    "provider_name": "anthropic",
                    "model_name": "claude-sonnet-4-20250514",
                    "api_key": "sk-non-default",
                    "is_default": False,
                },
            )

            list_resp = await client.get("/api/v1/settings/providers")

        providers = list_resp.json()["providers"]
        first = next(p for p in providers if p["id"] == first_id)
        assert first["is_default"] is True


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for provider endpoints."""

    @pytest.mark.asyncio
    async def test_env_var_provider_cannot_be_deleted(self, client) -> None:
        """Attempting to delete an env var provider returns 409."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-env-test"})
        with patch.dict(os.environ, env, clear=True):
            # Get the env var provider's ID from the list
            list_resp = await client.get("/api/v1/settings/providers")
            providers = list_resp.json()["providers"]
            env_provider = next(
                p for p in providers if p["source"] == "env_var"
            )

            # Try to delete
            del_resp = await client.delete(
                f"/api/v1/settings/providers/{env_provider['id']}"
            )

        assert del_resp.status_code == 409
        assert del_resp.json()["error"]["code"] == "ENV_VAR_PROVIDER"

    @pytest.mark.asyncio
    async def test_env_var_providers_listed_with_source_env_var(self, client) -> None:
        """Env var providers appear in list with source='env_var'."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-env-list-test"})
        with patch.dict(os.environ, env, clear=True):
            response = await client.get("/api/v1/settings/providers")

        body = response.json()
        env_providers = [p for p in body["providers"] if p["source"] == "env_var"]
        assert len(env_providers) >= 1
        assert env_providers[0]["provider_name"] == "openai"
        assert env_providers[0]["has_api_key"] is True

    @pytest.mark.asyncio
    async def test_openai_compatible_requires_base_url(self, client) -> None:
        """openai_compatible provider without base_url returns 400."""
        with patch.dict(os.environ, _test_env(), clear=True):
            response = await client.post(
                "/api/v1/settings/providers",
                json={
                    "provider_name": "openai_compatible",
                    "model_name": "local-llm",
                    "api_key": "sk-test",
                },
            )

        assert response.status_code == 400
        assert "base_url" in response.json()["error"]["message"]

    @pytest.mark.asyncio
    async def test_openai_compatible_with_base_url_succeeds(self, client) -> None:
        """openai_compatible provider with base_url creates successfully."""
        with patch.dict(os.environ, _test_env(), clear=True):
            response = await client.post(
                "/api/v1/settings/providers",
                json={
                    "provider_name": "openai_compatible",
                    "model_name": "local-llm",
                    "api_key": "sk-test",
                    "base_url": "http://localhost:8080/v1",
                },
            )

        assert response.status_code == 201
        body = response.json()
        assert body["provider_name"] == "openai_compatible"
        assert body["base_url"] == "http://localhost:8080/v1"


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Error handling tests for provider endpoints."""

    @pytest.mark.asyncio
    async def test_invalid_provider_name_returns_400(self, client) -> None:
        """Invalid provider_name returns 400 with list of valid providers."""
        with patch.dict(os.environ, _test_env(), clear=True):
            response = await client.post(
                "/api/v1/settings/providers",
                json={
                    "provider_name": "invalid_provider",
                    "model_name": "some-model",
                    "api_key": "sk-test",
                },
            )

        assert response.status_code == 400
        body = response.json()
        assert body["error"]["code"] == "INVALID_PROVIDER"
        # The error message should list valid providers
        for valid_name in VALID_PROVIDER_NAMES:
            assert valid_name in body["error"]["message"]

    @pytest.mark.asyncio
    async def test_empty_api_key_returns_400(self, client) -> None:
        """Empty API key returns 400 validation error."""
        with patch.dict(os.environ, _test_env(), clear=True):
            response = await client.post(
                "/api/v1/settings/providers",
                json={
                    "provider_name": "openai",
                    "model_name": "gpt-4o",
                    "api_key": "",
                },
            )

        assert response.status_code == 400
        body = response.json()
        assert body["error"]["code"] == "INVALID_PROVIDER"

    @pytest.mark.asyncio
    async def test_whitespace_only_api_key_returns_400(self, client) -> None:
        """Whitespace-only API key returns 400."""
        with patch.dict(os.environ, _test_env(), clear=True):
            response = await client.post(
                "/api/v1/settings/providers",
                json={
                    "provider_name": "openai",
                    "model_name": "gpt-4o",
                    "api_key": "   ",
                },
            )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_required_fields_returns_422(self, client) -> None:
        """Missing required fields return 422 validation error."""
        with patch.dict(os.environ, _test_env(), clear=True):
            response = await client.post(
                "/api/v1/settings/providers",
                json={"provider_name": "openai"},
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_uuid_in_delete_returns_422(self, client) -> None:
        """Invalid UUID format in DELETE path returns 422."""
        with patch.dict(os.environ, _test_env(), clear=True):
            response = await client.delete(
                "/api/v1/settings/providers/not-a-uuid"
            )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Service layer unit tests
# ---------------------------------------------------------------------------


class TestServiceLayer:
    """Direct tests for the provider service layer."""

    def test_create_provider_returns_record(self, db_session) -> None:
        """create_provider returns a ProviderRecord with correct fields."""
        with patch.dict(os.environ, _test_env(), clear=True):
            record = create_provider(
                db_session,
                provider_name="openai",
                model_name="gpt-4o",
                api_key="sk-test-service",
            )
            assert record.provider_name == "openai"
            assert record.model_name == "gpt-4o"
            assert record.is_active is True
            assert record.source == "ui"
            assert record.has_api_key is True

    def test_create_invalid_provider_raises(self, db_session) -> None:
        """create_provider raises ValueError for invalid provider_name."""
        with patch.dict(os.environ, _test_env(), clear=True):
            with pytest.raises(ValueError, match="Invalid provider_name"):
                create_provider(
                    db_session,
                    provider_name="fake_provider",
                    model_name="model",
                    api_key="key",
                )

    def test_delete_env_var_provider_raises(self, db_session) -> None:
        """delete_provider raises PermissionError for env var providers."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-env"})
        with patch.dict(os.environ, env, clear=True):
            providers = _detect_env_providers()
            env_id = providers[0].id
            with pytest.raises(PermissionError, match="environment variable"):
                delete_provider(db_session, env_id)

    def test_delete_nonexistent_raises_key_error(self, db_session) -> None:
        """delete_provider raises KeyError for nonexistent provider."""
        with patch.dict(os.environ, _test_env(), clear=True):
            with pytest.raises(KeyError):
                delete_provider(db_session, uuid.uuid4())

    def test_list_includes_both_env_and_db(self, db_session) -> None:
        """list_providers includes both env var and DB providers."""
        env = _test_env({"DATAX_OPENAI_API_KEY": "sk-env"})
        with patch.dict(os.environ, env, clear=True):
            create_provider(
                db_session,
                provider_name="anthropic",
                model_name="claude-sonnet-4-20250514",
                api_key="sk-db",
            )
            providers = list_providers(db_session)

        sources = {p.source for p in providers}
        assert "env_var" in sources
        assert "ui" in sources

    def test_default_uniqueness_at_service_level(self, db_session) -> None:
        """Setting a new default unsets the old one in the service layer."""
        with patch.dict(os.environ, _test_env(), clear=True):
            first = create_provider(
                db_session,
                provider_name="openai",
                model_name="gpt-4o",
                api_key="sk-first",
                is_default=True,
            )
            assert first.is_default is True

            create_provider(
                db_session,
                provider_name="anthropic",
                model_name="claude-sonnet-4-20250514",
                api_key="sk-second",
                is_default=True,
            )

            # Check the first one is no longer default
            providers = list_providers(db_session)
            db_providers = [p for p in providers if p.source == "ui"]
            defaults = [p for p in db_providers if p.is_default]
            assert len(defaults) == 1
            assert defaults[0].provider_name == "anthropic"
