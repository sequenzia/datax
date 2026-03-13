"""Alembic environment configuration.

Reads DATABASE_URL from the environment (via app.config.Settings) and imports
all SQLAlchemy models so autogenerate can detect schema changes.
"""

import os
from logging.config import fileConfig
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from alembic import context

# Load .env.local from project root so DATABASE_URL is available
# without requiring it to be set in the shell environment.
load_dotenv(Path(__file__).resolve().parents[3] / ".env.local")

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models so Alembic autogenerate detects them.
# The import of app.models triggers app/models/__init__.py which
# imports all 7 ORM entity models and re-exports Base.
from app.models import Base  # noqa: E402

target_metadata = Base.metadata

# Override sqlalchemy.url from DATABASE_URL environment variable.
# This avoids storing credentials in alembic.ini.
database_url = os.environ.get("DATABASE_URL")
if database_url:
    # Ensure SQLAlchemy uses psycopg v3 driver, not legacy psycopg2
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL so that SQL can be
    emitted to script output without requiring a live database.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
