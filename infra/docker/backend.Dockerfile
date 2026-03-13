FROM python:3.12-slim

WORKDIR /app

# Install uv for fast Python package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for layer caching
COPY apps/backend/pyproject.toml apps/backend/uv.lock ./

# Install dependencies (no venv needed inside container)
RUN uv sync --frozen --no-dev

# Copy application code (overridden by volume mount in dev)
COPY apps/backend/ .

EXPOSE 8000

# Dev server with hot-reload, listening on all interfaces
CMD ["uv", "run", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--reload"]
