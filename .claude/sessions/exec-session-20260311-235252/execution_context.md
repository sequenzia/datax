# Execution Context

## Project Patterns
- Backend: `app/` inside `backend/`, FastAPI factory pattern, Pydantic Settings
- Error responses: `{"error": {"code": "ERROR_CODE", "message": "..."}}`
- Tests: httpx.AsyncClient + ASGITransport, `sqlite://` DATABASE_URL (not postgresql)
- Frontend: pnpm, `@/` = `src/`, shadcn/ui in `src/components/ui/`
- Stores in `src/stores/`, contexts in `src/contexts/`, hooks in `src/hooks/`
- Layout in `src/components/layout/`, pages in `src/pages/`, tests in `__tests__/`
- vitest.config.ts separate from vite.config.ts; jsdom needs localStorage + matchMedia mocks
- ORM models in `backend/app/models/orm.py`, services in `backend/app/services/`
- DB session dependency: `get_db` in `dependencies.py` yields per-request Session
- `create_app()` initializes app.state.db_engine, app.state.session_factory, app.state.duckdb_manager
- API client in `frontend/src/lib/api.ts`, types in `frontend/src/types/api.ts`
- TanStack Query hooks in `frontend/src/hooks/`

## Key Decisions
- FastAPI factory pattern, no module-level app instance
- DuckDB manager on app.state, psycopg[binary] v3.2+ for PostgreSQL
- CodeMirror 6 for SQL editor (lighter than Monaco for SQL-only)
- Zustand per-tab state for SQL editor (results in store, not refs)
- Cursor-based pagination with subquery for cross-database compatibility
- Connection endpoints use in-memory storage pending PostgreSQL session wiring
- Provider env var detection with deterministic UUID5
- Inline FOUC prevention script in index.html for theme

## Known Issues
- Tests must use `sqlite://` DATABASE_URL (postgresql fails without psycopg2)
- Concurrent tasks may modify shared files; use separate modules
- jsdom 28+ needs localStorage + matchMedia mocks in test setup
- Pre-existing lint errors in sql-editor.tsx (ref access during render) - cosmetic only

## File Map
- `backend/app/main.py` - FastAPI factory with CORS, DuckDB, DB engine, ShutdownManager
- `backend/app/config.py` - Pydantic Settings
- `backend/app/database.py` - SQLAlchemy engine/session factory creation
- `backend/app/dependencies.py` - get_db, get_duckdb_manager, get_connection_manager
- `backend/app/encryption.py` - Fernet utilities
- `backend/app/api/v1/` - Router, datasets, connections, conversations, providers endpoints
- `backend/app/models/` - base.py, orm.py, dataset.py, connection.py
- `backend/app/services/` - duckdb_manager.py, connection_manager.py, provider_service.py
- `backend/alembic/` - Migrations
- `frontend/src/App.tsx` - Routes with React.lazy + Suspense
- `frontend/src/components/layout/` - AppLayout, Sidebar, ChatPanel, ResultsCanvas, BottomNavigation
- `frontend/src/components/results/` - ResultsPanel, ResultCard
- `frontend/src/components/sql-editor/` - CodeEditor, TabBar, SqlResultsPanel
- `frontend/src/stores/` - ui-store, results-store, sql-editor-store
- `frontend/src/types/api.ts` - Shared API types
- `frontend/src/lib/api.ts` - API client
- `frontend/src/hooks/` - use-theme, use-breakpoint, use-dashboard-data

## Task History
### Waves 1-3 (14 tasks): All PASS
Setup (#1,#2), DuckDB (#8), layout (#11), encryption (#6), models (#4), health (#50), Docker (#3), Alembic (#5), routing (#12), results panel (#24), data preview (#10), theme (#13), responsive (#49)

### Task [27]: Connection CRUD API - PASS
- ConnectionManager wraps SQLAlchemy engines per-connection with pool_size=2
- In-memory storage pattern pending PostgreSQL session wiring

### Task [21]: Conversation CRUD API - PASS
- Created `backend/app/database.py` for engine/session factory
- All tests now require `sqlite://` DATABASE_URL since create_app() creates DB engine

### Task [14]: AI provider settings API - PASS
- Provider endpoints at `/settings/providers`, env var detection with uuid5
- In-memory store pattern for providers

### Task [41]: SQL editor with CodeMirror 6 - PASS
- Per-tab state in Zustand store (content, cursor, results, execution state)
- CodeMirror mocked in tests (jsdom doesn't support it fully)

### Task [45]: Dashboard overview page - PASS
- TanStack Query hooks with 30s polling, new API client + types modules
