import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import settings, dashboard, automation, jobs, cv, answers, chat, profile, auth, sources, linkedin_debug

app = FastAPI(title="JobsLand API", version="1.0.0")

# On Replit (REPL_ID is set) allow all origins — Replit proxies via *.repl.co domains.
# Note: allow_credentials=True cannot be combined with allow_origins=["*"] per CORS spec.
_is_replit = bool(os.environ.get("REPL_ID"))
_allowed_origins = ["*"] if _is_replit else [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5000",
    "http://0.0.0.0:5000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=not _is_replit,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(settings.router,       prefix="/api")
app.include_router(dashboard.router,      prefix="/api")
app.include_router(automation.router,     prefix="/api")
app.include_router(jobs.router,           prefix="/api")
app.include_router(cv.router,             prefix="/api")
app.include_router(answers.router,        prefix="/api")
app.include_router(chat.router,           prefix="/api")
app.include_router(profile.router,        prefix="/api")
app.include_router(auth.router,           prefix="/api")
app.include_router(sources.router,        prefix="/api")
app.include_router(linkedin_debug.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "JobsLand"}


@app.get("/")
def root():
    _port = os.environ.get("PORT", "3000")
    return {
        "app": "JobsLand API",
        "message": f"Open the web app at http://0.0.0.0:{_port}/",
        "health": "/api/health",
    }
