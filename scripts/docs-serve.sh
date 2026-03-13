#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../docs"
uv run mkdocs serve
