#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Start backend
(cd apps/backend && uv run fastapi dev) &
BACKEND_PID=$!

# Start frontend
(cd apps/frontend && pnpm dev) &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
