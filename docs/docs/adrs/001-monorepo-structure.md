# ADR 001: Monorepo Structure

## Status

Accepted

## Date

2026-03-12

## Context

The DataX repository started as a flat layout with `backend/` and `frontend/` at the root. As the project grows to include shared packages, infrastructure configs, and CI/CD pipelines, a more structured monorepo layout is needed.

## Decision

Adopt a workspace-based monorepo pattern:

- **`apps/`** — Deployable applications (backend, frontend)
- **`packages/`** — Shared libraries (e.g., shared-types)
- **`infra/`** — Docker, Kubernetes, Terraform configs
- **`scripts/`** — Developer utility scripts
- **`docs/`** — Documentation site (MkDocs)
- **`internal/`** — Specs and internal documents

Use pnpm workspaces for Node.js packages and uv workspaces for Python packages, with Turborepo for cross-language task orchestration.

The backend uses a `src` layout (`apps/backend/src/app/`) so that `from app.*` imports remain unchanged while cleanly separating source from config files.

## Consequences

- **Positive:** Clear separation of concerns, workspace-level dependency management, parallel task execution via Turborepo, easier CI/CD with path-based filtering
- **Negative:** Slightly deeper paths, Docker build context changes to repo root, relative path updates needed in configs
- **Neutral:** Git history preserved via `git mv`
