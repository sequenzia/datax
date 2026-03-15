# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DataX is an AI-native data analytics platform — a "chat with your data" app. Users ask questions in natural language, and an agentic AI generates SQL, executes queries, and produces interactive visualizations. It supports uploaded files (CSV, Excel, Parquet, JSON) and live database connections (PostgreSQL, MySQL) through a virtual data layer powered by DuckDB.

The full spec lives at `internal/specs/datax-SPEC.md`. The spec analysis (open findings) is at `internal/specs/datax-SPEC.analysis.md`.

## Architecture

**Workspace-based monorepo**: Python backend + TypeScript/React frontend in `apps/`, shared packages in `packages/`, infrastructure in `infra/`. Connected via REST + AG-UI (CopilotKit).

### Backend (Python / FastAPI)
- **FastAPI** server with async endpoints and AG-UI streaming for chat
- **Pydantic AI** agent with 9 tools and multi-provider support (OpenAI, Anthropic, Gemini, OpenAI-compatible)
- **AG-UI endpoint** at `/api/agent` — ASGI app mounted via `agent.to_ag_ui()`
- **Virtual Data Layer**: routes queries to DuckDB (uploaded files) or SQLAlchemy (live databases)
- **DuckDB**: analytical engine for file-based data — persistent file-backed storage with httpfs extension
- **PostgreSQL**: persistent app state (datasets, connections, conversations, provider configs)
- **SQLAlchemy**: ORM for PostgreSQL app state + proxy for user database connections
- **Fernet encryption**: API keys and database passwords encrypted at rest

### Frontend (TypeScript / Vite + React)
- **Vite + React** SPA (no SSR — backend is FastAPI)
- **shadcn/ui + Tailwind CSS 4+** for components and styling
- **TanStack Query v5+** for server state, **Zustand** for UI state
- **CopilotKit** (`@copilotkit/react-core`) for AI chat integration via AG-UI protocol
- **react-plotly.js** for interactive charts (16 chart types, AI generates Plotly JSON configs)
- **TanStack Table v8 + @tanstack/react-virtual** for DataTable with virtual scrolling

### Data Flow
```
User question → CopilotKit → AG-UI → Pydantic AI agent → tool calls (run_query, render_chart, etc.)
                                                        → Virtual Data Layer routes to DuckDB or SQLAlchemy
                                                        → results + AI-generated Plotly chart config
                                                        → AG-UI stream back to CopilotKit → generative UI components
```

### Key Data Entities
- **Dataset**: uploaded file metadata + DuckDB virtual table name + data_stats (JSONB)
- **Connection**: external database credentials (password Fernet-encrypted)
- **SchemaMetadata**: column-level schema for both datasets and connections (polymorphic via `source_id` + `source_type`)
- **Conversation / Message**: chat history with structured columns (sql, chart_config, query_result_summary)
- **Bookmark**: saved query results with SQL, chart config, and result snapshot
- **Dashboard / DashboardItem**: pinnable grids of bookmarks
- **DataProfile**: SUMMARIZE statistics and sample values per dataset
- **ProviderConfig**: AI provider API keys (encrypted) and model selection

All entities include a nullable `user_id` field for future multi-user support (NULL in single-user MVP).

## Build & Development Commands

### Python Backend
```bash
cd apps/backend
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
cd apps/frontend
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

### Monorepo Scripts
```bash
./scripts/dev.sh                 # Start backend + frontend concurrently
./scripts/build.sh               # Build both apps
./scripts/lint.sh                # Lint both apps
./scripts/docs-serve.sh          # Serve docs site locally
```

## API Design Conventions

- All endpoints prefixed with `/api/v1/`
- REST resource pattern: `POST` to create, `GET` to list/read, `PUT` to update, `DELETE` to remove
- Chat streaming uses AG-UI protocol via CopilotKit at `/api/agent`
- Additional REST endpoints: `/api/v1/bookmarks`, `/api/v1/dashboards`, `/api/v1/queries/paginate`, `/api/v1/datasets/{id}/profile`
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
- **App factory**: `create_app(settings=None)` in `apps/backend/src/app/main.py` — no module-level app instance; use `uv run uvicorn app.main:create_app --factory`
- **App state**: DuckDB manager, DB engine, session factory, connection manager, settings all attached to `app.state`
- **Dependencies**: `apps/backend/src/app/dependencies.py` provides `get_db`, `get_duckdb_manager`, `get_connection_manager`, `get_settings`, etc.
- **Database**: `apps/backend/src/app/database.py` for SQLAlchemy engine/session factory creation; psycopg[binary] v3.2+ driver
- **Services**: business logic in `apps/backend/src/app/services/` (agent_tools, agent_service, duckdb_manager, connection_manager, provider_service, query_service, bookmark_service, dashboard_service, schema_context, conversation_context, chart_heuristics, chart_config)
- **AG-UI**: `apps/backend/src/app/agui.py` — ASGI app factory with CORS and error handling
- **Agent tools**: 9 tools in `agent_tools.py` (run_query, get_schema, summarize_table, render_chart, render_table, render_data_profile, suggest_followups, create_bookmark, search_bookmarks)
- **Tests**: use `sqlite://` DATABASE_URL (not postgresql), httpx.AsyncClient + ASGITransport
- **JSONB columns**: `JSON().with_variant(JSONB, "postgresql")` for SQLite test compatibility
- **Boolean defaults**: `sa_true()`/`sa_false()` for cross-database `server_default`

### Frontend
- **Vite 7 + React 19 + TypeScript 5.9** with strict mode
- **Tailwind CSS 4** via @tailwindcss/vite plugin (no PostCSS config)
- **shadcn/ui v4**: components in `src/components/ui/`, components.json created manually
- **CodeMirror 6** for SQL editor (lighter than Monaco for SQL-only use case)
- **CopilotKit**: `@copilotkit/react-core` for AG-UI integration; actions registered via CopilotActionsRegistrar pattern
- **Generative UI**: components in `src/components/generative-ui/` (InteractiveChart, DataTable, DataProfile, SQLApproval, QueryProgress, FollowUpSuggestions, ChartEditor, DataExplorer, BookmarkCard)
- **react-plotly.js** for interactive chart rendering (16 chart types, WebGL for large datasets)
- **TanStack Table v8 + @tanstack/react-virtual** for DataTable with virtual scrolling
- **Path alias**: `@/` maps to `src/` in both tsconfig.json and vite.config.ts
- **File organization**: contexts in `src/contexts/`, hooks in `src/hooks/`, stores in `src/stores/`, providers in `src/providers/`, types in `src/types/`, API client in `src/lib/api.ts`
- **Testing**: vitest v4 with jsdom, separate vitest.config.ts (avoids tailwind plugin in test env); jsdom 28+ requires localStorage + matchMedia mocks
- **Responsive**: three layout modes (mobile < 768px, tablet 768-1279px, desktop 1280px+) via `useBreakpoint()` hook
