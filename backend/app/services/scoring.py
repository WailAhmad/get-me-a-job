from datetime import datetime, timezone
import re

from app.models.entities import Job

TARGET_COUNTRIES = {"bahrain", "saudi arabia", "uae", "qatar", "kuwait", "oman", "ireland"}
ROLE_TERMS = {"ai", "data", "genai", "llm", "analytics", "architecture", "architect", "director", "head", "lead"}
TECH_TERMS = {"azure", "aws", "databricks", "synapse", "snowflake", "fabric", "collibra", "purview", "rag", "llm"}
DOMAIN_TERMS = {"government", "public sector", "telecom", "financial", "banking", "enterprise", "law enforcement"}
URGENCY_TERMS = {"immediate start", "backfill", "urgent", "asap", "confidential search", "retained search", "reposted"}


def _text(job: Job) -> str:
    return f"{job.title} {job.company} {job.description}".lower()


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def detect_apply_type(job: Job) -> str:
    text = f"{job.job_url} {job.apply_url} {job.description} {job.platform}".lower()
    if "easy apply" in text or "linkedin" in text and "easy" in text:
        return "easy_apply"
    if any(vendor in text for vendor in ["workday", "greenhouse", "lever", "successfactors", "sap"]):
        return "company_form"
    if job.apply_url or job.job_url:
        return "external_apply"
    return "unknown"


def jd_quality(job: Job) -> tuple[int, list[str]]:
    text = _text(job)
    score = 35
    reasons: list[str] = []
    if job.company and job.company.lower() != "unknown":
        score += 15
    else:
        reasons.append("company not fully named")
    if re.search(r"\b(salary|compensation|package|benefits)\b", text):
        score += 10
    if len(job.description) > 1200:
        score += 20
    elif len(job.description) < 350:
        score -= 15
        reasons.append("thin job description")
    if len(_tokens(text) & (ROLE_TERMS | TECH_TERMS)) + sum(1 for term in DOMAIN_TERMS if term in text) >= 6:
        score += 15
    if text.count(",") > 45 or "rockstar" in text or "ninja" in text:
        score -= 10
        reasons.append("possible buzzword overload")
    return max(0, min(100, score)), reasons


def recruiter_signals(job: Job) -> dict:
    text = _text(job)
    urgency = [term for term in URGENCY_TERMS if term in text]
    access = []
    if re.search(r"[\w.-]+@[\w.-]+\.\w+", text):
        access.append("recruiter email visible")
    if "hiring manager" in text:
        access.append("hiring manager named")
    quality = []
    if "salary" in text or "package" in text:
        quality.append("salary signal")
    if len(job.description) > 1000:
        quality.append("detailed JD")
    return {"urgency": urgency, "access": access, "quality": quality}


def score_job(job: Job) -> dict:
    text = _text(job)
    tokens = _tokens(text)
    role_hits = len(tokens & ROLE_TERMS)
    tech_hits = len(tokens & TECH_TERMS)
    domain_hits = sum(1 for term in DOMAIN_TERMS if term in text)
    country_score = 100 if job.country.lower() in TARGET_COUNTRIES else 30
    seniority_score = 95 if any(term in text for term in ["head", "director", "principal", "lead", "senior"]) else 60
    role_score = min(100, 35 + role_hits * 10)
    tech_score = min(100, 30 + tech_hits * 9)
    domain_score = min(100, 40 + domain_hits * 15)
    freshness_score = freshness(job)
    fit = round(role_score * 0.30 + seniority_score * 0.20 + country_score * 0.20 + domain_score * 0.15 + tech_score * 0.10 + freshness_score * 0.05)
    effort = effort_score(job)
    quality, concerns = jd_quality(job)
    if quality < 45:
        fit = max(0, fit - 8)
    signals = recruiter_signals(job)
    fast_track = bool(signals["urgency"] or signals["access"])
    return {
        "fit_score": fit,
        "effort_score": effort,
        "freshness_score": freshness_score,
        "jd_quality_score": quality,
        "signals": signals,
        "fast_track": fast_track,
        "match_reason": ", ".join(
            reason
            for reason in [
                f"{role_hits} role keyword hits" if role_hits else "",
                f"{tech_hits} technology matches" if tech_hits else "",
                f"{domain_hits} sector signals" if domain_hits else "",
                "target geography" if country_score == 100 else "",
            ]
            if reason
        ),
        "concerns": "; ".join(concerns),
        "recommendation": "Sprint now" if fit >= 80 and effort >= 60 else "Review in workspace",
    }


def freshness(job: Job) -> int:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    first_seen = job.first_seen_at or now
    hours = max(0.0, (now - first_seen).total_seconds() / 3600)
    if hours <= 2:
        return 100
    if hours <= 24:
        return 85
    if hours <= 24 * 7:
        return 60
    if hours <= 24 * 21:
        return 30
    return 10


def effort_score(job: Job) -> int:
    score = 35
    question_count = job.estimated_questions_count or 0
    if job.apply_type == "easy_apply":
        score += 35
    if question_count == 0:
        score += 25
    elif question_count < 5:
        score += 15
    if "cover letter" not in job.description.lower():
        score += 10
    if "salary" not in job.description.lower():
        score += 5
    if "visa" not in job.description.lower() and "relocation" not in job.description.lower():
        score += 5
    if job.apply_type == "company_form":
        score -= 25
    if (job.company or "Unknown").lower() == "unknown":
        score -= 10
    if (job.jd_quality_score or 50) < 45:
        score -= 10
    return max(0, min(100, score))


def first_to_apply_eligible(job: Job, fit_score: int, effort: int) -> tuple[bool, str]:
    is_fresh = freshness(job) == 100
    country_ok = job.country.lower() in TARGET_COUNTRIES
    eligible = is_fresh and fit_score >= 80 and effort >= 60 and country_ok
    reason = "Detected within 2 hours, high fit, high effort score, target country" if eligible else ""
    return eligible, reason
