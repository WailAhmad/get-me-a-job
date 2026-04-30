#!/usr/bin/env bash
# Install the agent's dependencies into the existing backend venv.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -x "backend/.venv/bin/python" ]; then
  echo "Backend venv missing. Run the main install first (./start.sh boots it)." >&2
  exit 1
fi
PY="backend/.venv/bin/python"
PIP="backend/.venv/bin/pip"

echo "→ Upgrading pip"
"$PIP" install --quiet --upgrade pip

echo "→ Installing agent requirements"
"$PIP" install --quiet -r requirements-agent.txt

echo "→ Installing Playwright Chromium runtime (one-time, ~120 MB)"
"$PY" -m playwright install chromium

if [ ! -d "/Applications/Google Chrome.app" ] && [ ! -x "/usr/bin/google-chrome" ]; then
  echo "WARNING: Google Chrome not found. The agent launches Chrome — please install it." >&2
fi

mkdir -p data agent
[ -f agent/data.json ] || cp agent/data.example.json agent/data.json
touch data/process.log

echo
echo "✓ Agent setup complete."
echo "  • Edit agent/data.json (or it will auto-sync from state.json on first run)."
echo "  • Export your Groq key:    export AI_API_KEY=gsk_…"
echo "  • Verify stealth:          $PY scripts/verify_stealth.py"
echo "  • Run agent (foreground):  $PY -m agent"
echo "  • Run agent (background):  ./scripts/start_agent.sh"
