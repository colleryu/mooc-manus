#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/mooc-manus-uv-cache}"
export UV_CACHE_DIR

docker compose -f "$PROJECT_DIR/docker-compose.yml" up -d postgres redis sandbox

(
  cd "$PROJECT_DIR/api"
  uv run alembic upgrade head
  exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
) &
API_PID=$!

(
  cd "$PROJECT_DIR/ui"
  exec npm run dev -- --hostname 0.0.0.0 --port 3000
) &
UI_PID=$!

cleanup() {
  kill "$API_PID" "$UI_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "MoocManus UI:  http://localhost:3000"
echo "MoocManus API: http://localhost:8000/docs"
wait
