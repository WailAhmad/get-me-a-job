"""Answer a free-text Easy Apply screening question using the user's profile.

Returns:
    {
      "answer":     "the value to type / select",
      "confidence": 0..100,
      "kind":       "text" | "number" | "yes_no" | "select",
      "reasoning":  "one sentence"
    }

Confidence < 70 → caller should route the question to the Pending Review
queue rather than guess.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agent.ai.provider import get_provider
from agent.logger import get_logger

log = get_logger("ai.qa")


@dataclass
class AnsweredQuestion:
    answer: str
    confidence: int
    kind: str
    reasoning: str
    raw: Dict[str, Any]


_SYSTEM_PROMPT = """\
You are filling out a job application on behalf of the candidate.

You will receive: the candidate's profile, the application question, and any
options if it's a multiple-choice/dropdown question.

Rules:
- Be honest. Do not invent qualifications the candidate doesn't have.
- Be brief — answers go into form fields, not essays.
- For yes/no questions, prefer "Yes" or "No" exactly.
- For numeric questions (years of experience, salary), answer with a clean number.
- For dropdowns, pick the option whose text is closest to the right answer.
- If you're not sure, set confidence below 70 and explain why in `reasoning`.

Return STRICT JSON:
{
  "answer":     "<string the user will type or select>",
  "confidence": <int 0..100>,
  "kind":       "text" | "number" | "yes_no" | "select",
  "reasoning":  "<one sentence>"
}
"""


def answer_question(profile: Dict[str, Any], question: str,
                    *, options: Optional[List[str]] = None,
                    job_title: str | None = None,
                    job_company: str | None = None) -> AnsweredQuestion:
    """Generate one answer, with confidence."""
    provider = get_provider()
    payload = {
        "candidate": {
            "identity":    profile.get("identity") or {},
            "profile":     profile.get("profile") or {},
            "preferences": profile.get("preferences") or {},
        },
        "question": question,
        "options":  options or [],
        "job":      {"title": job_title, "company": job_company},
    }
    raw = provider.chat_json(
        system=_SYSTEM_PROMPT,
        user=json.dumps(payload, ensure_ascii=False),
        max_tokens=300,
        temperature=0.1,
    )
    answer = str(raw.get("answer") or "").strip()
    conf = int(max(0, min(100, raw.get("confidence", 0))))
    out = AnsweredQuestion(
        answer=answer,
        confidence=conf,
        kind=str(raw.get("kind") or "text"),
        reasoning=str(raw.get("reasoning") or "").strip(),
        raw=raw,
    )
    log.info("Q='%s'  →  '%s' (%d%%)", question[:60], answer[:40], conf)
    return out


def is_confident(answered: AnsweredQuestion, threshold: int = 70) -> bool:
    return answered.confidence >= threshold and bool(answered.answer)
