#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Linting backend..."
(cd apps/backend && uv run ruff check . && uv run ruff format --check .)

echo "Linting frontend..."
(cd apps/frontend && pnpm lint)
