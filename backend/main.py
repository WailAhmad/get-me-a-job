from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import settings, dashboard, automation, jobs, cv, answers, chat, profile, auth, sources, linkedin_debug

app = FastAPI(title="JobsLand API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(settings.router,   prefix="/api")
app.include_router(dashboard.router,  prefix="/api")
app.include_router(automation.router, prefix="/api")
app.include_router(jobs.router,       prefix="/api")
app.include_router(cv.router,         prefix="/api")
app.include_router(answers.router,    prefix="/api")
app.include_router(chat.router,       prefix="/api")
app.include_router(profile.router,    prefix="/api")
app.include_router(auth.router,       prefix="/api")
app.include_router(sources.router,    prefix="/api")
app.include_router(linkedin_debug.router, prefix="/api")

@app.get("/api/health")
def health():
    return {"status": "ok", "app": "JobsLand"}


@app.get("/")
def root():
    return {
        "app": "JobsLand API",
        "message": "Open the web app at http://127.0.0.1:3000/",
        "health": "/api/health",
    }
