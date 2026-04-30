#!/bin/bash
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 Starting Job Land..."

# ── Backend ──────────────────────────────────────────────────────────────────
echo "  → Starting backend on port 8001…"
cd "$ROOT"
PYTHONPATH="$ROOT" "$ROOT/backend/.venv/bin/python" -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --reload &
BACKEND_PID=$!

# ── Frontend ─────────────────────────────────────────────────────────────────
echo "  → Starting frontend on port 3000…"
cd "$ROOT/frontend"
npm run dev -- --host 127.0.0.1 --port 3000 &
FRONTEND_PID=$!

echo ""
echo "✅ Job Land is running!"
echo "   Frontend → http://127.0.0.1:3000"
echo "   Backend  → http://127.0.0.1:8001"
echo ""
echo "Press Ctrl+C to stop."

wait $BACKEND_PID $FRONTEND_PID
