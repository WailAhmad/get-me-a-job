from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class CandidateProfile(Base):
    __tablename__ = "candidate_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), default="ApplyPilot User")
    current_title: Mapped[str] = mapped_column(String(200), default="Senior AI and Data Leader")
    current_company: Mapped[str] = mapped_column(String(200), default="")
    location: Mapped[str] = mapped_column(String(120), default="Bahrain")
    email: Mapped[str] = mapped_column(String(200), default="")
    linkedin_url: Mapped[str] = mapped_column(String(500), default="")
    nationality: Mapped[str] = mapped_column(String(120), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    years_experience: Mapped[int] = mapped_column(Integer, default=15)
    core_skills_json: Mapped[str] = mapped_column(Text, default="[]")
    ai_experience_json: Mapped[str] = mapped_column(Text, default="[]")
    data_experience_json: Mapped[str] = mapped_column(Text, default="[]")
    cloud_platforms_json: Mapped[str] = mapped_column(Text, default="[]")
    governance_tools_json: Mapped[str] = mapped_column(Text, default="[]")
    industries_json: Mapped[str] = mapped_column(Text, default="[]")
    employers_json: Mapped[str] = mapped_column(Text, default="[]")
    education_json: Mapped[str] = mapped_column(Text, default="[]")
    certifications_json: Mapped[str] = mapped_column(Text, default="[]")
    major_achievements_json: Mapped[str] = mapped_column(Text, default="[]")
    profile_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PlatformConnection(Base):
    __tablename__ = "source_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(80), default="not_connected")
    auth_type: Mapped[str] = mapped_column(String(120), default="manual")
    allowed_capabilities_json: Mapped[str] = mapped_column(Text, default="[]")
    blocked_capabilities_json: Mapped[str] = mapped_column(Text, default="[]")
    account_hint: Mapped[str] = mapped_column(String(250), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    token_path: Mapped[str] = mapped_column(String(500), default="")
    sync_status: Mapped[str] = mapped_column(String(80), default="idle")
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SourceRun(Base):
    __tablename__ = "source_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(80), default="started")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), index=True)
    company: Mapped[str] = mapped_column(String(250), default="Unknown")
    country: Mapped[str] = mapped_column(String(120), index=True)
    city: Mapped[str] = mapped_column(String(120), default="")
    platform: Mapped[str] = mapped_column(String(120), index=True)
    source_policy: Mapped[str] = mapped_column(String(120), default="manual_import")
    source_email_id: Mapped[str] = mapped_column(String(250), default="")
    source_email_subject: Mapped[str] = mapped_column(String(500), default="")
    source_email_from: Mapped[str] = mapped_column(String(250), default="")
    apply_type: Mapped[str] = mapped_column(String(80), default="unknown")
    apply_url: Mapped[str] = mapped_column(String(1000), default="")
    job_url: Mapped[str] = mapped_column(String(1000), default="")
    requires_login: Mapped[bool] = mapped_column(Boolean, default=False)
    estimated_questions_count: Mapped[int] = mapped_column(Integer, default=0)
    application_complexity: Mapped[str] = mapped_column(String(80), default="medium")
    manual_submit_required: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str] = mapped_column(Text, default="")
    description_summary: Mapped[str] = mapped_column(Text, default="")
    detected_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    posted_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    seniority: Mapped[str] = mapped_column(String(120), default="senior")
    role_category: Mapped[str] = mapped_column(String(120), default="AI Leadership")
    employment_type: Mapped[str] = mapped_column(String(80), default="full-time")
    work_mode: Mapped[str] = mapped_column(String(80), default="hybrid")
    status: Mapped[str] = mapped_column(String(80), default="discovered", index=True)
    is_first_to_apply_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    first_to_apply_reason: Mapped[str] = mapped_column(Text, default="")
    notification_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_prepared_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    jd_quality_score: Mapped[int] = mapped_column(Integer, default=50)
    recruiter_signals_json: Mapped[str] = mapped_column(Text, default="{}")
    fast_track: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    score: Mapped["JobScore"] = relationship(back_populates="job", cascade="all, delete-orphan", uselist=False)
    application: Mapped["Application"] = relationship(back_populates="job", cascade="all, delete-orphan", uselist=False)
    answers: Mapped[list["ApplicationAnswer"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    brief: Mapped["CompanyBrief"] = relationship(back_populates="job", cascade="all, delete-orphan", uselist=False)
    interview_kit: Mapped["InterviewKit"] = relationship(back_populates="job", cascade="all, delete-orphan", uselist=False)


class JobScore(Base):
    __tablename__ = "job_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True)
    fit_score: Mapped[int] = mapped_column(Integer, default=0)
    effort_score: Mapped[int] = mapped_column(Integer, default=0)
    freshness_score: Mapped[int] = mapped_column(Integer, default=0)
    match_reason: Mapped[str] = mapped_column(Text, default="")
    concerns: Mapped[str] = mapped_column(Text, default="")
    recommendation: Mapped[str] = mapped_column(Text, default="")
    learned_weight_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped[Job] = relationship(back_populates="score")


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True)
    status: Mapped[str] = mapped_column(String(80), default="prepared")
    prepared_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    applied_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    follow_up_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    follow_up_stage: Mapped[str] = mapped_column(String(80), default="not_started")
    cv_version: Mapped[str] = mapped_column(String(160), default="AI Strategy")
    cover_letter: Mapped[str] = mapped_column(Text, default="")
    outreach_message: Mapped[str] = mapped_column(Text, default="")
    outreach_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome: Mapped[str] = mapped_column(String(80), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped[Job] = relationship(back_populates="application")


class ApplicationAnswer(Base):
    __tablename__ = "application_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    question_text: Mapped[str] = mapped_column(Text)
    normalized_question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(80), default="Medium")
    source: Mapped[str] = mapped_column(String(120), default="cv_profile")
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped[Job] = relationship(back_populates="answers")


class AnswerBank(Base):
    __tablename__ = "answer_bank"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_question: Mapped[str] = mapped_column(Text)
    normalized_question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(80), default="High")
    source: Mapped[str] = mapped_column(String(120), default="user")
    reusable: Mapped[bool] = mapped_column(Boolean, default=True)
    tags: Mapped[str] = mapped_column(Text, default="")
    times_used: Mapped[int] = mapped_column(Integer, default=0)
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome_signal: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CompanyBrief(Base):
    __tablename__ = "company_briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True)
    company_name: Mapped[str] = mapped_column(String(250))
    recent_news: Mapped[str] = mapped_column(Text, default="")
    leadership_names: Mapped[str] = mapped_column(Text, default="")
    tech_stack_signals: Mapped[str] = mapped_column(Text, default="")
    ai_initiatives: Mapped[str] = mapped_column(Text, default="")
    sector_context: Mapped[str] = mapped_column(Text, default="")
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped[Job] = relationship(back_populates="brief")


class InterviewKit(Base):
    __tablename__ = "interview_kits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True)
    predicted_questions_json: Mapped[str] = mapped_column(Text, default="[]")
    suggested_answers_json: Mapped[str] = mapped_column(Text, default="[]")
    company_questions_json: Mapped[str] = mapped_column(Text, default="[]")
    cheat_sheet: Mapped[str] = mapped_column(Text, default="")
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped[Job] = relationship(back_populates="interview_kit")


class BehaviourLog(Base):
    __tablename__ = "user_behaviour_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[Optional[int]] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    action_type: Mapped[str] = mapped_column(String(80))
    action_value: Mapped[str] = mapped_column(String(200), default="")
    rejection_reason: Mapped[str] = mapped_column(String(200), default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
