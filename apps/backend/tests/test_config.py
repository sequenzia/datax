import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.config import Settings


class TestSettingsRequired:
    """Test required environment variable handling."""

    def test_missing_database_url_raises_error(self) -> None:
        """Missing DATABASE_URL produces a clear validation error."""
        env = {"DATAX_ENCRYPTION_KEY": "test-key"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError, match="DATABASE_URL"):
                Settings()  # type: ignore[call-arg]

    def test_missing_encryption_key_raises_error(self) -> None:
        """Missing DATAX_ENCRYPTION_KEY produces a clear validation error."""
        env = {"DATABASE_URL": "postgresql://localhost/datax"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError, match="DATAX_ENCRYPTION_KEY"):
                Settings()  # type: ignore[call-arg]

    def test_missing_both_required_vars_raises_error(self) -> None:
        """Missing both required vars produces errors for both."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings()  # type: ignore[call-arg]
            errors = exc_info.value.errors()
            error_locs = {e["loc"][0] for e in errors}
            assert "DATABASE_URL" in error_locs
            assert "DATAX_ENCRYPTION_KEY" in error_locs

    def test_required_vars_set_succeeds(self) -> None:
        """Settings loads successfully when required vars are set."""
        env = {
            "DATABASE_URL": "postgresql://localhost/datax",
            "DATAX_ENCRYPTION_KEY": "test-key-123",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.database_url == "postgresql://localhost/datax"
            assert settings.datax_encryption_key == "test-key-123"


class TestSettingsDefaults:
    """Test optional environment variable defaults."""

    def _base_env(self) -> dict[str, str]:
        return {
            "DATABASE_URL": "postgresql://localhost/datax",
            "DATAX_ENCRYPTION_KEY": "test-key",
        }

    def test_storage_path_default(self) -> None:
        with patch.dict(os.environ, self._base_env(), clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.datax_storage_path == Path("../../data/uploads")

    def test_max_query_timeout_default(self) -> None:
        with patch.dict(os.environ, self._base_env(), clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.datax_max_query_timeout == 30

    def test_max_retries_default(self) -> None:
        with patch.dict(os.environ, self._base_env(), clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.datax_max_retries == 3

    def test_provider_keys_default_none(self) -> None:
        with patch.dict(os.environ, self._base_env(), clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.datax_openai_api_key is None
            assert settings.datax_anthropic_api_key is None
            assert settings.datax_gemini_api_key is None

    def test_cors_origins_default(self) -> None:
        with patch.dict(os.environ, self._base_env(), clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.cors_origins == ["http://localhost:5173"]


class TestSettingsOverrides:
    """Test custom environment variable overrides."""

    def _base_env(self) -> dict[str, str]:
        return {
            "DATABASE_URL": "postgresql://localhost/datax",
            "DATAX_ENCRYPTION_KEY": "test-key",
        }

    def test_custom_storage_path(self) -> None:
        env = {**self._base_env(), "DATAX_STORAGE_PATH": "/custom/path"}
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.datax_storage_path == Path("/custom/path")

    def test_custom_max_query_timeout(self) -> None:
        env = {**self._base_env(), "DATAX_MAX_QUERY_TIMEOUT": "60"}
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.datax_max_query_timeout == 60

    def test_custom_max_retries(self) -> None:
        env = {**self._base_env(), "DATAX_MAX_RETRIES": "5"}
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.datax_max_retries == 5

    def test_provider_api_keys(self) -> None:
        env = {
            **self._base_env(),
            "DATAX_OPENAI_API_KEY": "sk-openai-123",
            "DATAX_ANTHROPIC_API_KEY": "sk-anthropic-456",
            "DATAX_GEMINI_API_KEY": "gemini-789",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.datax_openai_api_key == "sk-openai-123"
            assert settings.datax_anthropic_api_key == "sk-anthropic-456"
            assert settings.datax_gemini_api_key == "gemini-789"

    def test_cors_origins_comma_separated(self) -> None:
        env = {**self._base_env(), "CORS_ORIGINS": "http://localhost:3000,http://localhost:5173"}
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.cors_origins == ["http://localhost:3000", "http://localhost:5173"]
