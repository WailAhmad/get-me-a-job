"""
Dashboard router — aggregate counts for the main cards.
"""
from datetime import datetime, timezone
from fastapi import APIRouter
from backend import state

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
def stats():
    s = state.get()
    items = list(s["jobs"]["items"].values())
    today = datetime.now(timezone.utc).date()

    applied = [j for j in items if j.get("status") == "applied" and j.get("submission_verified")]
    recorded_applied = [j for j in items if j.get("status") == "applied" and not j.get("submission_verified")]
    pending = [j for j in items if j.get("status") == "pending"]
    pending_questions = [j for j in pending if j.get("pending_kind") != "verify_source"]
    pending_verify = [j for j in pending if j.get("pending_kind") == "verify_source"]
    external = [j for j in items if j.get("status") == "external"]
    skipped = [j for j in items if j.get("status") == "skipped"]
    queued = [j for j in items if j.get("status") in (None, "discovered")]

    applied_today = 0
    for j in applied:
        ts = j.get("applied_at")
        if ts and datetime.fromtimestamp(ts, tz=timezone.utc).date() == today:
            applied_today += 1

    return {
        "jobs_found":           len(items),
        "auto_applied":         len(applied),
        "recorded_applications": len(recorded_applied),
        "applied_today":        applied_today,
        "external_jobs":        len(external),
        "pending":              len(pending),
        "pending_questions":    len(pending_questions),
        "pending_verify":       len(pending_verify),
        "skipped":              len(skipped),
        "queued":               len(queued),
        "today_count":          s["automation"].get("today_count", 0),
        "hour_count":           s["automation"].get("hour_count", 0),
        "daily_cap":            100,
        "hourly_cap":           10,
        "cv_uploaded":          bool(s["cv"].get("filename")),
        "preferences_ready":    bool(s["preferences"].get("ready")),
    }
