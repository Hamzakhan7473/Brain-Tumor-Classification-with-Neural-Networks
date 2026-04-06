#!/usr/bin/env bash
# Start FastAPI (:8000) and Vite (:5173) together for a local demo (same machine).
# Usage from project root: ./scripts/demo_local.sh
# Requires: Python venv with requirements, Node/npm for frontend.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required for the frontend. Install Node.js LTS."
  exit 1
fi

export PYTHONPATH="$ROOT"
echo "Starting API at http://127.0.0.1:8000 (docs: /docs) …"
"$PY" -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!

cleanup() {
  echo ""
  echo "Stopping API (pid $API_PID)…"
  kill "$API_PID" 2>/dev/null || true
  wait "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

sleep 2

cd "$ROOT/frontend"
echo "Starting UI at http://localhost:5173 — press Ctrl+C to stop both."
npm run dev
