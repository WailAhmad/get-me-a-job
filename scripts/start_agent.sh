#!/usr/bin/env bash
# Background-launch the agent. Logs go to data/process.log.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="backend/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "Backend venv missing. Run ./scripts/setup_agent.sh first." >&2
  exit 1
fi

if [ -z "${AI_API_KEY:-}" ]; then
  echo "WARNING: AI_API_KEY is not set. The agent will fail at first LLM call." >&2
fi

mkdir -p data
nohup "$PY" -m agent >> data/process.log 2>&1 &
PID=$!
disown $PID 2>/dev/null || true
echo "$PID" > data/agent.pid
echo "✓ Agent started in background  pid=$PID"
echo "  tail -f data/process.log"
