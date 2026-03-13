<!-- docs/getting-started.md -->
# Getting Started

Get DataX running locally in under five minutes. This guide covers prerequisites, environment setup, and launching the platform — with both Docker and manual options.

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| **Python** | 3.12+ | Backend runtime |
| **Node.js** | 22+ | Frontend build tooling |
| **pnpm** | Latest | Frontend package manager |
| **uv** | Latest | Python package manager |
| **PostgreSQL** | 16 | App state database (or use Docker Compose) |
| **Docker** | Latest | Optional — for containerized setup |

!!! tip "Don't have `uv` or `pnpm`?"
    Install both with Homebrew (macOS) or their official installers:

    ```bash
    # macOS
    brew install uv pnpm

    # Or use the official install scripts
    curl -LsSf https://astral.sh/uv/install.sh | sh
    curl -fsSL https://get.pnpm.io/install.sh | sh
    ```

## Environment Setup

DataX requires two environment variables and optionally accepts AI provider keys.

### 1. Create your env file

Copy the example and fill in your values:

```bash
cp .env.example .env.local
```

### 2. Configure required variables

Open `.env.local` and set the following:

```bash title=".env.local"
# PostgreSQL connection string
DATABASE_URL=postgresql://datax:datax@localhost:5432/datax

# Fernet encryption key — protects API keys and passwords at rest
DATAX_ENCRYPTION_KEY=<your-generated-key>
```

!!! warning "Generate a real encryption key"
    The `.env.example` ships with a dev-only placeholder key. Generate a proper Fernet key for any non-trivial use:

    ```bash
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ```

    Copy the output into `DATAX_ENCRYPTION_KEY`.

### 3. Add an AI provider key (optional at startup)

You need at least one AI provider configured to chat with your data. You can set these via environment variables now, or configure them later through the Settings UI.

```bash title=".env.local (append)"
# Set at least one — env vars override UI-configured keys
DATAX_OPENAI_API_KEY=sk-...
DATAX_ANTHROPIC_API_KEY=sk-ant-...
DATAX_GEMINI_API_KEY=AIza...
```

!!! info "Env file search order"
    The backend loads environment files in this order (later files override earlier ones):

    1. `../.env` (project root)
    2. `../.env.local` (project root, gitignored)
    3. `.env` (backend directory)
    4. `.env.local` (backend directory, gitignored)

    Place your secrets in `.env.local` at the project root — it's gitignored and takes priority.

## Launch DataX

Choose the setup path that fits your workflow:

=== "Docker Compose (Recommended)"

    The fastest way to get everything running. Docker Compose orchestrates the backend, frontend, and optionally PostgreSQL.

    **With local PostgreSQL (all-in-one):**

    ```bash
    docker compose --profile local-db up
    ```

    This starts three containers:

    | Service | Port | Description |
    |---|---|---|
    | `postgres` | 5432 | PostgreSQL 16 database |
    | `backend` | 8000 | FastAPI server |
    | `frontend` | 5173 | Vite dev server |

    !!! note "Using an external database?"
        If you already have a PostgreSQL instance (e.g., Neon, Supabase, or a local install), skip the `--profile local-db` flag and set `DATABASE_URL` in your `.env.local`:

        ```bash
        docker compose up
        ```

    **Run in the background:**

    ```bash
    docker compose --profile local-db up -d
    ```

    **View logs:**

    ```bash
    docker compose logs -f backend   # Backend logs only
    docker compose logs -f            # All services
    ```

    **Stop everything:**

    ```bash
    docker compose down
    ```

=== "Local Development"

    Run each service directly on your machine for full hot-reload and debugging access.

    ### Start PostgreSQL

    If you don't have PostgreSQL running locally, use Docker for just the database:

    ```bash
    docker compose --profile local-db up postgres -d
    ```

    Or use any PostgreSQL 16 instance and set `DATABASE_URL` accordingly.

    ### Start the backend

    ```bash
    cd apps/backend
    uv sync                      # Install Python dependencies
    uv run alembic upgrade head  # Run database migrations
    uv run fastapi dev           # Start dev server on port 8000
    ```

    !!! tip "First time running?"
        `uv sync` creates a virtual environment and installs all dependencies automatically. You don't need to manually create a venv.

    ### Start the frontend

    Open a second terminal:

    ```bash
    cd apps/frontend
    pnpm install                 # Install Node dependencies
    pnpm dev                     # Start Vite dev server on port 5173
    ```

## Verify the Setup

Once both services are running, open your browser to:

**[:material-open-in-new: http://localhost:5173](http://localhost:5173)**

You should see the DataX onboarding wizard.

!!! success "Health check"
    Confirm the backend is reachable by visiting [http://localhost:8000/docs](http://localhost:8000/docs) — this opens the FastAPI interactive API documentation.

## First Steps in DataX

### 1. Complete the onboarding wizard

The three-step wizard walks you through initial setup the first time you open the app.

### 2. Configure an AI provider

Navigate to **Settings** and add at least one AI provider (OpenAI, Anthropic, or Google Gemini) with a valid API key. This enables the natural language query engine.

!!! info "Environment keys take priority"
    If you set a provider key via `DATAX_OPENAI_API_KEY` (or the Anthropic/Gemini equivalents) in your `.env.local`, it overrides any key configured through the UI.

### 3. Add your first data source

You have two options:

=== "Upload a file"

    Click **Upload** and drag in a CSV, Excel (.xlsx), Parquet, or JSON file. DataX registers it as a virtual table in DuckDB for instant querying.

=== "Connect a database"

    Click **Connect Database** and provide credentials for a PostgreSQL or MySQL instance. DataX connects in **read-only mode** with query time limits for safety.

### 4. Start chatting

Open a new conversation and ask a question in plain English:

> *"What are the top 10 customers by total revenue?"*

The AI agent generates SQL, executes it against your data, and returns results with interactive Plotly charts — all streamed in real time.

## What's Next?

- **[Configuration](configuration.md)** — Full reference for all environment variables and settings
- **[Development](../guides/development.md)** — Dev workflow, testing, linting, and contributing
- **[Architecture](../architecture/overview.md)** — How the backend, frontend, and AI pipeline fit together
