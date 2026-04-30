from __future__ import annotations

from datetime import datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import Application, Job
from app.services.analytics import summary


def answer_question(db: Session, question: str) -> dict:
    q = question.lower()
    data = _query_data(db, q)
    prompt = _prompt(question, data)
    ollama = _ollama(prompt)
    if ollama:
        return {"answer": ollama, "source": data["source"], "data": data}
    return {"answer": _fallback(question, data), "source": data["source"], "data": data, "fallback": "Ollama not running"}


def _query_data(db: Session, q: str) -> dict:
    today = datetime.utcnow().date()
    if "first" in q and "apply" in q:
        jobs = db.query(Job).filter(Job.is_first_to_apply_candidate.is_(True)).all()
        return {"kind": "first_to_apply", "jobs": [_job(j) for j in jobs], "source": "jobs + job_scores where is_first_to_apply_candidate = true"}
    if "easy" in q or "quick" in q:
        jobs = db.query(Job).filter(Job.apply_type.in_(["easy_apply", "quick_apply"])).all()
        return {"kind": "easy_apply", "jobs": [_job(j) for j in jobs], "source": "jobs + job_scores where apply_type in easy/quick"}
    if "follow" in q:
        apps = db.query(Application).filter(Application.follow_up_date.isnot(None)).all()
        return {"kind": "followups", "applications": [{"job_id": a.job_id, "follow_up_date": str(a.follow_up_date), "status": a.status} for a in apps], "source": "applications where follow_up_date is not null"}
    if "review" in q:
        jobs = db.query(Job).join(Job.answers).filter_by(needs_review=True).all()
        return {"kind": "needs_review", "jobs": [_job(j) for j in jobs], "source": "jobs join application_answers where needs_review = true"}
    if "weekly" in q or "summary" in q:
        since = datetime.utcnow() - timedelta(days=7)
        jobs = db.query(Job).filter(Job.created_at >= since).all()
        return {"kind": "weekly_summary", "summary": summary(db), "jobs": [_job(j) for j in jobs], "source": "jobs/applications/job_scores for last 7 days"}
    if "next" in q or "apply" in q:
        jobs = sorted(db.query(Job).all(), key=lambda j: ((j.score.fit_score if j.score else 0), (j.score.effort_score if j.score else 0)), reverse=True)[:10]
        return {"kind": "ranked_next", "jobs": [_job(j) for j in jobs], "source": "jobs ranked by fit_score and effort_score"}
    return {"kind": "today", "summary": summary(db), "source": "analytics summary from jobs/job_scores/applications"}


def _job(job: Job) -> dict:
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "country": job.country,
        "platform": job.platform,
        "apply_type": job.apply_type,
        "status": job.status,
        "fit_score": job.score.fit_score if job.score else None,
        "effort_score": job.score.effort_score if job.score else None,
        "match_reason": job.score.match_reason if job.score else "",
    }


def _prompt(question: str, data: dict) -> str:
    return (
        "You are ApplyPilot AI Analyst. Answer only from the provided SQLite-derived data. "
        "If a fact is absent, say it is unavailable. Be concise and actionable.\n\n"
        f"Question: {question}\nData: {data}"
    )


def _ollama(prompt: str) -> str:
    try:
        with httpx.Client(timeout=8) as client:
            res = client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={"model": settings.ollama_model, "prompt": prompt, "stream": False, "options": {"temperature": 0.2}},
            )
            if res.status_code == 200:
                return res.json().get("response", "").strip()
    except Exception:
        return ""
    return ""


def _fallback(question: str, data: dict) -> str:
    if "jobs" in data:
        jobs = data["jobs"]
        if not jobs:
            return "No matching jobs are currently in that queue."
        lines = [f"{j['title']} at {j['company']} ({j['country']}) - fit {j['fit_score']}, effort {j['effort_score']}, status {j['status']}" for j in jobs[:8]]
        return "\n".join(lines)
    if "applications" in data:
        return f"{len(data['applications'])} applications have follow-up dates recorded."
    return f"Current pipeline summary: {data.get('summary', {})}"

