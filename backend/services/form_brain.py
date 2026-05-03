"""
Form Brain — AI-first form answering.

Strategy:
- Take a structured snapshot of the entire current form step (all fields,
  all options, current values, validation errors).
- Send ONE rich LLM call that returns answers for ALL fields together.
- The LLM sees full context (other fields, page title, error messages),
  so it can pick EXACT option text for selects/radios, choose the right
  type-coercion (integer vs text), and recover from validation errors
  on retry.

Resolution chain inside the brain:
    1. Profile / CV direct fields           — instant, free
    2. Answers bank (exact + fuzzy match)   — instant, free
    3. LLM (uploaded-CV context)            — ~1.5s, accurate
    4. Pending                              — only when LLM is uncertain
                                              about TRULY personal data

The LLM call is structured: we send a JSON list of fields with their types
and option lists, and we get back a JSON list of answers. This means every
select/radio answer is GUARANTEED to be one of the available options
(picked by the LLM character-for-character), eliminating fuzzy-match
failures like "Native or bilingual" vs "Native / Bilingual".
"""
from __future__ import annotations

import json
import logging
import re
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Profile-first heuristics  (fast path, no LLM call)
# ────────────────────────────────────────────────────────────────────────────

def _contact(cv: dict) -> dict:
    return cv.get("contact") or {}


def _phone(cv: dict, profile: dict) -> str:
    return (cv.get("phone") or _contact(cv).get("phone") or profile.get("phone") or "").strip()


def _email(cv: dict, profile: dict) -> str:
    return (cv.get("email") or _contact(cv).get("email") or profile.get("email") or "").strip()


def _name(cv: dict, profile: dict) -> str:
    return (cv.get("name") or profile.get("name") or "").strip()


def _location_value(cv: dict, profile: dict, kind: str) -> str:
    location = (
        cv.get("location")
        or _contact(cv).get("location")
        or profile.get("location")
        or ""
    ).strip()
    if not location:
        return ""
    parts = [p.strip() for p in re.split(r"[,|/]", location) if p.strip()]
    if kind == "city":
        return parts[0] if parts else location
    if kind == "country":
        return parts[-1] if len(parts) > 1 else location
    return location


def profile_lookup(label: str, cv: dict, profile: dict) -> Optional[str]:
    """Direct profile fields. Returns None if no confident match."""
    if not label:
        return None
    ll = label.lower().strip()

    phone = _phone(cv, profile)
    email = _email(cv, profile)
    name  = _name(cv, profile)

    # Phone country code. Only answer when the phone reveals it.
    if ("country" in ll and "code" in ll) or ll in ("phone country code", "country code"):
        if phone.startswith("+973"):
            return "Bahrain (+973)"
        return None

    # Phone / mobile
    if ("phone" in ll or "mobile" in ll) and "country" not in ll and phone:
        return phone

    # Email
    if "email" in ll and email:
        return email

    # Name
    if ll == "name" or ll == "full name" or "your name" in ll:
        return name or None
    if "first name" in ll or ll == "given name":
        return cv.get("first_name") or (name.split(" ", 1)[0] if name else "")
    if "last name" in ll or "surname" in ll or "family name" in ll:
        parts = name.split(" ", 1)
        return cv.get("last_name") or (parts[1] if len(parts) > 1 else "")

    # Years of experience
    if ("year" in ll or "years" in ll) and "experience" in ll and cv.get("years"):
        return str(cv["years"])

    # City / location
    if ll in ("city", "current city", "location (city)", "city, state, or zip code"):
        return _location_value(cv, profile, "city") or None
    if ll in ("current location", "location", "country", "country of residence"):
        return _location_value(cv, profile, "country") or None
    if "zip" in ll or "postal" in ll:
        return None

    # Nationality / citizenship
    if "nationality" in ll or "citizenship" in ll:
        return cv.get("nationality") or profile.get("nationality") or None

    # Notice period
    if "notice" in ll and ("period" in ll or "day" in ll or "month" in ll):
        return "30"

    # Education
    if ("bachelor" in ll) and ("education" in ll or "degree" in ll or "level" in ll or "completed" in ll):
        return "Yes"
    if "highest" in ll and ("education" in ll or "qualification" in ll or "degree" in ll):
        return "PhD"
    if "level of education" in ll or "education level" in ll:
        return "PhD"
    if "master" in ll and ("degree" in ll or "education" in ll):
        return "Yes"
    if ("phd" in ll or "doctor" in ll or "doctorate" in ll) and ("degree" in ll or "education" in ll):
        return "Yes"

    # Work authorisation / sponsorship / commute / background
    if ("authorized" in ll or "authorised" in ll or "authorization" in ll or "right to work" in ll) and "work" in ll:
        return "Yes"
    if "sponsorship" in ll:
        return "No"
    if "relocat" in ll:
        return "Yes"
    if "commut" in ll:
        return "Yes"
    if "background check" in ll or "background screening" in ll:
        return "Yes"
    if "drug test" in ll or "drug screen" in ll:
        return "Yes"
    if "at-will" in ll or "at will" in ll:
        return "Yes"
    if ("full" in ll and "time" in ll) or "full-time" in ll:
        return "Yes"
    if "18" in ll and ("age" in ll or "years" in ll or "older" in ll):
        return "Yes"

    # Salary
    if "expected" in ll and "salary" in ll:
        return "55000"
    if ("current" in ll or "present" in ll) and "salary" in ll:
        return "0"
    if ll in ("expected salary", "salary expectation", "salary expectations",
              "expected monthly salary", "expected annual salary"):
        return "55000"

    # LinkedIn URL
    if "linkedin" in ll and ("url" in ll or "profile" in ll or "link" in ll):
        return cv.get("linkedin") or _contact(cv).get("linkedin") or profile.get("linkedin") or None

    # Diversity / self-identification
    if "gender" in ll and ("identit" in ll or "describe" in ll or "term" in ll):
        return "Prefer not to say"
    if ll == "gender":
        return "Prefer not to say"
    if "pronoun" in ll:
        return "Prefer not to say"
    if "ethnic" in ll or "racial" in ll or ll == "race":
        return "Prefer not to say"
    if "veteran" in ll:
        return "I am not a protected veteran"
    if "disability" in ll or "disabled" in ll:
        return "I don't wish to answer"

    # Availability
    if "available immediately" in ll or "start immediately" in ll:
        return "No"
    if "available to start" in ll:
        return "30 days"

    return None


def bank_lookup(label: str, answers_bank: List[dict]) -> Optional[str]:
    """Look up a question in the user's saved answers bank (exact + fuzzy)."""
    if not label or not answers_bank:
        return None
    ll = label.lower().strip()
    bank = {(a.get("question") or "").strip().lower(): (a.get("answer") or "")
            for a in answers_bank if a.get("question")}

    # Exact
    if ll in bank and bank[ll]:
        return bank[ll]

    # Substring (either direction)
    for bq, ba in bank.items():
        if not ba:
            continue
        if bq in ll or ll in bq:
            return ba

    # Word overlap (≥ 3 significant words shared)
    ll_words = {w for w in re.findall(r"\w+", ll) if len(w) > 3}
    if len(ll_words) >= 3:
        for bq, ba in bank.items():
            if not ba:
                continue
            bq_words = {w for w in re.findall(r"\w+", bq) if len(w) > 3}
            if len(ll_words & bq_words) >= 3:
                return ba

    return None


# ────────────────────────────────────────────────────────────────────────────
# LLM call — answer all unresolved fields in one structured request
# ────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an expert AI agent filling LinkedIn job application forms for the candidate
represented by the provided user_profile and cv_full JSON. The uploaded CV is the
source of truth. Do not assume any identity, nationality, salary, degree, location,
LinkedIn URL, or specialist skills that are not in the JSON or previous answers.

YOUR ROLE:
Answer EVERY field in the form snapshot you receive confidently and professionally
when the answer is supported by the candidate profile, CV, previous answers, or a
standard employment convention. You are an AGENT, not a lookup table. Use reasoning.

ANSWER FORMATTING — STRICT:
Return ONLY valid JSON in this exact shape:
{
  "answers": [
    {"id": "<field_id>", "value": "<answer>", "confident": true|false},
    ...one entry per field in the snapshot, in the same order...
  ]
}

PER-TYPE RULES:
- type "number": value MUST be only digits. No commas, units, currency. ("15", not "15 years")
- type "select" or "radio" or "combobox" with options: value MUST be EXACTLY one of the
  provided option strings, character-for-character. Copy verbatim. Never paraphrase.
- type "checkbox": value is "yes" if the box should be ticked, "no" otherwise.
- type "text" / "textarea" / "tel" / "email" / "url": free-form, concise (under 100
  chars unless it's a cover letter).

CONFIDENCE RULES — be GENEROUS with confident=true:
- Standard employment questions (commuting, background check, drug test, at-will,
  full-time, 18+, right to work, willingness to relocate) → "Yes" / "No", confident=true.
- Diversity / self-id (gender, race, veteran, disability) → "Prefer not to say"
  or equivalent option, confident=true.
- Years-of-experience-with-X questions → use total experience only when the skill
  is present in the CV. For unrelated tools, use "0" or confident=false if required.
- Salary questions → use previous answers if available; otherwise choose a reasonable
  market expectation only if the field is mandatory and does not require private data.
- LinkedIn / portfolio URL → use the provided URL only. If absent, confident=false.
- ONLY set confident=false for: passport numbers, government IDs, SSN, bank account
  numbers, or questions about projects he genuinely cannot have done (e.g. "How
  many GIS national addressing projects have you led?" → confident=false).

VALIDATION RECOVERY:
If `validation_errors` is present, the previous attempt was rejected. Read the errors
carefully and adjust your answers. For example:
  - "Please enter a whole number" → strip decimals from a number field
  - "Please enter a valid email" → fix the email format
  - "Field is required" → make sure you're not returning an empty string

Return JSON. No prose. No markdown fences. Just the JSON object.
"""


def _build_user_prompt(snapshot: dict, fields_to_answer: List[dict],
                      profile: dict, cv: dict) -> str:
    location = _location_value(cv, profile, "full")
    payload = {
        "step_title": snapshot.get("step_title") or "",
        "page_text_excerpt": (snapshot.get("page_text") or "")[:600],
        "validation_errors": snapshot.get("validation_errors") or [],
        "user_profile": {
            "name": _name(cv, profile),
            "email": _email(cv, profile),
            "phone": _phone(cv, profile),
            "linkedin": cv.get("linkedin") or _contact(cv).get("linkedin") or profile.get("linkedin") or "",
            "location": location,
            "city": _location_value(cv, profile, "city"),
            "country": _location_value(cv, profile, "country"),
            "nationality": cv.get("nationality") or profile.get("nationality") or "",
            "years_experience": cv.get("years", 0),
            "seniority": cv.get("seniority", ""),
            "skills": (cv.get("skills") or [])[:15],
            "summary": cv.get("summary") or "",
        },
        "fields": [
            {
                "id": f["id"],
                "label": f["label"],
                "type": f["type"],
                "options": f.get("options") or [],
                "required": f.get("required", False),
                "current_value": f.get("current") or "",
                "max_length": f.get("max_length"),
            }
            for f in fields_to_answer
        ],
    }
    return (
        "Answer EVERY field below for the candidate's job application.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _call_llm(system: str, user: str, api_key: str, api_base: str,
             api_model: str, temperature: float = 0.1, timeout: int = 25) -> Optional[dict]:
    try:
        import httpx
        resp = httpx.post(
            f"{api_base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={
                "model": api_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        return json.loads(raw)
    except Exception as e:
        logger.warning("LLM call failed: %s", e)
        return None


def llm_answer_fields(
    snapshot: dict,
    fields_to_answer: List[dict],
    profile: dict,
    cv: dict,
    api_key: str,
    api_base: str,
    api_model: str,
) -> dict:
    """
    Single LLM call that returns answers for every field in `fields_to_answer`.
    Returns: {field_id: {"value": str, "confident": bool}, ...}
    """
    if not api_key or not fields_to_answer:
        return {}

    user_prompt = _build_user_prompt(snapshot, fields_to_answer, profile, cv)
    parsed = _call_llm(_SYSTEM_PROMPT, user_prompt, api_key, api_base, api_model)
    if not parsed:
        return {}

    answers = parsed.get("answers") or []
    if not isinstance(answers, list):
        return {}

    out: dict = {}
    for a in answers:
        try:
            fid = str(a.get("id", "")).strip()
            val = str(a.get("value", "")).strip()
            conf = bool(a.get("confident", False))
            if fid:
                out[fid] = {"value": val, "confident": conf}
        except Exception:
            pass
    return out


# ────────────────────────────────────────────────────────────────────────────
# Type coercion helpers (post-LLM)
# ────────────────────────────────────────────────────────────────────────────

def coerce_to_number(value: str) -> Optional[str]:
    """Strip everything but digits (and one decimal). Return integer string or None."""
    if value is None:
        return None
    clean = re.sub(r"[^\d.]", "", str(value))
    if not clean:
        return None
    try:
        return str(int(float(clean)))
    except Exception:
        return None


def normalise_for_match(s: str) -> str:
    """Normalise a string for option-matching: lowercase, strip, collapse separators."""
    if not s:
        return ""
    s = s.lower().strip()
    # "Native / Bilingual" ↔ "Native or Bilingual"
    s = s.replace(" / ", " or ").replace("/", " or ")
    s = s.replace(" & ", " and ").replace("&", " and ")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def best_option_match(value: str, options: List[str]) -> Optional[str]:
    """
    Find the best option match for `value` from `options`.
    Returns the EXACT option text from `options`, or None if no good match.
    """
    if not value or not options:
        return None
    v_norm = normalise_for_match(value)

    # 1. Exact match (normalised)
    for o in options:
        if normalise_for_match(o) == v_norm:
            return o

    # 2. Prefix / contains match
    for o in options:
        o_norm = normalise_for_match(o)
        if o_norm.startswith(v_norm) or v_norm.startswith(o_norm):
            return o
    for o in options:
        o_norm = normalise_for_match(o)
        if v_norm in o_norm or o_norm in v_norm:
            return o

    # 3. Word overlap
    v_words = set(re.findall(r"\w+", v_norm))
    v_words.discard("or"); v_words.discard("and")
    if v_words:
        best_o = None
        best_score = 0
        for o in options:
            o_words = set(re.findall(r"\w+", normalise_for_match(o)))
            o_words.discard("or"); o_words.discard("and")
            overlap = len(v_words & o_words)
            if overlap > best_score:
                best_score = overlap
                best_o = o
        if best_score >= max(1, min(len(v_words), 2)):
            return best_o

    # 4. Yes/No fallback
    yes_set = {"yes", "y", "true", "agree", "i agree"}
    no_set  = {"no", "n", "false", "disagree", "i disagree"}
    if v_norm in yes_set:
        for o in options:
            if normalise_for_match(o) in yes_set:
                return o
    if v_norm in no_set:
        for o in options:
            if normalise_for_match(o) in no_set:
                return o

    return None
