#!/usr/bin/env bash
# Start the SENTINEL-X dashboard on http://127.0.0.1:3010
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${SENTINEL_WEB_PORT:-3010}"
API="${NEXT_PUBLIC_API_URL:-http://127.0.0.1:8010}"

cd "$ROOT/frontend"

if [ ! -d "node_modules" ]; then
  echo "[start-frontend] installing dependencies (npm install)..."
  npm install
fi

export NEXT_PUBLIC_API_URL="$API"
echo "[start-frontend] dashboard on http://127.0.0.1:${PORT} -> API ${API}"
exec npm run dev -- --port "$PORT"
