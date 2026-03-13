# DataX

**AI-native data analytics platform — chat with your data.**

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![DuckDB](https://img.shields.io/badge/DuckDB-1.2+-FFF000?logo=duckdb&logoColor=black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)

## Overview

DataX lets you ask questions about your data in natural language. An AI agent translates your questions into SQL, executes queries against your data sources, and returns results with interactive visualizations — all through a conversational chat interface.

**Supported data sources:** Upload CSV, Excel, Parquet, or JSON files, or connect directly to PostgreSQL and MySQL databases. DataX can even join data across uploaded files and live database connections in a single query.

## Features

- **Natural language to SQL** with self-correcting retry loop (up to 3 attempts)
- **Multi-provider AI** — OpenAI, Anthropic, Gemini, and OpenAI-compatible endpoints
- **File upload** with automatic schema detection via DuckDB virtual tables
- **Live database connections** with Fernet-encrypted credentials and read-only query execution
- **Cross-source queries** — join uploaded files with live database tables
- **Interactive Plotly charts** with AI-selected chart types and PNG/SVG export
- **SQL editor** with CodeMirror 6, schema-aware autocomplete, and query saving
- **Real-time streaming** responses via Server-Sent Events (SSE)
- **Dark/light theme** with responsive layout (desktop, tablet, mobile)

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Backend** | Python 3.12+, FastAPI, Pydantic AI, SQLAlchemy 2, DuckDB, PostgreSQL 16, Alembic, structlog |
| **Frontend** | React 19, TypeScript 5.9, Vite 7, TanStack Query 5, Zustand 5, Tailwind CSS 4, shadcn/ui, CodeMirror 6, Plotly.js, Streamdown |
| **Infrastructure** | Docker Compose, PostgreSQL 16, Turborepo |

## Quick Start

### Prerequisites

- **Docker** (recommended) — or Python 3.12+, Node.js 22+, pnpm, and PostgreSQL 16
- An API key from at least one AI provider (OpenAI, Anthropic, or Gemini)

### Docker Compose (recommended)

```bash
cp .env.example .env
# Edit .env to set your encryption key for production use
docker compose up
```

The app will be available at:
- **Frontend:** http://localhost:5173
- **Backend API:** http://localhost:8000
- **API docs:** http://localhost:8000/docs

### Manual Setup

**Backend:**

```bash
cd apps/backend
uv sync
# Set required environment variables (see Environment Variables below)
uv run alembic upgrade head
uv run uvicorn app.main:create_app --factory --reload --host 0.0.0.0 --port 8000
```

**Frontend:**

```bash
cd apps/frontend
pnpm install
pnpm dev
```

**Both (concurrent):**

```bash
./scripts/dev.sh
```

## Architecture

```
User question
    │
    ▼
┌─────────┐    SSE stream    ┌──────────────┐
│  React   │◄────────────────│   FastAPI     │
│  SPA     │────────────────►│   Backend     │
└─────────┘   REST + SSE     └──────┬───────┘
                                    │
                              ┌─────▼──────┐
                              │ Pydantic AI │
                              │   Agent     │
                              └─────┬──────┘
                                    │ generates SQL
                              ┌─────▼──────┐
                              │  Virtual    │
                              │ Data Layer  │
                              └──┬──────┬──┘
                                 │      │
                    ┌────────────┘      └────────────┐
                    ▼                                 ▼
             ┌──────────┐                    ┌──────────────┐
             │  DuckDB   │                    │  SQLAlchemy   │
             │ (uploads) │                    │ (live DBs)    │
             └──────────┘                    └──────────────┘
```

**Workspace-based monorepo:** Python backend handles AI orchestration, SQL execution, and data management. TypeScript/React frontend provides the chat interface, SQL editor, and visualizations. They communicate via REST endpoints and SSE streaming.

## API Overview

All endpoints are prefixed with `/api/v1/`.

| Resource | Endpoints | Description |
|----------|-----------|-------------|
| **Datasets** | `GET/POST/DELETE /datasets` | Upload and manage file-based data sources |
| **Connections** | `GET/POST/PUT/DELETE /connections` | Manage live database connections |
| **Schema** | `GET /schema/{source_type}/{source_id}` | Retrieve column-level schema metadata |
| **Conversations** | `GET/POST/DELETE /conversations` | Manage chat conversations |
| **Messages** | `POST /conversations/{id}/messages` | Send messages; SSE stream for AI responses |
| **Queries** | `GET/POST/DELETE /queries` | Save and manage SQL queries |
| **Providers** | `GET/POST/PUT/DELETE /providers` | Configure AI provider API keys and models |
| **Health** | `GET /health` | Service health check |

SSE events during chat: `message_start`, `token`, `sql_generated`, `query_result`, `chart_config`, `message_end`.

## Development

### Backend Commands

```bash
cd apps/backend
uv run pytest                    # Run all tests
uv run pytest tests/test_foo.py  # Run a single test file
uv run pytest -k "test_name"    # Run tests matching a pattern
uv run ruff check .              # Lint
uv run ruff format .             # Format
uv run alembic upgrade head      # Run migrations
uv run alembic revision --autogenerate -m "description"  # Create migration
```

### Frontend Commands

```bash
cd apps/frontend
pnpm test                        # Run tests
pnpm lint                        # Lint
pnpm format                      # Format with Prettier
pnpm build                       # Production build
```

### Monorepo Scripts

```bash
./scripts/dev.sh                 # Start backend + frontend concurrently
./scripts/build.sh               # Build both apps
./scripts/lint.sh                # Lint both apps
./scripts/docs-serve.sh          # Serve documentation site
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Auto-generated in Docker from `POSTGRES_*` vars |
| `DATAX_ENCRYPTION_KEY` | Fernet key for encrypting API keys and passwords | Dev-only key in `.env.example` |
| `POSTGRES_USER` | PostgreSQL username | `datax` |
| `POSTGRES_PASSWORD` | PostgreSQL password | `datax` |
| `POSTGRES_DB` | PostgreSQL database name | `datax` |
| `VITE_API_URL` | Backend URL for frontend | `http://backend:8000` (Docker) |

> Generate a production encryption key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

## Project Structure

```
datax/
├── apps/
│   ├── backend/
│   │   ├── src/
│   │   │   └── app/
│   │   │       ├── api/v1/          # Route handlers (REST + SSE)
│   │   │       ├── models/          # SQLAlchemy ORM models
│   │   │       ├── services/        # Business logic
│   │   │       ├── config.py        # Settings (Pydantic Settings)
│   │   │       ├── database.py      # SQLAlchemy engine/session setup
│   │   │       ├── dependencies.py  # FastAPI dependency injection
│   │   │       └── main.py          # App factory
│   │   ├── alembic/                 # Database migrations
│   │   └── tests/
│   └── frontend/
│       └── src/
│           ├── components/          # UI components (shadcn/ui + custom)
│           ├── pages/               # Route pages
│           ├── hooks/               # Custom React hooks
│           ├── stores/              # Zustand state stores
│           ├── contexts/            # React contexts
│           ├── lib/                 # API client, utilities
│           └── types/               # TypeScript type definitions
├── infra/
│   └── docker/                      # Dockerfiles
├── scripts/                         # Dev utility scripts
├── docs/                            # MkDocs documentation site
├── data/                            # Sample/uploaded data
├── internal/                        # Specs & internal documents
├── docker-compose.yml
├── turbo.json
└── .env.example
```

## License

This project is not yet licensed. All rights reserved.
