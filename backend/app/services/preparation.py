from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.entities import Application, ApplicationAnswer, CandidateProfile, CompanyBrief, InterviewKit, Job


DEFAULT_QUESTIONS = [
    "Why are you interested in this role?",
    "Describe your relevant AI and data leadership experience.",
    "What is your notice period?",
]
SENSITIVE = {"salary", "visa", "relocation", "work authorization", "notice"}


def _profile(db: Session) -> CandidateProfile | None:
    return db.query(CandidateProfile).first()


def _list(value: str) -> list[str]:
    try:
        return json.loads(value or "[]")
    except Exception:
        return []


def select_cv_version(job: Job) -> str:
    text = f"{job.title} {job.description}".lower()
    if "public sector" in text or "government" in text or "sovereign" in text:
        return "Public Sector AI"
    if "genai" in text or "product" in text or "llm" in text:
        return "GenAI Product"
    if "bank" in text or "financial" in text:
        return "Financial Services"
    if "architecture" in text or "platform" in text:
        return "Data Architecture"
    return "AI Strategy"


def generate_company_brief(db: Session, job: Job) -> CompanyBrief:
    brief = job.brief or CompanyBrief(job_id=job.id, company_name=job.company)
    text = job.description.lower()
    stack = ", ".join(term for term in ["Azure", "AWS", "Databricks", "Snowflake", "Fabric", "RAG", "LLM"] if term.lower() in text) or "Not explicit in JD"
    brief.recent_news = "Web search integration is configured as a safe extension point; this MVP uses JD-only context until enabled."
    brief.leadership_names = "Not identified from the job description."
    brief.tech_stack_signals = stack
    brief.ai_initiatives = "AI/data transformation signals inferred from the role requirements."
    brief.sector_context = f"{job.country} market context for {job.role_category} roles."
    brief.generated_at = datetime.utcnow()
    db.add(brief)
    return brief


def generate_answers(db: Session, job: Job) -> list[ApplicationAnswer]:
    if job.answers:
        return job.answers
    profile = _profile(db)
    title = profile.current_title if profile else "senior AI and data leader"
    years = profile.years_experience if profile else 15
    skills = ", ".join((_list(profile.core_skills_json) if profile else [])[:8]) or "AI strategy, data architecture, governance, cloud data platforms, LLM and RAG delivery"
    achievements = _list(profile.major_achievements_json) if profile else []
    achievement_line = achievements[0] if achievements else "I have led enterprise AI and data transformation from strategy through governed production delivery."
    answers: list[ApplicationAnswer] = []
    for question in DEFAULT_QUESTIONS:
        ql = question.lower()
        needs_review = any(term in ql for term in SENSITIVE)
        answer = (
            f"I bring {years}+ years as a {title}, with strengths across {skills}. "
            f"For {job.company}, I would focus on the role's highest-impact outcomes: governed delivery, measurable adoption, and practical AI/data execution. "
            f"Relevant evidence from my background: {achievement_line}"
        )
        if needs_review:
            answer = "Needs user review before use."
        item = ApplicationAnswer(
            job_id=job.id,
            question_text=question,
            normalized_question=ql,
            answer=answer,
            confidence="High" if not needs_review else "Needs Review",
            needs_review=needs_review,
        )
        db.add(item)
        answers.append(item)
    return answers


def cover_letter(job: Job) -> str:
    # The generated text is deterministic and local; users review before copying.
    return (
        f"Dear Hiring Team,\n\n"
        f"I am interested in the {job.title} role at {job.company}. The opportunity stands out because it combines senior AI leadership, data platform execution, and measurable enterprise impact in {job.country}.\n\n"
        "Across 15+ years in AI, data architecture, engineering, governance, and analytics transformation, I have led cross-functional teams through strategy, platform modernization, and delivery of production-grade data and AI capabilities. My background spans executive stakeholder alignment, cloud data platforms, responsible AI governance, and practical adoption of LLM and RAG patterns.\n\n"
        "I would bring a pragmatic leadership style: clarify the business outcome, establish the right architecture and operating model, and ship capabilities that can be governed, measured, and improved. I would welcome the chance to discuss how my experience can support your AI and data priorities.\n\n"
        "Kind regards"
    )


def outreach(job: Job) -> str:
    return (
        f"Hi, I saw the {job.title} role at {job.company}. My background spans 15+ years in AI strategy, data architecture, and enterprise transformation across regulated sectors. "
        "The role looks closely aligned, and I would value connecting."
    )[:300]


def generate_interview_kit(db: Session, job: Job) -> InterviewKit:
    kit = job.interview_kit or InterviewKit(job_id=job.id)
    questions = [
        f"How would you define the first 90 days for {job.title}?",
        "How have you governed AI delivery in regulated environments?",
        "Describe a data platform transformation you led.",
        "How do you move GenAI from proof of concept to production?",
        "How do you align executive stakeholders around AI investment?",
        "What metrics would you use to prove impact?",
        "How do you handle model risk and responsible AI?",
        "How would you structure the team?",
        "Which cloud/data stack tradeoffs matter most here?",
        "Why this company and market?",
    ]
    kit.predicted_questions_json = json.dumps(questions)
    kit.suggested_answers_json = json.dumps(["Use CV achievements, company context, and quantified delivery outcomes." for _ in questions])
    kit.company_questions_json = json.dumps([
        "What AI initiatives are highest priority this year?",
        "Where are the biggest data platform constraints today?",
        "How will success be measured for this role?",
    ])
    kit.cheat_sheet = f"{job.company} | {job.title} | {job.country} | Apply type: {job.apply_type}"
    kit.generated_at = datetime.utcnow()
    db.add(kit)
    return kit


def prepare_job(db: Session, job: Job) -> Application:
    generate_company_brief(db, job)
    generate_answers(db, job)
    app = job.application or Application(job_id=job.id)
    app.status = "prepared"
    app.prepared_date = datetime.utcnow()
    app.follow_up_date = datetime.utcnow() + timedelta(days=7)
    app.cv_version = select_cv_version(job)
    app.cover_letter = cover_letter(job)
    app.outreach_message = outreach(job)
    job.status = "ready"
    job.auto_prepared_at = datetime.utcnow()
    db.add(app)
    db.add(job)
    db.flush()
    return app
