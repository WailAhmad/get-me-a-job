import json

from app.core.config import settings
from app.models.entities import AnswerBank, CandidateProfile, Job, PlatformConnection
from app.services.scoring import detect_apply_type, first_to_apply_eligible, score_job
from app.models.entities import JobScore


def seed(db):
    seed_connections(db)
    seed_profile(db)
    seed_answer_bank(db)
    if not settings.seed_demo_data:
        db.commit()
        return
    if db.query(Job).count():
        db.commit()
        return
    samples = [
        Job(
            title="Head of AI Strategy",
            company="Gulf Digital Authority",
            country="Qatar",
            platform="Gmail Alert",
            apply_type="easy_apply",
            job_url="",
            description="Urgent hire for Head of AI with Azure, Databricks, governance, public sector transformation, LLM and RAG experience. Salary package disclosed. Hiring manager named.",
        ),
        Job(
            title="Principal Data Architect",
            company="Banking Group",
            country="UAE",
            platform="Manual Import",
            apply_type="company_form",
            job_url="",
            description="Senior principal data architecture role across AWS, Snowflake, Fabric, data governance, regulated financial services and analytics transformation.",
        ),
        Job(
            title="GenAI Product Lead",
            company="Telecom Innovation Lab",
            country="Saudi Arabia",
            platform="RSS",
            apply_type="quick_apply",
            job_url="",
            description="Immediate start. Lead GenAI product delivery, LLM, RAG, agentic AI platforms, Azure, stakeholder alignment, enterprise technology and telecom sector delivery.",
        ),
    ]
    for job in samples:
        job.apply_type = detect_apply_type(job) if job.apply_type == "unknown" else job.apply_type
        scores = score_job(job)
        job.jd_quality_score = scores["jd_quality_score"]
        job.fast_track = scores["fast_track"]
        db.add(job)
        db.flush()
        eligible, reason = first_to_apply_eligible(job, scores["fit_score"], scores["effort_score"])
        job.is_first_to_apply_candidate = eligible
        job.first_to_apply_reason = reason
        db.add(JobScore(job_id=job.id, **{k: scores[k] for k in ["fit_score", "effort_score", "freshness_score", "match_reason", "concerns", "recommendation"]}))
    db.commit()


def seed_answer_bank(db):
    if db.query(AnswerBank).count():
        return
    db.add(AnswerBank(original_question="Describe your AI leadership experience.", normalized_question="describe your ai leadership experience", answer="I have led AI and data transformation across strategy, governance, architecture, and production delivery.", tags="leadership,ai"))


def seed_profile(db):
    if db.query(CandidateProfile).count():
        return
    db.add(CandidateProfile(
        full_name="Wael",
        current_title="Senior AI and Data Leader",
        location="Bahrain",
        years_experience=15,
        profile_json=json.dumps({
            "target_countries": ["Bahrain", "Saudi Arabia", "UAE", "Qatar", "Kuwait", "Oman", "Ireland"],
            "target_roles": ["Head of AI", "Director of AI", "AI Product Lead", "Principal Data Architect", "GenAI Lead"],
            "core_skills": ["AI strategy", "data architecture", "governance", "LLM", "RAG", "Databricks", "Azure", "AWS"]
        })
    ))


def seed_connections(db):
    if db.query(PlatformConnection).count():
        return
    safe_browser = ["Open user-provided URLs", "Read current page with user action", "Prepare answers", "Chrome extension field fill", "Manual submit only"]
    blocked = ["Auto-submit", "Bulk apply", "Credential capture", "Restricted scraping", "Bypass rate limits"]
    connections = [
        PlatformConnection(
            platform="Gmail",
            status="credentials_required",
            auth_type="OAuth 2.0",
            allowed_capabilities_json=json.dumps(["Read job alert emails with permission", "Parse job alerts", "Sync source history"]),
            blocked_capabilities_json=json.dumps(["Read non-job email without filters"]),
            notes="Configure Google OAuth credentials to ingest LinkedIn, Indeed, NaukriGulf, Bayt, GulfTalent, and ATS job alerts from Gmail.",
        ),
        PlatformConnection(
            platform="LinkedIn",
            status="browser_assist_ready",
            auth_type="User browser session only",
            allowed_capabilities_json=json.dumps(safe_browser),
            blocked_capabilities_json=json.dumps(blocked),
            notes="LinkedIn personal jobseeker account automation is not supported. Use job alerts, manual URLs, and the extension on pages you open yourself.",
        ),
        PlatformConnection(
            platform="Indeed",
            status="browser_assist_ready",
            auth_type="User browser session only",
            allowed_capabilities_json=json.dumps(safe_browser),
            blocked_capabilities_json=json.dumps(blocked),
            notes="Indeed partner APIs are not a personal jobseeker account feed. Use job alerts, manual imports, and extension-assisted form fill.",
        ),
        PlatformConnection(
            platform="NaukriGulf",
            status="browser_assist_ready",
            auth_type="User browser session only",
            allowed_capabilities_json=json.dumps(safe_browser),
            blocked_capabilities_json=json.dumps(blocked),
            notes="Use job alert email ingestion, manual URL import, and extension-assisted form fill on pages you open.",
        ),
    ]
    for connection in connections:
        db.add(connection)
