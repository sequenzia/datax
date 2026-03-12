# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DataX is an AI-native data analytics platform — a "chat with your data" app. Users ask questions in natural language, and an agentic AI generates SQL, executes queries, and produces interactive visualizations. It supports uploaded files (CSV, Excel, Parquet, JSON) and live database connections (PostgreSQL, MySQL) through a virtual data layer powered by DuckDB.

The full spec lives at `internal/specs/datax-SPEC.md`. The spec analysis (open findings) is at `internal/specs/datax-SPEC.analysis.md`.

## Architecture

**Two-language monorepo**: Python backend + TypeScript/React frontend, connected via REST + SSE.

### Backend (Python / FastAPI)
- **FastAPI** server with async endpoints and SSE streaming for chat
- **Pydantic AI** agent with multi-provider support (OpenAI, Anthropic, Gemini, OpenAI-compatible)
- **Virtual Data Layer**: routes queries to DuckDB (uploaded files) or SQLAlchemy (live databases)
- **DuckDB**: analytical engine for file-based data — files are registered as virtual tables
- **PostgreSQL**: persistent app state (datasets, connections, conversations, provider configs)
- **SQLAlchemy**: ORM for PostgreSQL app state + proxy for user database connections
- **Fernet encryption**: API keys and database passwords encrypted at rest

### Frontend (TypeScript / Vite + React)
- **Vite + React** SPA (no SSR — backend is FastAPI)
- **shadcn/ui + Tailwind CSS 4+** for components and styling
- **TanStack Query v5+** for server state, **Zustand** for UI state
- **Vercel ai-sdk + Streamdown** for AI streaming and markdown rendering
- **Tambo AI** for conversational UI components
- **react-plotly.js** for interactive charts (AI generates Plotly JSON configs)

### Data Flow
```
User question → FastAPI → Pydantic AI agent → generates SQL
                                             → Virtual Data Layer routes to DuckDB or SQLAlchemy
                                             → results + AI-generated Plotly chart config
                                             → SSE stream back to React frontend
```

### Key Data Entities
- **Dataset**: uploaded file metadata + DuckDB virtual table name
- **Connection**: external database credentials (password Fernet-encrypted)
- **SchemaMetadata**: column-level schema for both datasets and connections (polymorphic via `source_id` + `source_type`)
- **Conversation / Message**: chat history with JSONB metadata (SQL, chart configs)
- **SavedQuery**: user-saved SQL queries
- **ProviderConfig**: AI provider API keys (encrypted) and model selection

All entities include a nullable `user_id` field for future multi-user support (NULL in single-user MVP).

## Build & Development Commands

### Python Backend
```bash
cd backend
uv sync                          # Install dependencies
uv run fastapi dev               # Dev server with hot reload
uv run pytest                    # Run all tests
uv run pytest tests/test_foo.py  # Run single test file
uv run pytest -k "test_name"     # Run single test by name
uv run ruff check .              # Lint
uv run ruff format .             # Format
uv run alembic upgrade head      # Run database migrations
uv run alembic revision --autogenerate -m "description"  # Create migration
```

### Frontend
```bash
cd frontend
pnpm install                     # Install dependencies
pnpm dev                         # Dev server (Vite)
pnpm build                       # Production build
pnpm lint                        # Lint
pnpm test                        # Run tests
```

### Docker
```bash
docker compose up                # Full stack (backend + frontend + PostgreSQL)
docker compose up -d             # Detached mode
```

## API Design Conventions

- All endpoints prefixed with `/api/v1/`
- REST resource pattern: `POST` to create, `GET` to list/read, `PUT` to update, `DELETE` to remove
- Chat streaming uses SSE via `POST /api/v1/conversations/{id}/messages` with `Accept: text/event-stream`
- SSE events: `message_start`, `token`, `sql_generated`, `query_result`, `chart_config`, `message_end`
- Error responses use `{ "error": { "code": "ERROR_CODE", "message": "..." } }` format
- Passwords/API keys are never returned in API responses

## Key Design Decisions

- **DuckDB is per-process**: file queries run in-process DuckDB, so scaling requires session affinity or shared storage
- **Agentic retry loop**: AI agent self-corrects failed SQL queries (up to 3 retries) before asking the user to refine
- **Read-only by default**: connected databases are queried in read-only mode with execution time limits
- **SchemaMetadata is polymorphic**: `source_type` (dataset/connection) + `source_id` pattern — no separate tables for dataset vs connection schemas
- **Chart type selection**: AI chooses chart type based on query result shape heuristics, generates Plotly JSON config
- **Cross-source queries**: Virtual Data Layer can orchestrate queries spanning both DuckDB and live databases

## Implementation Patterns

### Backend
- **App factory**: `create_app(settings=None)` in `app/main.py` — no module-level app instance; use `uv run uvicorn app.main:create_app --factory`
- **App state**: DuckDB manager, DB engine, session factory, connection manager, settings all attached to `app.state`
- **Dependencies**: `backend/app/dependencies.py` provides `get_db`, `get_duckdb_manager`, `get_connection_manager`, `get_settings`, etc.
- **Database**: `backend/app/database.py` for SQLAlchemy engine/session factory creation; psycopg[binary] v3.2+ driver
- **Services**: business logic in `backend/app/services/` (duckdb_manager, connection_manager, provider_service, query_service, nl_query_service, agent_service, schema_context, schema_introspection, chart_heuristics, chart_config, cross_source_query, file_upload)
- **Tests**: use `sqlite://` DATABASE_URL (not postgresql), httpx.AsyncClient + ASGITransport
- **JSONB columns**: `JSON().with_variant(JSONB, "postgresql")` for SQLite test compatibility
- **Boolean defaults**: `sa_true()`/`sa_false()` for cross-database `server_default`

### Frontend
- **Vite 7 + React 19 + TypeScript 5.9** with strict mode
- **Tailwind CSS 4** via @tailwindcss/vite plugin (no PostCSS config)
- **shadcn/ui v4**: components in `src/components/ui/`, components.json created manually
- **CodeMirror 6** for SQL editor (lighter than Monaco for SQL-only use case)
- **Streamdown** for streaming markdown rendering in chat
- **react-plotly.js** for interactive chart rendering
- **Path alias**: `@/` maps to `src/` in both tsconfig.json and vite.config.ts
- **File organization**: contexts in `src/contexts/`, hooks in `src/hooks/`, stores in `src/stores/`, types in `src/types/`, API client in `src/lib/api.ts`
- **Testing**: vitest v4 with jsdom, separate vitest.config.ts (avoids tailwind plugin in test env); jsdom 28+ requires localStorage + matchMedia mocks
- **Responsive**: three layout modes (mobile < 768px, tablet 768-1279px, desktop 1280px+) via `useBreakpoint()` hook
