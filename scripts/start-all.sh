#!/usr/bin/env bash
# Start backend + frontend together (Git Bash / Linux).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[start-all] launching backend on :8010 (background)"
bash "$ROOT/scripts/start-backend.sh" &
BACK_PID=$!
trap 'kill $BACK_PID 2>/dev/null || true' EXIT

echo "[start-all] waiting for /health..."
for _ in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then
    echo "[start-all] backend healthy"
    break
  fi
  sleep 1
done

echo "[start-all] launching dashboard on :3010"
bash "$ROOT/scripts/start-frontend.sh"
