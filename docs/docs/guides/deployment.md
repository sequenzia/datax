<!-- docs/deployment.md -->
# Deployment

This guide covers running DataX in development with Docker Compose,
preparing for production deployments, and the operational concerns
you should be aware of at each stage.

## Docker Compose Architecture

DataX ships a three-service Docker Compose stack connected by a `datax`
bridge network. The stack is optimized for **local development** with
hot-reload, bind mounts, and dev-mode servers.

```mermaid
graph LR
    subgraph "Docker Compose — datax network"
        direction LR
        FE["<b>frontend</b><br/>node:22-slim<br/>Vite HMR :5173"]
        BE["<b>backend</b><br/>python:3.12-slim<br/>Uvicorn :8000"]
        PG["<b>postgres</b><br/>postgres:16<br/>:5432<br/><i>profile: local-db</i>"]
    end

    User["Browser"] -->|":5173"| FE
    FE -->|"VITE_API_URL"| BE
    BE -->|"DATABASE_URL"| PG
    BE --- DuckDB["DuckDB<br/><i>in-process</i>"]

    style User fill:#e3f2fd,stroke:#1565c0,color:#000
    style FE fill:#fff3e0,stroke:#e65100,color:#000
    style BE fill:#e8f5e9,stroke:#2e7d32,color:#000
    style PG fill:#fce4ec,stroke:#c62828,color:#000
    style DuckDB fill:#f3e5f5,stroke:#6a1b9a,color:#000
```

## Development Setup

### Quick Start

The fastest way to get DataX running locally:

```bash title="Terminal"
# 1. Start PostgreSQL + backend + frontend
docker compose --profile local-db up

# 2. Run database migrations (in a second terminal)
cd apps/backend && uv run alembic upgrade head
```

The application will be available at:

- **Frontend:** [http://localhost:5173](http://localhost:5173)
- **Backend API:** [http://localhost:8000](http://localhost:8000)
- **PostgreSQL:** `localhost:5432` (user: `datax`, password: `datax`)

### The `local-db` Profile

The PostgreSQL service uses a Docker Compose
[profile](https://docs.docker.com/compose/profiles/), meaning it only
starts when explicitly requested:

=== "With local PostgreSQL"

    ```bash
    # Starts all three services including postgres
    docker compose --profile local-db up
    ```

=== "With external PostgreSQL"

    ```bash
    # Starts only backend + frontend
    # Set DATABASE_URL to point to your external database
    DATABASE_URL=postgresql://user:pass@your-host:5432/datax \
      docker compose up
    ```

!!! tip "When to skip the local database"
    If you already have a PostgreSQL 16+ instance running — for example,
    a shared team database or a managed cloud instance — skip the
    `local-db` profile and set `DATABASE_URL` directly.

### Service Details

#### Backend

| Property | Value |
|---|---|
| **Base image** | `python:3.12-slim` |
| **Package manager** | `uv` (copied from `ghcr.io/astral-sh/uv:latest`) |
| **Port** | `8000` |
| **Command** | `uv run uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --reload` |
| **Volumes** | `./apps/backend:/app` (bind mount for hot reload), `backend_venv` (cached `.venv`) |

#### Frontend

| Property | Value |
|---|---|
| **Base image** | `node:22-slim` |
| **Package manager** | `pnpm` (via corepack) |
| **Port** | `5173` |
| **Command** | `pnpm dev --host 0.0.0.0 --port 5173` |
| **Volumes** | `./apps/frontend:/app` (bind mount for HMR), `frontend_node_modules` (cached `node_modules`) |

#### PostgreSQL

| Property | Value |
|---|---|
| **Image** | `postgres:16` |
| **Port** | `5432` |
| **Profile** | `local-db` (opt-in) |
| **Volume** | `postgres_data` (persistent data) |
| **Healthcheck** | `pg_isready` every 5s, 5 retries, 10s start period |

### Environment Variables

The Compose file provides defaults suitable for development:

```yaml title="docker-compose.yml (excerpt)"
backend:
  environment:
    DATABASE_URL: postgresql://datax:datax@postgres:5432/datax
    DATAX_ENCRYPTION_KEY: dev-only_ulHPfBdOTM5i8oPZdpi9S0X-di0ON2QNlMSK1J0LN8Y=
```

!!! danger "Never use the default encryption key outside development"
    The `DATAX_ENCRYPTION_KEY` default is embedded in `docker-compose.yml`
    and is public. Any deployment beyond local development **must** generate
    a unique Fernet key. See [Configuration — Encryption Key](../getting-started/configuration.md#encryption-key)
    for generation instructions.

For the full list of environment variables — including AI provider keys,
storage paths, and query tuning — see the
[Configuration](../getting-started/configuration.md) reference.

## Database Migrations

DataX uses [Alembic](https://alembic.sqlalchemy.org/) to manage the
PostgreSQL schema. Migrations must be run before first use and after
pulling changes that include new migration files.

### Running Migrations

```bash title="Apply all pending migrations"
cd apps/backend
uv run alembic upgrade head
```

### Creating New Migrations

```bash title="Auto-generate from model changes"
cd apps/backend
uv run alembic revision --autogenerate -m "add user preferences table"
```

!!! note "Review auto-generated migrations"
    Always inspect the generated migration file before applying it.
    Alembic's autogenerate can miss certain changes (renamed columns,
    data migrations) and may produce incorrect downgrades.

### Migration Tips

- **Inside Docker:** Run migrations from the backend container:
  ```bash
  docker compose exec backend uv run alembic upgrade head
  ```
- **CI/CD:** Run migrations as a one-off init container or pre-deploy
  step, not as part of the application startup.
- **Rollback:** `uv run alembic downgrade -1` reverts the last migration.

## Health Checks

DataX exposes two probe endpoints at the application root (not under
`/api/v1/`) for use with container orchestrators:

### `GET /health` — Liveness Probe

Returns `200 OK` if the FastAPI process is running. No dependency checks.

```json
{ "status": "ok" }
```

### `GET /ready` — Readiness Probe

Checks PostgreSQL connectivity (`SELECT 1`) and DuckDB availability.
Returns `200` when all dependencies are reachable, `503` otherwise.

=== "Healthy"

    ```json
    {
      "status": "ready",
      "checks": {
        "postgresql": "ok",
        "duckdb": "ok"
      }
    }
    ```

=== "Unhealthy"

    ```json
    {
      "status": "unavailable",
      "checks": {
        "postgresql": "error: connection refused",
        "duckdb": "ok"
      }
    }
    ```

### Kubernetes / Docker Example

```yaml title="Kubernetes probe configuration"
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 5
  failureThreshold: 3
```

## Persistent Storage

Two categories of data require persistent volumes in any deployment:

### PostgreSQL Data

The `postgres_data` Docker volume stores all application state — datasets,
connections, conversations, saved queries, and provider configurations.

!!! warning "Back up PostgreSQL regularly"
    Losing the PostgreSQL volume means losing all application data.
    Use `pg_dump` for backups in production environments.

### Uploaded Files

Uploaded files (CSV, Excel, Parquet, JSON) are stored at the path
configured by `DATAX_STORAGE_PATH` (default: `./data/uploads`).

- In development, the bind mount (`./apps/backend:/app`) makes uploads
  available on the host filesystem.
- In production, this path must be backed by a persistent volume or
  object storage.

!!! warning "DuckDB virtual tables depend on uploaded files"
    DuckDB registers uploaded files as virtual tables. If an uploaded
    file is deleted or moved, the corresponding virtual table becomes
    inaccessible. Ensure the storage path is durable and consistent.

## Production Considerations

The current Docker setup is designed for **development only**. Several
changes are required before deploying to production.

### What's Not Production-Ready

!!! danger "Development-only Dockerfiles"
    Both Dockerfiles run dev servers with hot-reload enabled:

    - **Backend:** `uvicorn ... --reload` reloads on every file change
    - **Frontend:** `pnpm dev` runs the Vite development server

    Production deployments need multi-stage builds with optimized images
    and production-grade servers.

#### Backend — Production Changes Needed

| Area | Current (Dev) | Production Target |
|---|---|---|
| **Server** | `uvicorn --reload` | `uvicorn` or `gunicorn` with `uvicorn.workers.UvicornWorker`, no `--reload` |
| **Workers** | 1 (single-process) | Multiple workers (but see [scaling considerations](#scaling-considerations)) |
| **Dockerfile** | Single stage, full image | Multi-stage with slim runtime image |
| **Dependencies** | `uv sync --frozen --no-dev` | Same (already excludes dev deps in Docker) |

#### Frontend — Production Changes Needed

| Area | Current (Dev) | Production Target |
|---|---|---|
| **Server** | `pnpm dev` (Vite HMR) | `pnpm build` → static files served by nginx or CDN |
| **Dockerfile** | Single stage with Node runtime | Multi-stage: build stage + nginx/alpine for serving |
| **Assets** | Unbundled, on-the-fly transforms | Pre-built, minified, hashed static assets |

### Security Gaps

!!! danger "No authentication"
    DataX currently has no authentication or authorization middleware.
    It is designed as a **single-user application**. Do not expose it to
    the public internet without adding an authentication layer (reverse
    proxy with auth, OAuth2, etc.).

- **Encryption key:** The default `DATAX_ENCRYPTION_KEY` is public. Generate a real Fernet key for any non-local deployment. See [Configuration](../getting-started/configuration.md).
- **CORS:** The default `CORS_ORIGINS` allows `http://localhost:5173`. Update this to match your production domain.
- **Database credentials:** The default PostgreSQL user/password (`datax`/`datax`) must be changed.

## Scaling Considerations

### DuckDB Is Per-Process

DuckDB runs in-process — each backend worker gets its own isolated
DuckDB instance. This has important implications:

```mermaid
graph TB
    LB["Load Balancer"] --> W1["Worker 1<br/>DuckDB instance A"]
    LB --> W2["Worker 2<br/>DuckDB instance B"]
    LB --> W3["Worker 3<br/>DuckDB instance C"]

    W1 --- note1["Each worker has its own<br/>registered virtual tables"]

    style LB fill:#e3f2fd,stroke:#1565c0,color:#000
    style W1 fill:#e8f5e9,stroke:#2e7d32,color:#000
    style W2 fill:#e8f5e9,stroke:#2e7d32,color:#000
    style W3 fill:#e8f5e9,stroke:#2e7d32,color:#000
    style note1 fill:#fff9c4,stroke:#f9a825,color:#000
```

- **Uploaded files** are registered as DuckDB virtual tables at
  upload time. Other workers won't have these registrations.
- **Session affinity** (sticky sessions) is required if running multiple
  workers, so each user's requests always hit the same DuckDB instance.
- Alternatively, a shared DuckDB storage layer or re-registration
  strategy can synchronize state across workers.

!!! info "Single-worker is fine for most use cases"
    DuckDB is exceptionally fast for analytical queries. A single
    worker can handle significant throughput for the query workloads
    DataX targets. Scale vertically (bigger instance) before adding
    workers.

### Horizontal Scaling Strategy

If you need multiple backend instances:

1. **Session affinity** at the load balancer (e.g., cookie-based sticky sessions)
2. **Shared file storage** (NFS, EFS, or object storage) for uploaded files
3. **Re-register virtual tables** on worker startup by scanning the uploads directory

## Production Readiness Checklist

Use this checklist before deploying DataX outside a local development
environment:

- [ ] **Encryption key** — Generate a unique `DATAX_ENCRYPTION_KEY` ([how-to](../getting-started/configuration.md#encryption-key))
- [ ] **Database credentials** — Use strong PostgreSQL credentials, not the defaults
- [ ] **Multi-stage Dockerfiles** — Build production images without dev dependencies or hot-reload
- [ ] **Frontend static build** — Serve `pnpm build` output via nginx or CDN, not `pnpm dev`
- [ ] **Backend production server** — Run `uvicorn` without `--reload`, optionally behind `gunicorn`
- [ ] **CORS origins** — Set `CORS_ORIGINS` to your actual frontend domain
- [ ] **Authentication** — Add an authentication layer before exposing to users
- [ ] **Persistent storage** — Mount durable volumes for PostgreSQL data and uploaded files
- [ ] **Backups** — Set up `pg_dump` or equivalent for PostgreSQL
- [ ] **TLS termination** — Add HTTPS via reverse proxy (nginx, Caddy, cloud LB)
- [ ] **Health checks** — Configure `/health` and `/ready` probes in your orchestrator
- [ ] **Logging** — Route structured logs (JSON) to your observability stack
- [ ] **Secrets management** — Use a secrets manager for API keys and database passwords, not environment variable files
- [ ] **Resource limits** — Set CPU/memory limits for containers
