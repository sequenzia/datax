<!-- docs/configuration.md -->
# Configuration

DataX is configured entirely through environment variables, loaded via
[Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).
This page documents every variable, how they're resolved, and how the
settings flow through the application at runtime.

## Environment Variables

### Required

These **must** be set before DataX will start.

| Variable | Type | Description |
|---|---|---|
| `DATABASE_URL` | `str` | PostgreSQL connection string (see [DATABASE_URL format](#database_url-format) below) |
| `DATAX_ENCRYPTION_KEY` | `str` | Fernet master key for encrypting API keys and database passwords at rest |

### Backend — Optional

| Variable | Type | Default | Description |
|---|---|---|---|
| `DATAX_STORAGE_PATH` | `Path` | `./data/uploads` | Directory for uploaded file storage |
| `DATAX_MAX_QUERY_TIMEOUT` | `int` | `30` | Maximum SQL query execution time in seconds |
| `DATAX_MAX_RETRIES` | `int` | `3` | Maximum AI agent retry attempts for failed SQL generation |
| `DATAX_MAX_CROSS_SOURCE_ROWS` | `int` | `100000` | Maximum rows per sub-query in cross-source queries (memory guard) |
| `CORS_ORIGINS` | `str` | `http://localhost:5173` | Comma-separated list of allowed CORS origins |

### AI Provider API Keys

Set these to configure AI providers via environment variables instead of (or in
addition to) the UI. See [Provider priority](#provider-priority) for how these
interact with UI-configured providers.

| Variable | Type | Default | Description |
|---|---|---|---|
| `DATAX_OPENAI_API_KEY` | `str` | *unset* | OpenAI API key — overrides any UI-configured OpenAI provider |
| `DATAX_ANTHROPIC_API_KEY` | `str` | *unset* | Anthropic API key — overrides any UI-configured Anthropic provider |
| `DATAX_GEMINI_API_KEY` | `str` | *unset* | Google Gemini API key — overrides any UI-configured Gemini provider |

### Frontend

| Variable | Type | Default | Description |
|---|---|---|---|
| `VITE_API_URL` | `str` | `http://localhost:8000` | Backend API base URL — used by Vite's dev server proxy |

!!! note "Vite proxy, not runtime fetch"
    `VITE_API_URL` configures the **Vite dev server proxy** in `vite.config.ts`.
    All frontend `/api` requests are proxied to this URL during development.
    In production Docker builds, the frontend container sets this to
    `http://backend:8000` so requests route to the backend service.

### Docker Compose

These variables are only used by `docker-compose.yml` for the PostgreSQL
service. The backend's `DATABASE_URL` is auto-generated from them when running
via Docker Compose.

| Variable | Type | Default | Description |
|---|---|---|---|
| `POSTGRES_USER` | `str` | `datax` | PostgreSQL user |
| `POSTGRES_PASSWORD` | `str` | `datax` | PostgreSQL password |
| `POSTGRES_DB` | `str` | `datax` | PostgreSQL database name |

---

## Environment File Loading

!!! info "Search order"
    Pydantic Settings loads `.env` files in the following order, relative to the
    `apps/backend/` directory. **Later files override earlier ones.**

    1. `../.env` — project root
    2. `../.env.local` — project root local overrides
    3. `.env` — backend directory
    4. `.env.local` — backend directory local overrides

This means you can keep shared variables (like `DATABASE_URL`) in the project
root `.env` and backend-specific overrides in `apps/backend/.env.local`.

!!! warning "Never commit `.env` files"
    Add `.env` and `.env.local` to your `.gitignore`. These files contain
    secrets (database passwords, API keys, encryption keys) that must not be
    checked into version control. Use `.env.example` as a reference template.

---

## DATABASE_URL Format

DataX uses **psycopg v3** (not the legacy psycopg2) as the PostgreSQL driver.
The `create_db_engine()` function in `apps/backend/src/app/database.py` automatically
rewrites the URL scheme:

```
postgresql://user:pass@host:5432/db
       ↓ auto-rewrite
postgresql+psycopg://user:pass@host:5432/db
```

This means you can use the standard `postgresql://` scheme in your environment —
SQLAlchemy will receive the psycopg-qualified URL automatically.

!!! tip
    If you're using a hosted provider like Neon, their connection strings use
    `postgresql://` by default — this works out of the box with DataX.

---

## Encryption Key

The `DATAX_ENCRYPTION_KEY` is a [Fernet](https://cryptography.io/en/latest/fernet/)
symmetric key used to encrypt sensitive data at rest:

- AI provider API keys
- External database connection passwords

Generate a production key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

!!! danger "Keep your encryption key safe"
    - **Losing the key** means all encrypted data (API keys, database passwords)
      becomes unrecoverable. Back it up securely.
    - **Rotating the key** requires re-encrypting all stored secrets — there is
      no built-in rotation mechanism yet.
    - The `.env.example` ships with a `dev-only` key for local development.
      **Never use this key in production.**

For more details on the encryption implementation, see the
[Security](security.md) page.

---

## Provider Priority

DataX supports two ways to configure AI providers: environment variables and the
web UI. When both exist for the same provider, specific precedence rules apply.

### How it works

```mermaid
flowchart TD
    A[Provider requested] --> B{Env var set?}
    B -->|Yes| C[Use env-var provider]
    B -->|No| D{UI provider exists?}
    D -->|Yes| E[Use UI-configured provider]
    D -->|No| F[No provider available]
```

**Environment-variable providers:**

- Are detected at runtime by checking `DATAX_OPENAI_API_KEY`,
  `DATAX_ANTHROPIC_API_KEY`, and `DATAX_GEMINI_API_KEY`
- Receive deterministic UUIDs via `uuid5(NAMESPACE_DNS, "env-{provider_name}")`
  so their IDs are stable across restarts
- Appear in the provider list with `source: "env_var"`
- **Cannot be deleted** via the API — attempting to do so returns HTTP 409. Remove
  the environment variable to unconfigure them
- Use default model names: `gpt-4o` (OpenAI), `claude-sonnet-4-20250514`
  (Anthropic), `gemini-2.0-flash` (Gemini)

**UI-configured providers:**

- Created through the `/api/v1/providers` endpoint
- API keys are Fernet-encrypted before storage
- Appear with `source: "ui"` and can be freely updated or deleted

Both env-var and UI providers appear side-by-side in the provider list, so the
UI can show which source each provider came from.

---

## Settings Flow

Understanding how settings propagate through the application helps when
debugging configuration issues.

```mermaid
sequenceDiagram
    participant Env as Environment / .env files
    participant S as Settings (Pydantic)
    participant App as FastAPI app
    participant Dep as Dependencies
    participant Handler as Request handlers

    Env->>S: Pydantic Settings reads env vars
    S->>App: create_app(settings) attaches to app.state.settings
    App->>App: Engine, session factory, managers created from settings
    Handler->>Dep: Request arrives → get_settings(request)
    Dep->>App: Reads request.app.state.settings
    Dep-->>Handler: Returns Settings instance
```

1. **Startup** — `create_app()` in `apps/backend/src/app/main.py` instantiates `Settings()`
   from the environment (or accepts explicit settings for testing)
2. **Attachment** — The settings instance is stored on `app.state.settings`, along
   with the database engine, session factory, DuckDB manager, and connection
   manager — all derived from those settings
3. **Request time** — FastAPI dependencies (`get_settings`, `get_db`,
   `get_duckdb_manager`, etc.) read from `app.state` via the `Request` object
4. **Single instance** — The same `Settings` object created at startup is reused
   for every request (no re-parsing of environment variables)

---

## Complete `.env.example`

Below is a complete reference of all supported variables. Copy this to `.env`
and fill in the values for your environment.

```bash title=".env.example"
# ──────────────────────────────────────────────
# PostgreSQL — choose ONE option
# ──────────────────────────────────────────────

# Option A: Hosted (e.g., Neon)
# DATABASE_URL=postgresql://<user>:<password>@<host>/<dbname>?sslmode=require

# Option B: Local Docker (start with: docker compose --profile local-db up)
# POSTGRES_USER=datax
# POSTGRES_PASSWORD=datax
# POSTGRES_DB=datax
# DATABASE_URL is auto-generated from POSTGRES_* vars in docker-compose.yml

# ──────────────────────────────────────────────
# Encryption
# ──────────────────────────────────────────────

# Generate a real key for production:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
DATAX_ENCRYPTION_KEY=dev-only_ulHPfBdOTM5i8oPZdpi9S0X-di0ON2QNlMSK1J0LN8Y=

# ──────────────────────────────────────────────
# Backend (optional)
# ──────────────────────────────────────────────

# DATAX_STORAGE_PATH=./data/uploads
# DATAX_MAX_QUERY_TIMEOUT=30
# DATAX_MAX_RETRIES=3
# DATAX_MAX_CROSS_SOURCE_ROWS=100000
# CORS_ORIGINS=http://localhost:5173

# ──────────────────────────────────────────────
# AI Providers (optional — can also configure via UI)
# ──────────────────────────────────────────────

# DATAX_OPENAI_API_KEY=sk-...
# DATAX_ANTHROPIC_API_KEY=sk-ant-...
# DATAX_GEMINI_API_KEY=AI...

# ──────────────────────────────────────────────
# Frontend
# ──────────────────────────────────────────────

# VITE_API_URL=http://localhost:8000
```

---

## Related Pages

- [Security](security.md) — encryption implementation, API key storage, and
  read-only query enforcement
- [Deployment](deployment.md) — Docker Compose setup, production configuration,
  and scaling considerations
