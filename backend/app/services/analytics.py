from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import Application, Job, JobScore


def summary(db: Session) -> dict:
    total = db.query(Job).count()
    first = db.query(Job).filter(Job.is_first_to_apply_candidate.is_(True)).count()
    easy = db.query(Job).filter(Job.apply_type.in_(["easy_apply", "quick_apply"])).count()
    ready = db.query(Job).filter(Job.status == "ready").count()
    needs_review = db.query(Job).join(Job.answers).filter_by(needs_review=True).count()
    applied = db.query(Application).filter(Application.status == "applied").count()
    avg_fit = db.query(func.avg(JobScore.fit_score)).scalar() or 0
    return {
        "new_jobs_today": total,
        "first_to_apply": first,
        "easy_apply_ready": easy,
        "high_fit_jobs": db.query(JobScore).filter(JobScore.fit_score >= 80).count(),
        "ready_to_apply": ready,
        "needs_review": needs_review,
        "applied_this_week": applied,
        "followups_due": db.query(Application).filter(Application.follow_up_stage != "cold").count(),
        "average_fit_score": round(avg_fit, 1),
        "no_response_14_days": db.query(Application).filter(Application.outcome == "No Response").count(),
    }


def grouped(db: Session, column) -> list[dict]:
    rows = db.query(column, func.count(Job.id)).group_by(column).all()
    return [{"name": name or "Unknown", "value": count} for name, count in rows]

