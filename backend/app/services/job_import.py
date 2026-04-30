from __future__ import annotations

import hashlib
import re
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.entities import CandidateProfile, Job
from app.services.preparation import prepare_job
from app.services.scoring import first_to_apply_eligible, score_job

PLATFORMS = ["LinkedIn", "Bayt", "GulfTalent", "IrishJobs", "Workday", "Greenhouse", "Lever"]


def parse_job_text(text: str, url: str = "", platform_hint: str = "") -> dict:
    compact = re.sub(r"\s+", " ", text).strip()
    title = _extract_label(text, ["job title", "title", "role"]) or _guess_title(text)
    company = _extract_label(text, ["company", "employer", "organization", "organisation"]) or _guess_company(text, url)
    country = _extract_country(text) or "Bahrain"
    platform = platform_hint or _platform_from(url, text)
    found_url = url or _first_url(text)
    return {
        "title": title or "Imported Job",
        "company": company or "Unknown",
        "country": country,
        "platform": platform,
        "job_url": found_url,
        "apply_url": found_url,
        "description": compact[:20000],
    }


def create_or_update_job(db: Session, data: dict, source: dict | None = None, auto_prepare: bool = True) -> tuple[Job, bool]:
    source = source or {}
    existing = _find_duplicate(db, data)
    is_duplicate = existing is not None
    job = existing or Job()
    for key in ["title", "company", "country", "platform", "job_url", "apply_url", "description"]:
        value = data.get(key)
        if value:
            setattr(job, key, value)
    job.source_policy = source.get("source_policy", job.source_policy or "manual_import")
    job.source_email_id = source.get("source_email_id", job.source_email_id or "")
    job.source_email_subject = source.get("source_email_subject", job.source_email_subject or "")
    job.source_email_from = source.get("source_email_from", job.source_email_from or "")
    job.last_seen_at = datetime.utcnow()
    db.add(job)
    db.flush()
    scores = _apply_scores(db, job)
    scores = _apply_profile_signal(db, job, scores)
    if auto_prepare and scores["fit_score"] >= 70:
        prepare_job(db, job)
    return job, is_duplicate


def _apply_scores(db: Session, job: Job) -> dict:
    from app.models.entities import JobScore
    from app.services.scoring import detect_apply_type

    job.apply_type = detect_apply_type(job)
    scores = score_job(job)
    job.jd_quality_score = scores["jd_quality_score"]
    job.fast_track = scores["fast_track"]
    eligible, reason = first_to_apply_eligible(job, scores["fit_score"], scores["effort_score"])
    job.is_first_to_apply_candidate = eligible
    job.first_to_apply_reason = reason
    existing = job.score or JobScore(job_id=job.id)
    for key in ["fit_score", "effort_score", "freshness_score", "match_reason", "concerns", "recommendation"]:
        setattr(existing, key, scores[key])
    db.add(job)
    db.add(existing)
    return scores


def _apply_profile_signal(db: Session, job: Job, scores: dict) -> dict:
    import json

    profile = db.query(CandidateProfile).first()
    if not profile or not job.score:
        return scores
    terms: list[str] = []
    for raw in [profile.core_skills_json, profile.ai_experience_json, profile.data_experience_json, profile.cloud_platforms_json, profile.governance_tools_json, profile.industries_json]:
        try:
            terms.extend(json.loads(raw or "[]"))
        except Exception:
            continue
    text = f"{job.title} {job.description}".lower()
    hits = sorted({term for term in terms if term and term.lower() in text})
    if hits:
        bonus = min(10, len(hits) * 2)
        job.score.fit_score = min(100, job.score.fit_score + bonus)
        job.score.match_reason = f"{job.score.match_reason}; profile matches: {', '.join(hits[:6])}"
        eligible, reason = first_to_apply_eligible(job, job.score.fit_score, job.score.effort_score)
        job.is_first_to_apply_candidate = eligible
        job.first_to_apply_reason = reason
        scores["fit_score"] = job.score.fit_score
        scores["match_reason"] = job.score.match_reason
    return scores


def _find_duplicate(db: Session, data: dict) -> Job | None:
    url = data.get("job_url") or data.get("apply_url")
    if url:
        found = db.query(Job).filter((Job.job_url == url) | (Job.apply_url == url)).first()
        if found:
            return found
    title = (data.get("title") or "").strip().lower()
    company = (data.get("company") or "").strip().lower()
    if title and company:
        for job in db.query(Job).all():
            if job.title.lower().strip() == title and job.company.lower().strip() == company:
                return job
    return None


def _extract_label(text: str, labels: list[str]) -> str:
    for label in labels:
        match = re.search(rf"^\s*{re.escape(label)}\s*[:\-]\s*(.+)$", text, flags=re.I | re.M)
        if match:
            return match.group(1).strip()[:250]
    return ""


def _guess_title(text: str) -> str:
    for line in text.splitlines()[:20]:
        clean = line.strip(" -|\t")
        if 5 <= len(clean) <= 120 and re.search(r"\b(ai|data|architect|director|head|lead|manager|engineer|analyst|product)\b", clean, re.I):
            return clean
    return ""


def _guess_company(text: str, url: str) -> str:
    match = re.search(r"(?:at|company)\s+([A-Z][A-Za-z0-9& ]{2,60}?)(?:[.,\n]|$)", text)
    if match:
        return match.group(1).strip()
    host = urlparse(url).hostname or ""
    if host and not any(p.lower() in host.lower() for p in PLATFORMS):
        return host.replace("www.", "").split(".")[0].title()
    return ""


def _extract_country(text: str) -> str:
    for item in ["Bahrain", "Saudi Arabia", "UAE", "United Arab Emirates", "Qatar", "Kuwait", "Oman", "Ireland"]:
        if re.search(rf"\b{re.escape(item)}\b", text, re.I):
            return "UAE" if item == "United Arab Emirates" else item
    return ""


def _platform_from(url: str, text: str) -> str:
    blob = f"{url} {text}".lower()
    for platform in PLATFORMS:
        if platform.lower() in blob:
            return platform
    host = urlparse(url).hostname or ""
    return host.replace("www.", "").split(".")[0].title() if host else "Manual"


def _first_url(text: str) -> str:
    match = re.search(r"https?://[^\s<>\")]+", text)
    return match.group(0).rstrip(".,") if match else ""


def fingerprint(data: dict) -> str:
    raw = "|".join((data.get(k) or "").lower().strip() for k in ["title", "company", "country", "job_url"])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
