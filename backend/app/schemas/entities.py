from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class JobCreate(BaseModel):
    title: str
    company: str = "Unknown"
    country: str = "Bahrain"
    platform: str = "manual"
    description: str = ""
    job_url: str = ""
    apply_url: str = ""


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    company: str
    country: str
    platform: str
    apply_type: str
    job_url: str
    status: str
    is_first_to_apply_candidate: bool
    fast_track: bool
    jd_quality_score: int
    first_seen_at: datetime


class JobDetail(JobRead):
    description: str
    description_summary: str


class ImportTextRequest(BaseModel):
    title: str = "Imported Role"
    company: str = "Unknown"
    country: str = "Bahrain"
    platform: str = "manual"
    description: str
    job_url: str = ""


class RejectRequest(BaseModel):
    rejection_reason: str = "other"


class OutcomeRequest(BaseModel):
    outcome: str


class BehaviourRequest(BaseModel):
    job_id: Optional[int] = None
    action_type: str
    action_value: str = ""
    rejection_reason: str = ""


class AnswerBankCreate(BaseModel):
    original_question: str
    answer: str
    confidence: str = "High"
    tags: str = ""
