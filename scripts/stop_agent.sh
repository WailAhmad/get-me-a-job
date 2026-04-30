#!/usr/bin/env bash
# Stop the agent and the background Chrome it spawned.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -f data/agent.pid ]; then
  PID=$(cat data/agent.pid)
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
    echo "Sent SIGTERM to agent pid=$PID"
  fi
  rm -f data/agent.pid
fi

# Best-effort: ask Chrome to close via its CDP /json/close endpoint.
PORT="${AGENT_CDP_PORT:-9222}"
curl -s --max-time 2 "http://127.0.0.1:${PORT}/json/close" > /dev/null || true

# Then kill any chrome process that was launched against this user-data-dir.
PROFILE_DIR="$ROOT/data/chrome_user_data"
pgrep -f "user-data-dir=${PROFILE_DIR}" 2>/dev/null | while read -r pid; do
  kill "$pid" 2>/dev/null || true
done

echo "✓ Agent stopped."
