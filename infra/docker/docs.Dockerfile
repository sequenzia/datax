FROM python:3.12-slim

WORKDIR /docs

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY docs/pyproject.toml ./
RUN uv sync --frozen --no-dev

COPY docs/ .

EXPOSE 8001

CMD ["uv", "run", "mkdocs", "serve", "--dev-addr", "0.0.0.0:8001"]
