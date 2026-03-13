#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Building backend..."
(cd apps/backend && uv build)

echo "Building frontend..."
(cd apps/frontend && pnpm build)
