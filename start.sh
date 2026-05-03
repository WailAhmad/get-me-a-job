#!/bin/bash
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── Detect environment ────────────────────────────────────────────────────────
if [ -n "$REPL_ID" ]; then
  # ── Replit ──────────────────────────────────────────────────────────────────
  BACKEND_HOST="0.0.0.0"
  BACKEND_PORT="8000"
  FRONTEND_PORT="${PORT:-5000}"
  PYTHON_CMD="python"
  echo "🌐 Running on Replit (backend :${BACKEND_PORT} · frontend :${FRONTEND_PORT})"

  # Start virtual display for Selenium (Replit has no physical display)
  if command -v Xvfb &> /dev/null; then
    Xvfb :99 -screen 0 1280x720x24 &>/dev/null &
    export DISPLAY=:99
    echo "  → Virtual display started (:99)"
  fi
else
  # ── Local Mac ───────────────────────────────────────────────────────────────
  BACKEND_HOST="127.0.0.1"
  BACKEND_PORT="8001"
  FRONTEND_PORT="3000"
  PYTHON_CMD="$ROOT/backend/.venv/bin/python"
  echo "🚀 Starting JobsLand locally (backend :${BACKEND_PORT} · frontend :${FRONTEND_PORT})"
fi

# ── Backend ───────────────────────────────────────────────────────────────────
echo "  → Starting backend on ${BACKEND_HOST}:${BACKEND_PORT}…"
cd "$ROOT"
PYTHONPATH="$ROOT" $PYTHON_CMD -m uvicorn backend.main:app \
  --host "$BACKEND_HOST" \
  --port "$BACKEND_PORT" \
  --reload &
BACKEND_PID=$!

# ── Frontend ──────────────────────────────────────────────────────────────────
echo "  → Starting frontend on :${FRONTEND_PORT}…"
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ JobsLand is running!"
if [ -n "$REPL_ID" ]; then
  echo "   App → https://${REPL_SLUG}.${REPL_OWNER}.repl.co"
else
  echo "   Frontend → http://127.0.0.1:${FRONTEND_PORT}"
  echo "   Backend  → http://127.0.0.1:${BACKEND_PORT}"
fi
echo ""
echo "Press Ctrl+C to stop."

wait $BACKEND_PID $FRONTEND_PID
