from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=True,
        env_file=("../../.env", "../../.env.local", ".env", ".env.local"),
        env_file_encoding="utf-8",
    )

    # Required
    database_url: str = Field(
        ...,
        alias="DATABASE_URL",
        description="PostgreSQL connection string",
    )
    datax_encryption_key: str = Field(
        ...,
        alias="DATAX_ENCRYPTION_KEY",
        description="Fernet master key for encrypting API keys and passwords",
    )

    # Optional with defaults
    datax_duckdb_path: Path = Field(
        default=Path("../../data/datax.duckdb"),
        alias="DATAX_DUCKDB_PATH",
        description="File path for persistent DuckDB database",
    )
    datax_storage_path: Path = Field(
        default=Path("../../data/uploads"),
        alias="DATAX_STORAGE_PATH",
        description="Path for uploaded file storage",
    )
    datax_max_query_timeout: int = Field(
        default=30,
        alias="DATAX_MAX_QUERY_TIMEOUT",
        description="Maximum query execution time in seconds",
    )
    datax_max_retries: int = Field(
        default=3,
        alias="DATAX_MAX_RETRIES",
        description="Maximum agentic retry attempts",
    )
    datax_max_cross_source_rows: int = Field(
        default=100_000,
        alias="DATAX_MAX_CROSS_SOURCE_ROWS",
        description="Maximum rows per sub-query in cross-source queries (memory guard)",
    )

    # Optional provider API keys
    datax_openai_api_key: str | None = Field(
        default=None,
        alias="DATAX_OPENAI_API_KEY",
        description="OpenAI API key (overrides UI-configured key)",
    )
    datax_anthropic_api_key: str | None = Field(
        default=None,
        alias="DATAX_ANTHROPIC_API_KEY",
        description="Anthropic API key (overrides UI-configured key)",
    )
    datax_gemini_api_key: str | None = Field(
        default=None,
        alias="DATAX_GEMINI_API_KEY",
        description="Google Gemini API key (overrides UI-configured key)",
    )

    # httpfs extension for remote data access
    datax_httpfs_enabled: bool = Field(
        default=True,
        alias="DATAX_HTTPFS_ENABLED",
        description="Enable DuckDB httpfs extension for S3/HTTP remote file access",
    )
    datax_httpfs_timeout: int = Field(
        default=30,
        alias="DATAX_HTTPFS_TIMEOUT",
        description="HTTP timeout in seconds for remote file access via httpfs",
    )

    # AWS credentials for S3 access via httpfs
    aws_access_key_id: str | None = Field(
        default=None,
        alias="AWS_ACCESS_KEY_ID",
        description="AWS access key for S3 remote data access",
    )
    aws_secret_access_key: str | None = Field(
        default=None,
        alias="AWS_SECRET_ACCESS_KEY",
        description="AWS secret key for S3 remote data access",
    )
    aws_default_region: str | None = Field(
        default=None,
        alias="AWS_DEFAULT_REGION",
        description="AWS region for S3 remote data access",
    )

    # CORS - stored as comma-separated string, exposed as list via computed_field
    cors_origins_str: str = Field(
        default="http://localhost:5173",
        alias="CORS_ORIGINS",
        description="Allowed CORS origins (comma-separated)",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origins(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins_str.split(",") if origin.strip()]


def get_settings() -> Settings:
    """Create and return application settings from environment variables."""
    return Settings()  # type: ignore[call-arg]
