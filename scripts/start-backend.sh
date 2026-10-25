#!/usr/bin/env bash
# Start the SENTINEL-X backend (FastAPI + SQLite) on http://127.0.0.1:8010
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
PORT="${SENTINEL_PORT:-8010}"

cd "$BACKEND"

if [ ! -d ".venv" ]; then
  echo "[start-backend] creating virtualenv..."
  python -m venv .venv
fi

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  PY=".venv/Scripts/python.exe"   # Git Bash on Windows
fi

if ! "$PY" -c "import fastapi, uvicorn, sqlalchemy" >/dev/null 2>&1; then
  echo "[start-backend] installing dependencies..."
  "$PY" -m pip install -r requirements.txt
fi

echo "[start-backend] initializing database (create_all + seed)..."
"$PY" -c "from app.db import init_db; init_db(); print('database ready')"

echo "[start-backend] serving on http://127.0.0.1:${PORT}"
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
