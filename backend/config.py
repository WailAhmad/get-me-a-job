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

SMTP_PROVIDER = os.getenv("SMTP_PROVIDER", "smtp2go").strip().lower()
_SMTP_DEFAULTS = {
    "smtp2go": ("mail.smtp2go.com", 2525),
    "brevo": ("smtp-relay.brevo.com", 587),
    "mailjet": ("in-v3.mailjet.com", 587),
    "sendgrid": ("smtp.sendgrid.net", 587),
    "gmail": ("smtp.gmail.com", 587),
}
_default_host, _default_port = _SMTP_DEFAULTS.get(SMTP_PROVIDER, ("", 587))
SMTP_HOST = os.getenv("SMTP_HOST", _default_host)
SMTP_PORT = int(os.getenv("SMTP_PORT", str(_default_port)) or str(_default_port))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME)
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "JobsLand")
SMTP2GO_API_KEY = os.getenv("SMTP2GO_API_KEY", "")
SMTP2GO_API_BASE_URL = os.getenv("SMTP2GO_API_BASE_URL", "https://api.smtp2go.com/v3")

# Ensure dirs exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
Path(CHROME_PROFILE_PATH).mkdir(parents=True, exist_ok=True)
