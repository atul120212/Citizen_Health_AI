#!/usr/bin/env bash
# Citizen Health AI — start backend, LiveKit worker, and frontend (macOS/Linux)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
WORKER="$ROOT/livekit_worker"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
SKIP_WORKER="${SKIP_WORKER:-0}"

echo ""
echo "  Citizen Health AI — full stack startup"
echo "  Root: $ROOT"
echo ""

if [[ ! -d "$BACKEND/.venv" ]]; then
  echo "==> Creating backend venv..."
  python3 -m venv "$BACKEND/.venv"
  "$BACKEND/.venv/bin/pip" install -r "$BACKEND/requirements.txt"
fi

PY="$BACKEND/.venv/bin/python"
PIP="$BACKEND/.venv/bin/pip"

if [[ "$SKIP_WORKER" != "1" ]]; then
  echo "==> Installing LiveKit worker deps..."
  "$PIP" install -q -r "$WORKER/requirements.txt"
fi

if [[ ! -d "$FRONTEND/node_modules" ]]; then
  echo "==> npm install (frontend)..."
  (cd "$FRONTEND" && npm install)
fi

cleanup() {
  echo ""
  echo "Stopping services..."
  jobs -p | xargs -r kill 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

echo "==> Starting backend :$BACKEND_PORT"
(cd "$BACKEND" && "$PY" -m uvicorn app.main:app --reload --host 127.0.0.1 --port "$BACKEND_PORT") &
sleep 2

if [[ "$SKIP_WORKER" != "1" ]]; then
  echo "==> Starting LiveKit worker"
  (cd "$WORKER" && "$PY" agent.py dev) &
  sleep 2
fi

echo "==> Starting frontend :$FRONTEND_PORT"
(cd "$FRONTEND" && npm run dev -- -p "$FRONTEND_PORT") &
sleep 2

echo ""
echo "  Backend:  http://127.0.0.1:$BACKEND_PORT/health"
echo "  Frontend: http://localhost:$FRONTEND_PORT"
echo ""
echo "  Press Ctrl+C to stop all."
echo ""

wait
