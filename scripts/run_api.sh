#!/usr/bin/env bash
# Run the Brain Tumor MRI REST API (from project root).
# Usage: ./scripts/run_api.sh [port]
# Requires: pip install -r requirements.txt
set -e
cd "$(dirname "$0")/.."
PORT="${1:-8000}"
echo "Starting API on port $PORT (docs: http://localhost:$PORT/docs)"
exec python -m uvicorn src.api.main:app --host 0.0.0.0 --port "$PORT"
