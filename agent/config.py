"""Constants & paths for the agent. No logic — values only."""
from __future__ import annotations
import os
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────
ROOT          = Path(__file__).resolve().parents[1]
DATA_DIR      = ROOT / "data"
AGENT_DIR     = ROOT / "agent"
LOG_FILE      = DATA_DIR / "process.log"
HISTORY_DB    = DATA_DIR / "history.db"
PROFILE_DIR   = DATA_DIR / "chrome_user_data"
DATA_JSON     = AGENT_DIR / "data.json"
DATA_EXAMPLE  = AGENT_DIR / "data.example.json"
STATE_JSON    = DATA_DIR / "state.json"   # written by the FastAPI app
ENV_FILE      = ROOT / ".env"

DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── Auto-load .env (best effort, never crashes the agent) ─────────────
try:
    from dotenv import load_dotenv
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=False)
except Exception:
    pass

# ── Chrome remote debugging ───────────────────────────────────────────
CDP_PORT = int(os.environ.get("AGENT_CDP_PORT", "9222"))
CDP_HOST = "127.0.0.1"

CHROME_BINARIES = {
    "darwin": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "linux":  "/usr/bin/google-chrome",
    "win32":  r"C:\Program Files\Google\Chrome\Application\chrome.exe",
}

def chrome_binary() -> str:
    path = CHROME_BINARIES.get(sys.platform)
    if not path or not Path(path).exists():
        raise RuntimeError(f"Google Chrome not found at {path}. Install it or set CHROME_BINARIES.")
    return path

# ── Defaults (data.json overrides at runtime) ─────────────────────────
MIN_SCORE        = 85
MAX_PER_HOUR     = 20
MAX_PER_DAY      = 100
DELAY_BETWEEN    = (120, 240)   # seconds, uniform random between jobs

# ── LLM (Groq, OpenAI-compatible chat completions) ────────────────────
GROQ_BASE_URL = os.environ.get("AI_BASE_URL") or "https://api.groq.com/openai/v1"
GROQ_API_KEY  = os.environ.get("AI_API_KEY") or os.environ.get("GROQ_API_KEY") or ""
GROQ_MODEL    = os.environ.get("AI_MODEL") or "llama-3.3-70b-versatile"
GROQ_TIMEOUT  = float(os.environ.get("AGENT_LLM_TIMEOUT", "30"))

# ── Logging ───────────────────────────────────────────────────────────
LOG_LEVEL     = os.environ.get("AGENT_LOG_LEVEL", "INFO").upper()
LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUPS   = 5
