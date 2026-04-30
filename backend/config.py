import os
from pathlib import Path

BASE_DIR    = Path(__file__).parent
ROOT_DIR    = BASE_DIR.parent
DATA_DIR    = BASE_DIR.parent / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
CHROME_PROFILE_PATH = str(SESSIONS_DIR / "chrome_profile")

DATABASE_URL = f"sqlite:///{DATA_DIR / 'db.sqlite'}"

def _load_env_file() -> None:
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()

AI_PROVIDER = os.getenv("AI_PROVIDER", "groq")
AI_API_KEY  = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.groq.com/openai/v1")
AI_MODEL    = os.getenv("AI_MODEL", "llama-3.3-70b-versatile")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://127.0.0.1:3000")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://127.0.0.1:8001/api/auth/google/callback")

APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID", "")
APPLE_CLIENT_SECRET = os.getenv("APPLE_CLIENT_SECRET", "")
APPLE_REDIRECT_URI = os.getenv("APPLE_REDIRECT_URI", "http://127.0.0.1:8001/api/auth/apple/callback")

# Ensure dirs exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
Path(CHROME_PROFILE_PATH).mkdir(parents=True, exist_ok=True)
