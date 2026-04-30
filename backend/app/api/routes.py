from __future__ import annotations

from datetime import datetime, timedelta
import csv
import io
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.entities import AnswerBank, Application, BehaviourLog, CandidateProfile, Job, JobScore, PlatformConnection, SourceRun
from app.schemas.entities import AnswerBankCreate, BehaviourRequest, ImportTextRequest, JobCreate, JobDetail, JobRead, OutcomeRequest, RejectRequest
from app.services.analytics import grouped, summary
from app.services.ai_analyst import answer_question
from app.services.application_status import detect_applied_status, mark_already_applied
from app.services.cv_parser import apply_parsed_profile, extract_text_from_upload, parse_cv_text
from app.services.gmail_service import auth_url, disconnect as gmail_disconnect, oauth_callback, sync_gmail, get_recruiter_emails
from app.services.job_import import create_or_update_job, parse_job_text
from app.services.preparation import generate_company_brief, generate_interview_kit, prepare_job
from app.services.scoring import detect_apply_type, first_to_apply_eligible, score_job

router = APIRouter()


def serialize_job(job: Job) -> dict:
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "country": job.country,
        "city": job.city,
        "platform": job.platform,
        "source_policy": job.source_policy,
        "source_email_id": job.source_email_id,
        "source_email_subject": job.source_email_subject,
        "source_email_from": job.source_email_from,
        "apply_type": job.apply_type,
        "apply_url": job.apply_url,
        "job_url": job.job_url,
        "status": job.status,
        "description": job.description,
        "description_summary": job.description_summary,
        "is_first_to_apply_candidate": job.is_first_to_apply_candidate,
        "first_to_apply_reason": job.first_to_apply_reason,
        "fast_track": job.fast_track,
        "jd_quality_score": job.jd_quality_score,
        "first_seen_at": job.first_seen_at,
        "score": {
            "fit_score": job.score.fit_score,
            "effort_score": job.score.effort_score,
            "freshness_score": job.score.freshness_score,
            "match_reason": job.score.match_reason,
            "concerns": job.score.concerns,
            "recommendation": job.score.recommendation,
        } if job.score else None,
        "application": {
            "status": job.application.status,
            "cv_version": job.application.cv_version,
            "cover_letter": job.application.cover_letter,
            "outreach_message": job.application.outreach_message,
            "follow_up_date": job.application.follow_up_date,
            "applied_date": job.application.applied_date,
            "notes": job.application.notes,
        } if job.application else None,
        "answers": [
            {
                "id": answer.id,
                "question_text": answer.question_text,
                "normalized_question": answer.normalized_question,
                "answer": answer.answer,
                "confidence": answer.confidence,
                "needs_review": answer.needs_review,
            }
            for answer in job.answers
        ],
        "brief": {
            "recent_news": job.brief.recent_news,
            "leadership_names": job.brief.leadership_names,
            "tech_stack_signals": job.brief.tech_stack_signals,
            "ai_initiatives": job.brief.ai_initiatives,
            "sector_context": job.brief.sector_context,
        } if job.brief else None,
        "interview_kit": {
            "predicted_questions_json": job.interview_kit.predicted_questions_json,
            "suggested_answers_json": job.interview_kit.suggested_answers_json,
            "company_questions_json": job.interview_kit.company_questions_json,
            "cheat_sheet": job.interview_kit.cheat_sheet,
        } if job.interview_kit else None,
    }


def apply_scores(db: Session, job: Job) -> Job:
    job.apply_type = detect_apply_type(job)
    scores = score_job(job)
    job.jd_quality_score = scores["jd_quality_score"]
    job.fast_track = scores["fast_track"]
    eligible, reason = first_to_apply_eligible(job, scores["fit_score"], scores["effort_score"])
    job.is_first_to_apply_candidate = eligible
    job.first_to_apply_reason = reason
    db.add(job)
    db.flush()
    existing = job.score or JobScore(job_id=job.id)
    for key in ["fit_score", "effort_score", "freshness_score", "match_reason", "concerns", "recommendation"]:
        setattr(existing, key, scores[key])
    db.add(existing)
    return job


@router.get("/health")
def health():
    return {"status": "ok", "manual_submit_required": True}


@router.get("/profile")
def profile(db: Session = Depends(get_db)):
    item = db.query(CandidateProfile).first()
    if not item:
        item = CandidateProfile()
        db.add(item)
        db.commit()
        db.refresh(item)
    return item


def serialize_profile(item: CandidateProfile) -> dict:
    return {
        "id": item.id,
        "full_name": item.full_name,
        "current_title": item.current_title,
        "current_company": item.current_company,
        "location": item.location,
        "email": item.email,
        "linkedin_url": item.linkedin_url,
        "nationality": item.nationality,
        "summary": item.summary,
        "years_experience": item.years_experience,
        "core_skills": json.loads(item.core_skills_json or "[]"),
        "ai_experience": json.loads(item.ai_experience_json or "[]"),
        "data_experience": json.loads(item.data_experience_json or "[]"),
        "cloud_platforms": json.loads(item.cloud_platforms_json or "[]"),
        "governance_tools": json.loads(item.governance_tools_json or "[]"),
        "industries": json.loads(item.industries_json or "[]"),
        "employers": json.loads(item.employers_json or "[]"),
        "education": json.loads(item.education_json or "[]"),
        "certifications": json.loads(item.certifications_json or "[]"),
        "major_achievements": json.loads(item.major_achievements_json or "[]"),
        "profile": json.loads(item.profile_json or "{}"),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


@router.get("/profile/structured")
def structured_profile(db: Session = Depends(get_db)):
    item = db.query(CandidateProfile).first()
    if not item:
        item = CandidateProfile()
        db.add(item)
        db.commit()
        db.refresh(item)
    return serialize_profile(item)


@router.put("/profile")
def update_profile(payload: dict, db: Session = Depends(get_db)):
    item = db.query(CandidateProfile).first() or CandidateProfile()
    for key in ["full_name", "current_title", "current_company", "location", "email", "linkedin_url", "nationality", "summary", "years_experience"]:
        if key in payload and hasattr(item, key):
            setattr(item, key, payload[key])
    json_fields = {
        "core_skills": "core_skills_json",
        "ai_experience": "ai_experience_json",
        "data_experience": "data_experience_json",
        "cloud_platforms": "cloud_platforms_json",
        "governance_tools": "governance_tools_json",
        "industries": "industries_json",
        "employers": "employers_json",
        "education": "education_json",
        "certifications": "certifications_json",
        "major_achievements": "major_achievements_json",
    }
    for key, attr in json_fields.items():
        if key in payload:
            setattr(item, attr, json.dumps(payload[key]))
    if "profile" in payload:
        item.profile_json = json.dumps(payload["profile"])
    item.updated_at = datetime.utcnow()
    db.add(item)
    db.commit()
    return item


@router.post("/profile/upload-cv")
async def upload_cv(file: UploadFile, db: Session = Depends(get_db)):
    content = await file.read()
    filename = file.filename or "cv"
    try:
        text = extract_text_from_upload(filename, content)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    parsed = parse_cv_text(text, filename)
    profile = db.query(CandidateProfile).first() or CandidateProfile()
    apply_parsed_profile(profile, parsed)
    profile.updated_at = datetime.utcnow()
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return {"filename": filename, "characters": len(text), "profile": serialize_profile(profile)}


@router.get("/connections")
def connections(db: Session = Depends(get_db)):
    return db.query(PlatformConnection).order_by(PlatformConnection.platform.asc()).all()


@router.post("/connections/{platform}/account-hint")
def set_account_hint(platform: str, payload: dict, db: Session = Depends(get_db)):
    item = db.query(PlatformConnection).filter(PlatformConnection.platform.ilike(platform)).first()
    if not item:
        raise HTTPException(404, "Connection not found")
    item.account_hint = payload.get("account_hint", "")
    item.updated_at = datetime.utcnow()
    db.commit()
    return item


@router.get("/jobs")
def list_jobs(status: Optional[str] = None, country: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Job).options(joinedload(Job.score), joinedload(Job.application), joinedload(Job.answers), joinedload(Job.brief), joinedload(Job.interview_kit)).order_by(Job.first_seen_at.desc())
    if status:
        query = query.filter(Job.status == status)
    if country:
        query = query.filter(Job.country == country)
    return [serialize_job(job) for job in query.all()]


@router.get("/jobs/hot")
def list_hot_jobs(db: Session = Depends(get_db)):
    # Jobs that are NOT easy apply, fit_score >= 85
    load_opts = [joinedload(Job.score), joinedload(Job.application), joinedload(Job.answers), joinedload(Job.brief), joinedload(Job.interview_kit)]
    skip = ["rejected", "skipped", "closed", "applied"]
    jobs = (
        db.query(Job).options(*load_opts)
        .join(JobScore, Job.id == JobScore.job_id)
        .filter(Job.apply_type.notin_(["easy_apply", "quick_apply", "unknown"]))
        .filter(JobScore.fit_score >= 85)
        .filter(Job.status.notin_(skip))
        .order_by(Job.first_seen_at.desc())
        .limit(50).all()
    )
    
    serialized = []
    now = datetime.utcnow()
    for j in jobs:
        data = serialize_job(j)
        
        # Add frontend tags
        tags = ["Manual Apply", "High Fit"]
        if (now - j.first_seen_at).total_seconds() < 86400:
            tags.append("Recent")
        if any(p.lower() in j.company.lower() for p in LARGE_CO_NAMES):
            tags.append("Top Company")
            
        data["hot_tags"] = tags
        serialized.append(data)
        
    return serialized


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).options(joinedload(Job.score), joinedload(Job.application), joinedload(Job.answers), joinedload(Job.brief), joinedload(Job.interview_kit)).get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return serialize_job(job)


@router.post("/jobs/import-text")
def import_text(payload: ImportTextRequest, db: Session = Depends(get_db)):
    data = parse_job_text(payload.description, payload.job_url, payload.platform)
    data.update({k: v for k, v in payload.model_dump().items() if v})
    job, duplicate = create_or_update_job(db, data, {"source_policy": "manual_text"})
    db.commit()
    job = db.query(Job).options(joinedload(Job.score), joinedload(Job.application), joinedload(Job.answers), joinedload(Job.brief), joinedload(Job.interview_kit)).get(job.id)
    result = serialize_job(job)
    result["duplicate"] = duplicate
    return result


@router.post("/jobs/import-url")
def import_url(payload: JobCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    data["description"] = data.get("description") or f"Imported from URL: {data.get('job_url') or data.get('apply_url')}"
    job, duplicate = create_or_update_job(db, data, {"source_policy": "manual_url"})
    db.commit()
    job = db.query(Job).options(joinedload(Job.score), joinedload(Job.application), joinedload(Job.answers), joinedload(Job.brief), joinedload(Job.interview_kit)).get(job.id)
    result = serialize_job(job)
    result["duplicate"] = duplicate
    return result


@router.post("/jobs/import-csv")
async def import_csv(file: UploadFile, db: Session = Depends(get_db)):
    content = (await file.read()).decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    count = 0
    for row in reader:
        data = parse_job_text(row.get("description", ""), row.get("job_url", ""), row.get("platform", "CSV"))
        data.update({k: row.get(k) for k in ["title", "company", "country", "platform", "description", "job_url"] if row.get(k)})
        _job, duplicate = create_or_update_job(db, data, {"source_policy": "csv_import"})
        count += 0 if duplicate else 1
    db.commit()
    return {"imported": count}


@router.post("/jobs/analyze-page")
def analyze_page(payload: dict, db: Session = Depends(get_db)):
    text = payload.get("text") or ""
    url = payload.get("url") or ""
    platform = payload.get("platform") or ""
    if not text.strip() and not url:
        raise HTTPException(400, "Provide visible page text or URL")
    data = parse_job_text(text, url, platform)
    if payload.get("title") and data.get("title") == "Imported Job":
        data["title"] = payload["title"]
    job, duplicate = create_or_update_job(db, data, {"source_policy": "browser_assist"})
    external_status = detect_applied_status(text, url)
    if external_status["applied"]:
        mark_already_applied(db, job, external_status["reason"])
    db.commit()
    job = db.query(Job).options(joinedload(Job.score), joinedload(Job.application), joinedload(Job.answers), joinedload(Job.brief), joinedload(Job.interview_kit)).get(job.id)
    result = serialize_job(job)
    result["duplicate"] = duplicate
    result["external_application_status"] = external_status
    return result


@router.post("/jobs/{job_id}/prepare")
@router.post("/jobs/{job_id}/auto-prepare")
def prepare(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    application = prepare_job(db, job)
    db.commit()
    return {"status": "prepared", "application_id": application.id}


@router.post("/jobs/{job_id}/detect-apply-type")
def detect(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.apply_type = detect_apply_type(job)
    db.commit()
    return {"apply_type": job.apply_type}


@router.post("/jobs/{job_id}/score-effort")
def rescore(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    apply_scores(db, job)
    db.commit()
    return job.score


@router.post("/jobs/{job_id}/generate-brief")
def brief(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    item = generate_company_brief(db, job)
    db.commit()
    return item


@router.post("/jobs/{job_id}/generate-cover-letter")
def gen_cover(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    app = prepare_job(db, job)
    db.commit()
    return {"cover_letter": app.cover_letter}


@router.post("/jobs/{job_id}/generate-outreach")
def gen_outreach(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    app = prepare_job(db, job)
    db.commit()
    return {"outreach_message": app.outreach_message}


@router.post("/jobs/{job_id}/generate-interview-kit")
def gen_kit(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    kit = generate_interview_kit(db, job)
    db.commit()
    return kit


@router.post("/jobs/{job_id}/shortlist")
def shortlist(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.status = "shortlisted"
    db.add(BehaviourLog(job_id=job.id, action_type="shortlist"))
    db.commit()
    return {"status": job.status}


@router.post("/jobs/{job_id}/reject")
def reject(job_id: int, payload: RejectRequest, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.status = "rejected"
    db.add(BehaviourLog(job_id=job.id, action_type="reject", rejection_reason=payload.rejection_reason))
    db.commit()
    return {"status": job.status}


@router.get("/applications")
def applications(db: Session = Depends(get_db)):
    return db.query(Application).all()


@router.post("/applications/auto-applied")
def log_auto_applied(payload: dict, db: Session = Depends(get_db)):
    data = {"job_url": payload.get("url", ""), "title": payload.get("title", "Auto-Applied Job")}
    job, _ = create_or_update_job(db, data, {"source_policy": "auto_apply_bot"})
    app = job.application or prepare_job(db, job)
    app.status = "applied"
    app.applied_date = datetime.utcnow()
    app.follow_up_date = datetime.utcnow() + timedelta(days=7)
    job.status = "applied"
    db.add(BehaviourLog(job_id=job.id, action_type="auto_apply"))
    db.commit()
    return {"status": "logged", "job_id": job.id}


@router.post("/applications/{job_id}/mark-applied")
def mark_applied(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    app = job.application or prepare_job(db, job)
    app.status = "applied"
    app.applied_date = datetime.utcnow()
    app.follow_up_date = datetime.utcnow() + timedelta(days=7)
    job.status = "applied"
    generate_interview_kit(db, job)
    db.add(BehaviourLog(job_id=job.id, action_type="apply"))
    db.commit()
    return {"status": "applied"}


@router.post("/applications/{job_id}/record-outcome")
def record_outcome(job_id: int, payload: OutcomeRequest, db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.job_id == job_id).first()
    if not app:
        raise HTTPException(404, "Application not found")
    app.outcome = payload.outcome
    db.commit()
    return {"outcome": app.outcome}


@router.post("/applications/{job_id}/skip")
def skip(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.status = "skipped"
    db.add(BehaviourLog(job_id=job.id, action_type="skip"))
    db.commit()
    return {"status": "skipped"}


@router.post("/applications/{job_id}/follow-up")
def follow_up(job_id: int, db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.job_id == job_id).first()
    if not app:
        raise HTTPException(404, "Application not found")
    app.follow_up_stage = "day_7"
    db.commit()
    return {"follow_up_stage": app.follow_up_stage}


@router.post("/applications/{job_id}/close")
def close(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.status = "closed"
    db.commit()
    return {"status": "closed"}


@router.post("/behaviour/log")
def behaviour(payload: BehaviourRequest, db: Session = Depends(get_db)):
    db.add(BehaviourLog(**payload.model_dump()))
    db.commit()
    return {"logged": True}


@router.get("/answer-bank")
def answer_bank(search: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(AnswerBank)
    if search:
        query = query.filter(AnswerBank.normalized_question.contains(search.lower()))
    return query.order_by(AnswerBank.updated_at.desc()).all()


@router.post("/answer-bank")
def create_answer(payload: AnswerBankCreate, db: Session = Depends(get_db)):
    item = AnswerBank(original_question=payload.original_question, normalized_question=payload.original_question.lower(), answer=payload.answer, confidence=payload.confidence, tags=payload.tags)
    db.add(item)
    db.commit()
    return item


@router.put("/answer-bank/{answer_id}")
def update_answer(answer_id: int, payload: AnswerBankCreate, db: Session = Depends(get_db)):
    item = db.get(AnswerBank, answer_id)
    if not item:
        raise HTTPException(404, "Answer not found")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    item.normalized_question = item.original_question.lower()
    db.commit()
    return item


@router.delete("/answer-bank/{answer_id}")
def delete_answer(answer_id: int, db: Session = Depends(get_db)):
    item = db.get(AnswerBank, answer_id)
    if not item:
        raise HTTPException(404, "Answer not found")
    db.delete(item)
    db.commit()
    return {"deleted": True}


@router.post("/answer-bank/search-similar")
def search_similar(payload: dict, db: Session = Depends(get_db)):
    needle = (payload.get("question") or "").lower()
    return db.query(AnswerBank).filter(AnswerBank.normalized_question.contains(needle[:30])).limit(5).all()


@router.get("/first-to-apply")
def first_to_apply(db: Session = Depends(get_db)):
    jobs = db.query(Job).options(joinedload(Job.score), joinedload(Job.application), joinedload(Job.answers), joinedload(Job.brief), joinedload(Job.interview_kit)).filter(Job.is_first_to_apply_candidate.is_(True)).order_by(Job.first_seen_at.asc()).all()
    return [serialize_job(job) for job in jobs]


@router.get("/easy-apply-ready")
def easy_apply_ready(db: Session = Depends(get_db)):
    jobs = db.query(Job).options(joinedload(Job.score), joinedload(Job.application), joinedload(Job.answers), joinedload(Job.brief), joinedload(Job.interview_kit)).filter(Job.apply_type.in_(["easy_apply", "quick_apply"])).order_by(Job.first_seen_at.asc()).all()
    return [serialize_job(job) for job in jobs]


@router.get("/analytics/summary")
def analytics_summary(db: Session = Depends(get_db)):
    return summary(db)


@router.get("/analytics/conversion-funnel")
def conversion_funnel(db: Session = Depends(get_db)):
    return [{"name": "Discovered", "value": db.query(Job).count()}, {"name": "Ready", "value": db.query(Job).filter(Job.status == "ready").count()}, {"name": "Applied", "value": db.query(Job).filter(Job.status == "applied").count()}]


@router.get("/analytics/platform-performance")
def platform_performance(db: Session = Depends(get_db)):
    return grouped(db, Job.platform)


@router.get("/analytics/answer-performance")
def answer_performance(db: Session = Depends(get_db)):
    return db.query(AnswerBank).order_by(AnswerBank.times_used.desc()).all()


@router.get("/analytics/learned-weights")
def learned_weights():
    return {"status": "collecting", "actions_required": 30, "weights": {"role_relevance": 0.30, "seniority": 0.20, "geography": 0.20, "domain": 0.15, "technology": 0.10, "freshness": 0.05}}


@router.get("/inbox")
def get_inbox():
    return get_recruiter_emails()


# ── Dashboard ──────────────────────────────────────────────────────────────

LARGE_CO_NAMES = [
    "google", "microsoft", "amazon", "meta", "apple", "ibm", "oracle", "sap",
    "accenture", "deloitte", "pwc", "kpmg", "ernst & young", "mckinsey", "bcg",
    "emirates", "etihad", "adnoc", "dp world", "emaar", "mubadala", "aldar",
    "mashreq", "enbd", "fab ", "first abu dhabi", "adib", "dewa", "du telecom",
    "bank of ireland", "allied irish", "aib bank", "crh ", "kerry group",
    "hsbc", "standard chartered", "citibank", "barclays", "bnp paribas",
    "morgan stanley", "goldman sachs", "jp morgan", "blackrock",
    "cognizant", "infosys", "tata ", "wipro", "capgemini", "atos",
]


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    load_opts = [joinedload(Job.score), joinedload(Job.application), joinedload(Job.brief)]
    skip = ["rejected", "skipped", "closed"]

    # Hot last hour — all jobs detected < 1 h, sorted by fit in Python
    raw_hot = (
        db.query(Job).options(*load_opts)
        .filter(Job.first_seen_at >= one_hour_ago)
        .filter(Job.status.notin_(skip))
        .all()
    )
    raw_hot.sort(key=lambda j: j.score.fit_score if j.score else 0, reverse=True)
    hot_last_hour = raw_hot[:12]

    # Easy apply
    easy_jobs = (
        db.query(Job).options(*load_opts)
        .filter(Job.apply_type.in_(["easy_apply", "quick_apply"]))
        .filter(Job.status.notin_(skip + ["applied"]))
        .order_by(Job.first_seen_at.desc()).limit(10).all()
    )

    # Company form / external
    form_jobs = (
        db.query(Job).options(*load_opts)
        .filter(Job.apply_type.notin_(["easy_apply", "quick_apply", "unknown"]))
        .filter(Job.status.notin_(skip + ["applied"]))
        .order_by(Job.first_seen_at.desc()).limit(10).all()
    )

    # Recruiter signals (fast track)
    signal_jobs = (
        db.query(Job).options(*load_opts)
        .filter(Job.fast_track.is_(True))
        .filter(Job.status.notin_(skip))
        .order_by(Job.first_seen_at.desc()).limit(8).all()
    )

    # Large companies — match on company name
    large_filter = or_(*[Job.company.ilike(f"%{n}%") for n in LARGE_CO_NAMES])
    large_co_jobs = (
        db.query(Job).options(*load_opts)
        .filter(large_filter)
        .filter(Job.company.notin_(["Unknown", ""]))
        .filter(Job.status.notin_(skip))
        .order_by(Job.first_seen_at.desc()).limit(10).all()
    )

    # Summary counts
    total_today = db.query(Job).filter(Job.first_seen_at >= today_start).count()
    applied_total = db.query(Job).filter(Job.status == "applied").count()
    total_all = db.query(Job).filter(Job.status.notin_(skip)).count()
    high_fit = (
        db.query(Job).join(JobScore, Job.id == JobScore.job_id)
        .filter(JobScore.fit_score >= 75)
        .filter(Job.status.notin_(skip + ["applied"])).count()
    )
    easy_count = db.query(Job).filter(
        Job.apply_type.in_(["easy_apply", "quick_apply"]),
        Job.status.notin_(skip + ["applied"])
    ).count()
    form_count = db.query(Job).filter(
        Job.apply_type.notin_(["easy_apply", "quick_apply", "unknown"]),
        Job.status.notin_(skip + ["applied"])
    ).count()
    fta_count = db.query(Job).filter(
        Job.is_first_to_apply_candidate.is_(True),
        Job.status.notin_(skip)
    ).count()
    followups_due = db.query(Application).filter(
        Application.status == "applied",
        Application.follow_up_date <= now
    ).count()

    return {
        "summary": {
            "total_today": total_today,
            "applied_total": applied_total,
            "total_active": total_all,
            "high_fit_pending": high_fit,
            "easy_apply_count": easy_count,
            "company_form_count": form_count,
            "first_to_apply_count": fta_count,
            "followups_due": followups_due,
        },
        "hot_last_hour": [serialize_job(j) for j in hot_last_hour],
        "easy_apply_jobs": [serialize_job(j) for j in easy_jobs],
        "company_form_jobs": [serialize_job(j) for j in form_jobs],
        "recruiter_signal_jobs": [serialize_job(j) for j in signal_jobs],
        "large_company_jobs": [serialize_job(j) for j in large_co_jobs],
    }


@router.get("/sources")
def sources(db: Session = Depends(get_db)):
    gmail = db.query(PlatformConnection).filter(PlatformConnection.platform == "Gmail").first()
    return [
        {"name": "Gmail job alerts", "status": gmail.status if gmail else "credentials_required", "frequency": "5m", "last_sync_at": gmail.last_sync_at if gmail else None, "sync_status": gmail.sync_status if gmail else "idle", "last_error": gmail.last_error if gmail else ""},
        {"name": "Manual import", "status": "active", "frequency": "on_demand", "last_sync_at": None, "sync_status": "idle", "last_error": ""},
        {"name": "Chrome extension browser assist", "status": "ready", "frequency": "user_action", "last_sync_at": None, "sync_status": "idle", "last_error": ""},
    ]


@router.post("/sources/gmail/connect")
def gmail_connect(db: Session = Depends(get_db)):
    return auth_url(db)


@router.get("/sources/gmail/callback", response_class=HTMLResponse)
def gmail_callback(code: str = Query(...), state: str = "", db: Session = Depends(get_db)):
    try:
        oauth_callback(db, code, state)
        return "<h1>Gmail connected</h1><p>You can close this tab and return to ApplyPilot AI.</p>"
    except Exception as exc:
        raise HTTPException(400, str(exc))


@router.post("/sources/gmail/disconnect")
def gmail_disconnect_route(db: Session = Depends(get_db)):
    return gmail_disconnect(db)


@router.post("/sources/gmail/sync")
def gmail_sync_route(db: Session = Depends(get_db)):
    return sync_gmail(db)


@router.get("/source-runs")
def source_runs(db: Session = Depends(get_db)):
    return db.query(SourceRun).order_by(SourceRun.started_at.desc()).limit(50).all()


@router.post("/sources/{source_id}/set-scan-frequency")
def set_frequency(source_id: int, payload: dict):
    return {"source_id": source_id, "frequency": payload.get("frequency", "60m")}


@router.get("/scheduler/status")
def scheduler_status():
    return {"running": False, "mode": "standard", "laptop_resume_catchup": True}


@router.post("/scheduler/run-now")
def run_now():
    return {"status": "started"}


@router.post("/ai/chat")
def ai_chat(payload: dict, db: Session = Depends(get_db)):
    question = payload.get("message", "")
    return answer_question(db, question)


@router.get("/notifications")
def notifications(db: Session = Depends(get_db)):
    jobs = db.query(Job).filter(Job.is_first_to_apply_candidate.is_(True)).all()
    return [{"type": "first_to_apply", "message": f"{job.title} - {job.country} - Fit {job.score.fit_score if job.score else 'n/a'}"} for job in jobs]


@router.get("/reports/export-csv")
def export_csv(db: Session = Depends(get_db)):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["job title", "company", "country", "platform", "source", "apply type", "fit score", "effort score", "freshness score", "match reason", "concerns", "status", "applied date", "follow-up date"])
    for job in db.query(Job).options(joinedload(Job.score), joinedload(Job.application)).all():
        writer.writerow([
            job.title,
            job.company,
            job.country,
            job.platform,
            job.source_policy,
            job.apply_type,
            job.score.fit_score if job.score else "",
            job.score.effort_score if job.score else "",
            job.score.freshness_score if job.score else "",
            job.score.match_reason if job.score else "",
            job.score.concerns if job.score else "",
            job.status,
            job.application.applied_date if job.application else "",
            job.application.follow_up_date if job.application else "",
        ])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=applypilot_jobs.csv"})


@router.get("/reports/export-excel")
def export_excel(db: Session = Depends(get_db)):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "ApplyPilot Jobs"
    headers = ["job title", "company", "country", "platform", "source", "apply type", "fit score", "effort score", "freshness score", "match reason", "concerns", "status", "applied date", "follow-up date"]
    ws.append(headers)
    for job in db.query(Job).options(joinedload(Job.score), joinedload(Job.application)).all():
        ws.append([
            job.title,
            job.company,
            job.country,
            job.platform,
            job.source_policy,
            job.apply_type,
            job.score.fit_score if job.score else "",
            job.score.effort_score if job.score else "",
            job.score.freshness_score if job.score else "",
            job.score.match_reason if job.score else "",
            job.score.concerns if job.score else "",
            job.status,
            job.application.applied_date.isoformat() if job.application and job.application.applied_date else "",
            job.application.follow_up_date.isoformat() if job.application and job.application.follow_up_date else "",
        ])
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=applypilot_jobs.xlsx"})
