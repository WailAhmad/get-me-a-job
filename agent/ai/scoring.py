"""Match-score a job description against the user's profile.

Returns an int 0–100 plus a one-line rationale and a small structured
breakdown. The agent only proceeds with Easy Apply when score >= 85.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agent.ai.provider import get_provider
from agent.logger import get_logger

log = get_logger("ai.score")


@dataclass
class MatchResult:
    score: int                  # 0–100
    rationale: str              # one sentence
    matched_skills: List[str]
    missing_skills: List[str]
    title_alignment: str        # "exact" | "adjacent" | "stretch" | "off"
    seniority_alignment: str    # "match" | "above" | "below"
    raw: Dict[str, Any]


_SYSTEM_PROMPT = """\
You are a recruiter screening a candidate against a job description.

Score the FIT between the candidate profile and the job description on a 0–100 scale.
Be strict and calibrated:
- 90–100: candidate is a clearly strong fit (title, seniority, must-have skills all align).
- 80–89: strong match with 1–2 minor gaps.
- 70–79: directionally relevant but missing important requirements.
- 60–69: tangential — same domain/seniority but wrong specialty.
- <60: weak or off-target.

Penalize seniority mismatches heavily. Reward exact title and tool overlap.
Treat soft requirements (preferred / nice-to-have) as worth half.

Return STRICT JSON:
{
  "score": <int 0..100>,
  "rationale": "<one sentence>",
  "matched_skills":   ["..."],
  "missing_skills":   ["..."],
  "title_alignment":      "exact" | "adjacent" | "stretch" | "off",
  "seniority_alignment":  "match"  | "above"    | "below"
}
"""


def _user_payload(profile: Dict[str, Any], job: Dict[str, Any]) -> str:
    p = profile or {}
    payload = {
        "candidate": {
            "headline":         (p.get("profile") or {}).get("headline"),
            "current_title":    (p.get("profile") or {}).get("current_title"),
            "years_experience": (p.get("profile") or {}).get("years_experience"),
            "skills":           (p.get("profile") or {}).get("skills") or [],
            "summary":          (p.get("profile") or {}).get("summary"),
            "targets":          p.get("targets") or {},
        },
        "job": {
            "title":       job.get("title"),
            "company":     job.get("company"),
            "location":    job.get("location"),
            "description": (job.get("description") or "")[:6000],   # keep prompt small
            "easy_apply":  bool(job.get("easy_apply")),
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def score_job(profile: Dict[str, Any], job: Dict[str, Any]) -> MatchResult:
    """Return a calibrated match score with diagnostics."""
    provider = get_provider()
    raw = provider.chat_json(
        system=_SYSTEM_PROMPT,
        user=_user_payload(profile, job),
        max_tokens=400,
        temperature=0.0,
    )
    score = int(max(0, min(100, raw.get("score", 0))))
    result = MatchResult(
        score=score,
        rationale=str(raw.get("rationale") or "").strip(),
        matched_skills=list(raw.get("matched_skills") or []),
        missing_skills=list(raw.get("missing_skills") or []),
        title_alignment=str(raw.get("title_alignment") or "off"),
        seniority_alignment=str(raw.get("seniority_alignment") or "match"),
        raw=raw,
    )
    log.info("scored %s @ %s = %d  (%s)", job.get("title"), job.get("company"),
             result.score, result.title_alignment)
    return result


def passes_threshold(result: MatchResult, threshold: int = 85) -> bool:
    return result.score >= threshold
