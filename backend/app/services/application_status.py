from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.entities import Application, BehaviourLog, Job
from app.services.preparation import generate_interview_kit


APPLIED_PATTERNS = [
    r"\bapplication submitted\b",
    r"\byou(?:'|’)ve applied\b",
    r"\byou have applied\b",
    r"\balready applied\b",
    r"\bview resume\b",
    r"\bapplication viewed\b",
]


def detect_applied_status(text: str, url: str = "") -> dict:
    blob = f"{url}\n{text}".lower()
    if "linkedin." not in blob and "application submitted" not in blob:
        return {"applied": False, "reason": ""}
    for pattern in APPLIED_PATTERNS:
        if re.search(pattern, blob, flags=re.I):
            return {"applied": True, "reason": "Visible page shows application already submitted"}
    return {"applied": False, "reason": ""}


def mark_already_applied(db: Session, job: Job, reason: str) -> Application:
    app = db.query(Application).filter(Application.job_id == job.id).first() or Application(job_id=job.id)
    app.status = "applied"
    app.applied_date = app.applied_date or datetime.utcnow()
    app.follow_up_date = app.follow_up_date or datetime.utcnow() + timedelta(days=7)
    app.follow_up_stage = app.follow_up_stage or "day_0"
    note = f"Detected from browser page: {reason}"
    if note not in (app.notes or ""):
        app.notes = f"{app.notes}\n{note}".strip()
    job.status = "applied"
    db.add(app)
    db.add(job)
    db.add(BehaviourLog(job_id=job.id, action_type="detected_already_applied", action_value=reason))
    generate_interview_kit(db, job)
    return app
