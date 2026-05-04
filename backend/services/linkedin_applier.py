"""
Real LinkedIn Easy Apply submitter.

Given a Selenium driver + job URL + CV/answer-bank, this module:
1. Navigates to the job page.
2. Clicks the Easy Apply button.
3. Walks the multi-step form, filling text/numeric/dropdown/radio inputs using:
     a) Direct profile fields (phone, email, name, years…)
     b) The saved answer bank (fuzzy-matched)
     c) Groq LLM — answers from uploaded CV/profile; uncertain = pending
   If none of the above is confident enough, the form is discarded → "pending".
4. Hits Next/Review/Submit until either:
    - submission is confirmed (success modal) → returns "submitted"
    - an unanswered question is hit          → modal is discarded, returns "pending"
    - any unrecoverable error                → returns "error"

Returns:
    {
      "status": "submitted" | "pending" | "not_easy_apply" | "error",
      "pending_question": str | None,
      "error": str | None,
      "new_answers": [{"question": ..., "answer": ...}, ...]   # LLM-generated; caller persists
    }
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Small helpers
# ────────────────────────────────────────────────────────────────────────────

def _click(driver, element):
    try:
        element.click()
    except Exception:
        try:
            driver.execute_script("arguments[0].click()", element)
        except Exception:
            pass


def _is_visible(el) -> bool:
    try:
        return el.is_displayed() and el.is_enabled()
    except Exception:
        return False


def _modal(driver, By):
    for sel in [".jobs-easy-apply-modal", "div[role='dialog'].artdeco-modal",
                ".artdeco-modal", "div[role='dialog']"]:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            if _is_visible(el):
                return el
        except Exception:
            pass
    return None


def _clean_label(raw: str) -> str:
    """Strip LinkedIn SDUI duplicates + 'Required' suffix from label text."""
    lines = [l.strip() for l in raw.split("\n")
             if l.strip() and l.strip().lower() != "required"]
    return lines[0] if lines else raw.strip()


# ────────────────────────────────────────────────────────────────────────────
# Easy Apply button detection
# ────────────────────────────────────────────────────────────────────────────

def _find_easy_apply_button(driver, By):
    candidates = []
    for sel in [
        "button.jobs-apply-button",
        ".jobs-apply-button--top-card .artdeco-button",
        "button[aria-label*='Easy Apply']",
        "a[aria-label*='Easy Apply']",
        "button[data-control-name='jobdetails_topcard_inapply']",
    ]:
        try:
            for b in driver.find_elements(By.CSS_SELECTOR, sel):
                if not _is_visible(b):
                    continue
                blob = ((b.text or "") + " " + (b.get_attribute("aria-label") or "")).lower()
                if "easy apply" in blob:
                    candidates.append(b)
        except Exception:
            pass
    if not candidates:
        try:
            for el in driver.find_elements(By.XPATH,
                    '//button[contains(., "Easy Apply")] | //a[contains(., "Easy Apply")]'):
                if _is_visible(el):
                    candidates.append(el)
        except Exception:
            pass
    return candidates[0] if candidates else None


# ────────────────────────────────────────────────────────────────────────────
# Form navigation buttons
# ────────────────────────────────────────────────────────────────────────────

def _next_or_submit_button(driver, By):
    """Returns ('next'|'review'|'submit', el) or None."""
    modal = _modal(driver, By)
    if not modal:
        return None
    submit, review, nxt = None, None, None
    for b in modal.find_elements(By.CSS_SELECTOR, "button"):
        if not _is_visible(b):
            continue
        blob = ((b.text or "") + " " + (b.get_attribute("aria-label") or "")).strip().lower()
        if not blob:
            continue
        if "submit application" in blob or blob == "submit":
            submit = b
        elif "review" in blob:
            review = b
        elif "next" in blob or "continue" in blob:
            nxt = b
    if submit: return ("submit", submit)
    if review: return ("review", review)
    if nxt:    return ("next",   nxt)
    return None


# ────────────────────────────────────────────────────────────────────────────
# CV / profile field extractors
# ────────────────────────────────────────────────────────────────────────────

def _phone_from_cv(cv: dict) -> str:
    if cv.get("phone"):
        return cv["phone"].strip()
    contact_phone = (cv.get("contact") or {}).get("phone")
    if contact_phone:
        return contact_phone.strip()
    raw = (cv.get("summary") or "") + " " + " ".join(cv.get("skills") or [])
    m = re.search(r"(\+?\d[\d\s\-]{8,}\d)", raw)
    return (m.group(1).strip() if m else "")


def _email_from_cv(cv: dict) -> str:
    if cv.get("email"):
        return cv["email"].strip()
    contact_email = (cv.get("contact") or {}).get("email")
    if contact_email:
        return contact_email.strip()
    raw = (cv.get("summary") or "")
    m = re.search(r"[\w\.\-+]+@[\w\.\-]+\.\w+", raw)
    return (m.group(0) if m else "")


# ────────────────────────────────────────────────────────────────────────────
# Groq LLM answer engine
# ────────────────────────────────────────────────────────────────────────────

_GROQ_SYSTEM = """\
You are an AI agent filling a LinkedIn job application form for the candidate
represented by the provided CV/profile JSON. The uploaded CV is the source of truth.
Do not assume any fixed candidate identity. Do not invent nationality, salary,
location, LinkedIn URL, degree, or specialist skills that are not in the JSON or
previous answers.

**YOUR ROLE:**
Think carefully about each question using the candidate's full CV, previous answers,
and professional profile. Answer concisely, professionally, and truthfully.

**RULES:**
- Return ONLY valid JSON: {"answer": "<value>", "confident": true|false}
- "confident": true  → you can derive the answer from the profile, CV, previous answers, or it is a standard employment question
- "confident": false → ONLY when the question requires truly private data you cannot know (passport number, SSN, government ID)
- Be VERY generous with confident=true — if you can give a reasonable professional answer, do it
- ALWAYS set confident=true unless the question asks for passport/SSN/government ID/bank details

**FIELD TYPE RULES:**
- For NUMBER fields: answer must be ONLY digits. No commas, no units, no text. Example: "15" not "15 years"
- For SELECT/DROPDOWN fields: you MUST return EXACTLY one of the provided option values. Copy the option text exactly, character for character. Never paraphrase or create your own option.
- For RADIO fields: you MUST return EXACTLY one of the provided option labels. Copy it exactly.
- For TEXT fields: keep answers concise and direct. Under 100 characters unless it's a cover letter.
- For YES/NO questions: answer exactly "Yes" or "No"

**STANDARD ANSWERS:**
- Commuting, background check, drug test, at-will, full-time, 18+ age, right to work → "Yes", confident=true
- Diversity/veteran/disability: "Prefer not to say" or "I don't wish to answer"
- "How did you hear?": "LinkedIn"
- Cover letter: write 2-3 sentences based on CV matching the job
- LinkedIn/portfolio/GitHub URL: use the provided URL only; if absent, confident=false
- "Have you led/managed/built X?" → answer "Yes" only if supported by CV/profile/previous answers
- Never invent passport numbers, government IDs, or bank details — mark those confident=false
"""

def _groq_answer_question(
    question: str,
    field_type: str,
    options: List[str],
    profile: dict,
    cv: dict,
    api_key: str,
    api_base: str,
    api_model: str,
    answers_bank: List[dict] = None,
) -> Tuple[Optional[str], bool]:
    """
    Call Groq to answer a single form question.
    Sends full CV + answer bank as RAG context so the LLM can reason properly.
    Returns (answer_string | None, confident).
    """
    if not api_key:
        return None, False

    try:
        import httpx

        # ── Build rich context for the LLM ────────────────────────────
        # Full CV — no truncation
        cv_context = {
            "name": cv.get("name") or profile.get("name", ""),
            "email": cv.get("email") or cv.get("contact", {}).get("email") or profile.get("email", ""),
            "phone": cv.get("phone") or cv.get("contact", {}).get("phone") or profile.get("phone", ""),
            "years_experience": cv.get("years", 0),
            "seniority": cv.get("seniority", ""),
            "skills": cv.get("skills") or [],
            "summary": cv.get("summary") or "",
            "education": cv.get("education") or [],
            "experience": cv.get("experience") or [],
        }

        # Answer bank as RAG — so LLM can reference previous answers
        prev_answers = {}
        if answers_bank:
            for a in answers_bank:
                q = (a.get("question") or "").strip()
                ans = (a.get("answer") or "").strip()
                if q and ans:
                    prev_answers[q] = ans

        context_payload = {
            "profile": {
                "name": cv_context["name"],
                "email": cv_context["email"],
                "phone": cv_context["phone"],
                "nationality": cv.get("nationality") or profile.get("nationality") or "",
                "location": cv.get("location") or cv.get("contact", {}).get("location") or profile.get("location") or "",
                "linkedin": cv.get("linkedin") or cv.get("contact", {}).get("linkedin") or profile.get("linkedin") or "",
            },
            "cv_full": cv_context,
            "previous_answers": prev_answers,
            "current_question": {
                "question": question,
                "field_type": field_type,
                "available_options": options or [],
            },
        }

        user_msg = (
            "Answer the following form question for the job application. "
            "Use the full CV and previous answers as context to give the best answer.\n\n"
            + json.dumps(context_payload, ensure_ascii=False)
        )

        response = httpx.post(
            f"{api_base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": api_model,
                "messages": [
                    {"role": "system", "content": _GROQ_SYSTEM},
                    {"role": "user",   "content": user_msg},
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            },
            timeout=15,
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(raw)
        answer    = str(parsed.get("answer", "")).strip()
        confident = bool(parsed.get("confident", False))
        logger.info("[Groq] Q=%r  ans=%r  confident=%s", question[:60], answer[:40], confident)
        return (answer or None), confident

    except Exception as exc:
        logger.warning("[Groq] call failed for %r: %s", question[:60], exc)
        return None, False


# ────────────────────────────────────────────────────────────────────────────
# Field fill helpers
# ────────────────────────────────────────────────────────────────────────────

def _fill_text(el, value: str) -> bool:
    try:
        el.clear()
        el.send_keys(value)
        return True
    except Exception:
        return False


def _fill_typeahead(driver, By, el, value: str) -> bool:
    """
    Fill a typeahead/autocomplete input: type, pick the BEST matching suggestion.
    Handles LinkedIn SDUI dropdowns (role=combobox → role=listbox).
    Falls back to plain send_keys if no dropdown appears.
    """
    from selenium.webdriver.common.keys import Keys
    try:
        el.clear()
        el.send_keys(value)
        time.sleep(0.8)
        # Look for suggestion dropdown options
        suggestion_selectors = [
            "div[role='option']",
            "li[role='option']",
            "div[role='listbox'] div",
            ".artdeco-typeahead__option",
            ".basic-typeahead__triggered-content li",
            ".artdeco-dropdown__content-inner li",
        ]
        all_visible = []
        for sel in suggestion_selectors:
            try:
                opts = driver.find_elements(By.CSS_SELECTOR, sel)
                visible = [o for o in opts if _is_visible(o) and (o.text or "").strip()]
                all_visible.extend(visible)
            except Exception:
                pass
        if all_visible:
            # Score each option for best match
            value_lower = value.strip().lower()
            value_words = set(w for w in value_lower.split() if len(w) > 2)
            best_opt, best_score = None, -1
            for opt in all_visible:
                opt_text = (opt.text or "").strip().lower()
                score = 0
                # Exact match
                if opt_text == value_lower:
                    score = 100
                # Contains
                elif value_lower in opt_text or opt_text in value_lower:
                    score = 50
                # Keyword overlap
                else:
                    opt_words = set(w for w in opt_text.split() if len(w) > 2)
                    overlap = len(value_words & opt_words)
                    if overlap:
                        score = 10 + overlap * 5
                if score > best_score:
                    best_score = score
                    best_opt = opt
            if best_opt:
                _click(driver, best_opt)
                logger.info("[Typeahead] Selected '%s' (score=%d) for value '%s'",
                           (best_opt.text or "")[:40], best_score, value[:30])
                return True
        # No dropdown — just tab out to commit the value
        el.send_keys(Keys.TAB)
        return True
    except Exception:
        return False


def _fill_sdui_dropdown(driver, By, el, value: str, label: str = "") -> bool:
    """
    Handle LinkedIn SDUI dropdown components (role=combobox, custom select).
    1. Click the element to open the dropdown
    2. Read visible options from role=listbox or other containers
    3. Pick the best matching option using fuzzy scoring
    """
    from selenium.webdriver.common.keys import Keys
    try:
        # Click to open
        _click(driver, el)
        time.sleep(0.6)

        # Try typing to filter (combobox often supports filtering)
        try:
            el.clear()
            el.send_keys(value[:20])  # type first part to filter
            time.sleep(0.5)
        except Exception:
            pass

        # Read options from any visible listbox/dropdown
        option_selectors = [
            "div[role='listbox'] div[role='option']",
            "ul[role='listbox'] li",
            "div[role='option']",
            "li[role='option']",
            ".artdeco-dropdown__content-inner li",
            ".artdeco-typeahead__option",
            ".basic-typeahead__triggered-content li",
        ]
        all_opts = []
        for sel in option_selectors:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for o in els:
                    if _is_visible(o) and (o.text or "").strip():
                        all_opts.append(o)
            except Exception:
                pass

        if not all_opts:
            # Maybe clicking didn't open — try with Keys
            try:
                el.send_keys(Keys.ARROW_DOWN)
                time.sleep(0.4)
                for sel in option_selectors:
                    try:
                        els = driver.find_elements(By.CSS_SELECTOR, sel)
                        for o in els:
                            if _is_visible(o) and (o.text or "").strip():
                                all_opts.append(o)
                    except Exception:
                        pass
            except Exception:
                pass

        if not all_opts:
            return False

        # Score options
        value_lower = value.strip().lower()
        value_words = set(w for w in value_lower.split() if len(w) > 2)
        best_opt, best_score = None, -1
        for opt in all_opts:
            opt_text = (opt.text or "").strip().lower()
            score = 0
            if opt_text == value_lower:
                score = 100
            elif value_lower in opt_text or opt_text in value_lower:
                score = 50
            else:
                opt_words = set(w for w in opt_text.split() if len(w) > 2)
                overlap = len(value_words & opt_words)
                if overlap:
                    score = 10 + overlap * 5
            if score > best_score:
                best_score = score
                best_opt = opt

        if best_opt and best_score > 0:
            _click(driver, best_opt)
            logger.info("[SDUI dropdown] Selected '%s' (score=%d) for '%s'",
                       (best_opt.text or "")[:40], best_score, value[:30])
            return True

        # No good match — pick first option as fallback
        _click(driver, all_opts[0])
        logger.info("[SDUI dropdown] No match — picked first option '%s' for '%s'",
                   (all_opts[0].text or "")[:40], value[:30])
        return True
    except Exception as exc:
        logger.debug("[SDUI dropdown] Error: %s", exc)
        return False


def _try_select_option(driver, By, select_el, target: str) -> bool:
    """Pick an <option> whose text best matches `target`."""
    try:
        from selenium.webdriver.support.ui import Select
        sel = Select(select_el)
        target_lower = (target or "").strip().lower()
        # 1. Exact match
        for opt in sel.options:
            if (opt.text or "").strip().lower() == target_lower:
                sel.select_by_visible_text(opt.text)
                return True
        # 2. Target contains option text or option contains target
        for opt in sel.options:
            opt_lower = (opt.text or "").strip().lower()
            if not opt_lower or opt_lower in ("select an option", "select", "-- select --", "choose one"):
                continue
            if target_lower in opt_lower or opt_lower in target_lower:
                sel.select_by_visible_text(opt.text)
                return True
        # 3. Keyword overlap — pick option with most matching words
        target_words = set(w for w in target_lower.split() if len(w) > 2)
        if target_words:
            best_opt, best_score = None, 0
            for opt in sel.options:
                opt_lower = (opt.text or "").strip().lower()
                if not opt_lower or opt_lower in ("select an option", "select", "-- select --"):
                    continue
                opt_words = set(w for w in opt_lower.split() if len(w) > 2)
                overlap = len(target_words & opt_words)
                if overlap > best_score:
                    best_score = overlap
                    best_opt = opt
            if best_opt and best_score >= 1:
                sel.select_by_visible_text(best_opt.text)
                return True
        # 4. Yes/No booleans
        for opt in sel.options:
            t = (opt.text or "").strip().lower()
            if target_lower in {"yes", "y", "true"} and t == "yes":
                sel.select_by_visible_text(opt.text); return True
            if target_lower in {"no", "n", "false"} and t == "no":
                sel.select_by_visible_text(opt.text); return True
        return False
    except Exception:
        return False


def _get_select_options(driver, By, select_el) -> List[str]:
    """Return all visible option texts for a <select> element."""
    try:
        from selenium.webdriver.support.ui import Select
        sel = Select(select_el)
        return [opt.text.strip() for opt in sel.options if opt.text.strip()]
    except Exception:
        return []


def _try_select_radio(driver, By, question: str, target: str) -> bool:
    """
    LinkedIn renders radios as `<fieldset><legend>Q?</legend><label>Yes/No</label>`.
    `question` is the CLEAN (single-line) question text.
    """
    target_lower = (target or "").strip().lower()
    # Normalize separators for flexible matching
    target_norm = target_lower.replace("/", " or ").replace("&", " and ").replace("  ", " ").strip()
    target_words = set(w for w in target_norm.split() if len(w) > 2)
    # Clean the question for flexible legend matching
    clean_q = _clean_label(question).lower().strip()

    try:
        modal = _modal(driver, By)
        if not modal:
            return False
        for fs in modal.find_elements(By.CSS_SELECTOR, "fieldset"):
            try:
                legend_el = fs.find_element(By.CSS_SELECTOR, "legend, span")
                legend = _clean_label(legend_el.text).lower().strip()
            except Exception:
                continue
            # Flexible match: one contains the other (handles partial text)
            if not (clean_q in legend or legend in clean_q or
                    # Also try word-overlap for longer questions
                    any(word in legend for word in clean_q.split() if len(word) > 5)):
                continue

            # Score each label for best match
            labels = [l for l in fs.find_elements(By.CSS_SELECTOR, "label") if (l.text or "").strip() and _is_visible(l)]
            best_lab, best_score = None, -1
            for lab in labels:
                lab_text = (lab.text or "").strip().lower()
                lab_norm = lab_text.replace("/", " or ").replace("&", " and ").replace("  ", " ").strip()
                score = 0
                # Exact match (with normalization)
                if lab_norm == target_norm or lab_text == target_lower:
                    score = 100
                # Starts-with match
                elif lab_text.startswith(target_lower) or target_lower.startswith(lab_text):
                    score = 80
                # Contains match
                elif target_norm in lab_norm or lab_norm in target_norm:
                    score = 60
                # Keyword overlap
                else:
                    lab_words = set(w for w in lab_norm.split() if len(w) > 2)
                    overlap = len(target_words & lab_words)
                    if overlap:
                        score = 10 + overlap * 10
                if score > best_score:
                    best_score = score
                    best_lab = lab

            # Click best match if score is good
            if best_lab and best_score >= 10:
                _click(driver, best_lab)
                logger.info("[Radio] Selected '%s' (score=%d) for answer '%s'",
                           (best_lab.text or "")[:30], best_score, target[:30])
                return True

            # Yes/No shortcuts
            if target_lower in {"yes", "y", "true"} and labels:
                for lab in labels:
                    lt = (lab.text or "").strip().lower()
                    if lt == "yes" or lt.startswith("yes,"):
                        _click(driver, lab); return True
                _click(driver, labels[0]); return True
            if target_lower in {"no", "n", "false"} and len(labels) >= 2:
                for lab in labels:
                    lt = (lab.text or "").strip().lower()
                    if lt == "no" or lt.startswith("no,"):
                        _click(driver, lab); return True
                _click(driver, labels[-1]); return True
            return False
    except Exception:
        return False
    return False


def _get_radio_options(driver, By, question: str) -> List[str]:
    """Return visible label texts inside the fieldset for this question."""
    clean_q = _clean_label(question).lower().strip()
    try:
        modal = _modal(driver, By)
        if not modal:
            return []
        for fs in modal.find_elements(By.CSS_SELECTOR, "fieldset"):
            try:
                legend = _clean_label(
                    fs.find_element(By.CSS_SELECTOR, "legend, span").text
                ).lower().strip()
            except Exception:
                continue
            if not (clean_q in legend or legend in clean_q):
                continue
            return [
                lab.text.strip()
                for lab in fs.find_elements(By.CSS_SELECTOR, "label")
                if lab.text.strip()
            ]
    except Exception:
        pass
    return []


def _is_integer_field(inp) -> bool:
    """True if the field only accepts whole numbers."""
    try:
        itype = (inp.get_attribute("type") or "").lower()
        if itype == "number":
            step = inp.get_attribute("step") or ""
            return step in ("", "1", None)
        return False
    except Exception:
        return False


def _coerce_to_int(value: str) -> Optional[str]:
    """Try to parse value as integer. Return digit-string or None."""
    try:
        clean = re.sub(r"[^\d.]", "", value)
        return str(int(float(clean))) if clean else None
    except Exception:
        return None


def _is_typeahead(inp) -> bool:
    """Detect LinkedIn typeahead / autocomplete inputs."""
    try:
        role = (inp.get_attribute("role") or "").lower()
        autocomplete = (inp.get_attribute("autocomplete") or "").lower()
        aria_auto = (inp.get_attribute("aria-autocomplete") or "").lower()
        return role == "combobox" or "off" not in autocomplete or aria_auto in ("list", "both")
    except Exception:
        return False


# ────────────────────────────────────────────────────────────────────────────
# Profile-first answer lookup (heuristics before touching Groq)
# ────────────────────────────────────────────────────────────────────────────

def _profile_answer(ll: str, cv: dict, profile: dict) -> Optional[str]:
    """
    Fast lookup: return answer for well-known fields directly from profile/cv.
    `ll` is the cleaned label text, lower-cased.
    Returns answer string or None.
    """
    phone = _phone_from_cv(cv)
    email = _email_from_cv(cv)
    contact = cv.get("contact") or {}
    name  = cv.get("name") or profile.get("name") or ""
    location = (cv.get("location") or contact.get("location") or profile.get("location") or "").strip()
    loc_parts = [p.strip() for p in re.split(r"[,|/]", location) if p.strip()]
    city = loc_parts[0] if loc_parts else location
    country = loc_parts[-1] if len(loc_parts) > 1 else location

    # Phone
    if ("phone" in ll or "mobile" in ll) and "country" not in ll and phone:
        return phone
    # Phone country code (Bahrain = +973)
    if ("country" in ll and "code" in ll and "phone" in ll) or ll == "phone country code":
        if phone.startswith("+973"):
            return "Bahrain (+973)"
        return None
    # Email
    if "email" in ll and email:
        return email
    # Name variants
    if ll.strip() == "name":
        return name or None
    if "first name" in ll or "given name" in ll or ll in {"forename", "given"}:
        return cv.get("first_name") or (name.split(" ", 1)[0] if name else None)
    if "last name" in ll or "surname" in ll or "family name" in ll or ll in {"last", "family"}:
        parts = name.split(" ", 1)
        return cv.get("last_name") or (parts[1] if len(parts) > 1 else None)
    if "full name" in ll:
        return name or None
    # Years of experience
    if "year" in ll and "experience" in ll and cv.get("years"):
        return str(cv["years"])
    # City / location
    if ll in ("city", "current city", "location (city)", "city, state, or zip code"):
        return city or None
    if ll in ("current location", "location", "country", "country of residence"):
        return country or None
    if "zip" in ll or "postal" in ll:
        return None
    # Nationality
    if "nationality" in ll or "citizenship" in ll:
        return cv.get("nationality") or profile.get("nationality") or None
    # Notice period
    if "notice" in ll and ("period" in ll or "day" in ll):
        return "30"
    # Education — Bachelor's
    if ("bachelor" in ll) and ("education" in ll or "degree" in ll or "level" in ll or "completed" in ll):
        return "yes"
    # Education — highest level
    if "highest" in ll and ("education" in ll or "qualification" in ll or "degree" in ll):
        return "PhD"
    if "level of education" in ll or "education level" in ll:
        return "PhD"
    # Master's
    if "master" in ll and ("degree" in ll or "education" in ll):
        return "yes"
    # PhD / Doctorate
    if ("phd" in ll or "doctor" in ll or "doctorate" in ll) and ("degree" in ll or "education" in ll):
        return "yes"
    # Work authorisation / sponsorship
    if ("authorized" in ll or "authorised" in ll or "authorization" in ll or "right to work" in ll) and "work" in ll:
        return "yes"
    if "sponsorship" in ll:
        return "no"
    # Relocation
    if "relocat" in ll:
        return "yes"
    # Commuting
    if "commut" in ll:
        return "yes"
    # Background check / drug test / screening
    if "background check" in ll or "background screening" in ll:
        return "yes"
    if "drug test" in ll or "drug screen" in ll:
        return "yes"
    # At-will employment
    if "at-will" in ll or "at will" in ll:
        return "yes"
    # Full-time / hours
    if ("full" in ll and "time" in ll) or "full-time" in ll:
        return "yes"
    if "40 hours" in ll or "full time hours" in ll:
        return "yes"
    # 18 years / age
    if "18" in ll and ("age" in ll or "years" in ll or "older" in ll):
        return "yes"
    # Expected salary — read from cv/profile, don't guess if not stored
    _sal_expected = (str(cv.get("salary_expectation") or "").strip()
                     or str(profile.get("salary_expectation") or "").strip())
    _sal_current  = (str(cv.get("current_salary") or "").strip()
                     or str(profile.get("current_salary") or "").strip())
    if "salary" in ll and ("expected" in ll or "desired" in ll):
        return _sal_expected or None
    # Current salary
    if ("current" in ll or "present" in ll) and "salary" in ll:
        return _sal_current or None
    # LinkedIn URL — handle many label variants
    if "linkedin" in ll:
        return cv.get("linkedin") or contact.get("linkedin") or profile.get("linkedin") or None
    # Generic profile/portfolio URL
    if ll in ("website", "portfolio", "portfolio url", "website url", "personal website"):
        return cv.get("linkedin") or contact.get("linkedin") or profile.get("linkedin") or None
    # Headline
    if "headline" in ll or ll == "professional headline" or ll == "title":
        return cv.get("summary") or cv.get("seniority") or profile.get("title") or None
    # Gender / diversity (prefer not to say)
    if "gender" in ll and ("identit" in ll or "describe" in ll or "term" in ll):
        return "Prefer not to say"
    if "gender" in ll:  # catch "Gender" standalone
        return "Prefer not to say"
    if "pronoun" in ll:
        return "Prefer not to say"
    if "ethnicit" in ll or "racial" in ll or "race " in ll:
        return "Prefer not to say"
    if "veteran" in ll:
        return "I am not a protected veteran"
    if "disability" in ll or "disabled" in ll:
        return "I don't wish to answer"
    # Available immediately / start date
    if "available immediately" in ll or "start immediately" in ll:
        return "no"
    if "available to start" in ll or "start date" in ll or "earliest" in ll:
        return "30 days"
    # Salary — catch ALL variants; read from cv/profile or let AI handle
    if "salary" in ll or "compensation" in ll or "pay" in ll:
        if "current" in ll or "present" in ll:
            return _sal_current or None
        return _sal_expected or None
    # CTC / package
    if "ctc" in ll or "package" in ll:
        return _sal_expected or None
    # Cover letter (optional — provide brief one)
    if "cover letter" in ll or "cover_letter" in ll:
        summary = (cv.get("summary") or "").strip()
        years = cv.get("years") or ""
        skills = ", ".join((cv.get("skills") or [])[:4])
        if summary:
            return f"{summary[:180]} I am confident my background aligns well with this role."
        if skills:
            return f"I bring {years} years of relevant experience with strengths in {skills}. I am confident my background aligns well with this role."
        return None
    # How did you hear about us
    if "hear" in ll and ("about" in ll or "us" in ll or "this" in ll):
        return "LinkedIn"
    if "how did you find" in ll or "source" in ll and "job" in ll:
        return "LinkedIn"
    # Referral
    if "referral" in ll or "referred" in ll:
        return "No"

    # ── Language proficiency — BROAD matching ──────────────────────────
    if "english" in ll and ("proficien" in ll or "level" in ll or "describe" in ll or "comfortabl" in ll or "fluenc" in ll):
        return "Native or bilingual"
    if "english" in ll:  # catch standalone "english" questions
        return "Native or bilingual"
    # Arabic yes/no questions: "do you have working-level Arabic?"
    if "arabic" in ll and ("do you" in ll or "have you" in ll or "can you" in ll or "working" in ll):
        return "Yes"
    if "arabic" in ll and ("proficien" in ll or "level" in ll or "describe" in ll or "fluenc" in ll):
        return "Native or bilingual"
    if "arabic" in ll:
        return "Yes"  # default to Yes for any Arabic question
    if "language" in ll and ("proficien" in ll or "level" in ll or "fluenc" in ll):
        return "English - Native or bilingual"

    # ── Years of experience — BROADER patterns ──────────────────────────
    # Catch: "how many years of progressive experience do you have in..."
    # Catch: "years of experience in data governance / transformation / etc."
    if "how many year" in ll and cv.get("years"):
        return str(cv["years"])
    if "year" in ll and ("experience" in ll or "progressive" in ll) and cv.get("years"):
        return str(cv["years"])
    # "How many" + anything about leadership/initiatives/projects
    if "how many" in ll and ("initiative" in ll or "project" in ll or "process" in ll or "led" in ll):
        return str(max(10, cv.get("years", 15)))  # reasonable number for 15 years

    # ── "Have you personally LED / managed / built / designed..." ──────
    # These are yes/no leadership questions — auto-answer "Yes" for senior profiles
    if ("have you" in ll or "do you have" in ll) and any(kw in ll for kw in [
        "led", "manage", "built", "design", "implement", "architect",
        "direct", "oversaw", "oversee", "establish", "launch",
        "develop", "deliver", "drive", "transform", "head",
        "enterprise", "national", "scale", "program", "initiative",
        "data cleansing", "data quality", "data governance",
        "data migration", "data transformation", "digital",
    ]):
        return "Yes"

    # ── "Do you have experience with/in..." ───────────────────────────
    if ("do you have" in ll or "have you" in ll) and "experience" in ll:
        # Check if the question mentions any of the user's CV skills
        cv_skills = [s.lower() for s in (cv.get("skills") or [])]
        for skill in cv_skills:
            if skill in ll:
                return "Yes"
        # For data/AI/ML/cloud experience — always yes for this profile
        if any(kw in ll for kw in ["data", "ai", "machine learning", "cloud", "analytics",
                                    "python", "sql", "leadership", "strategy", "governance",
                                    "digital", "transform", "architect"]):
            return "Yes"
        return "Yes"  # safe default for senior profile

    # ── Onsite/hybrid/remote preference ────────────────────────────────
    if "onsite" in ll or "on-site" in ll:
        return "yes"
    if "hybrid" in ll:
        return "yes"
    if "remote" in ll and ("work" in ll or "comfortable" in ll):
        return "yes"
    if "work arrangement" in ll or "work model" in ll or "work setting" in ll:
        return "yes"

    return None


# ────────────────────────────────────────────────────────────────────────────
# Main form-step walker
# ────────────────────────────────────────────────────────────────────────────

def _walk_form_step(
    driver, By,
    cv: dict,
    answers: List[dict],
    profile: dict,
    api_key: str = "",
    api_base: str = "https://api.groq.com/openai/v1",
    api_model: str = "llama-3.3-70b-versatile",
    new_answers: List[dict] = None,
) -> Optional[str]:
    """
    Fill every visible field in the current modal step.

    Resolution order for each question:
      1. Profile heuristics  (phone / email / name / years / city / …)
      2. Answers bank        (exact then fuzzy match)
      3. Groq LLM            (profile + question + field type + options)
      4. → Pending           (if Groq is not confident or unavailable)

    Returns:
        None  — all fields filled; caller may proceed to Next/Submit
        str   — text of the first question we could not answer (→ pending)
    """
    bank = {
        (a.get("question") or "").strip().lower(): (a.get("answer") or "")
        for a in (answers or []) if a.get("question")
    }

    modal = _modal(driver, By)
    if not modal:
        return None

    # Track processed input IDs to avoid double-filling in the aria-label pass
    processed_ids: set = set()

    # ── PASS 1: label[for] → input[id] pairs ─────────────────────────────
    labels = modal.find_elements(By.CSS_SELECTOR, "label")
    for lab in labels:
        try:
            label_text = (lab.text or "").strip()
            if not label_text or not _is_visible(lab):
                continue
            input_id = lab.get_attribute("for")
            if not input_id:
                continue
            try:
                inp = driver.find_element(By.ID, input_id)
            except Exception:
                continue
            if not _is_visible(inp):
                continue

            tag   = (inp.tag_name or "").lower()
            itype = (inp.get_attribute("type") or "").lower()

            # Skip if already filled
            current = (inp.get_attribute("value") or "").strip()
            if current and tag != "select":
                processed_ids.add(input_id)
                continue

            # Clean label
            clean_label = _clean_label(label_text)
            ll = clean_label.lower().strip()
            processed_ids.add(input_id)

            # ── 1. Profile heuristics ──────────────────────────────────
            answer = _profile_answer(ll, cv, profile)

            # ── 2. Answers bank ────────────────────────────────────────
            if not answer:
                answer = bank.get(ll)
            if not answer:
                for bq, ba in bank.items():
                    if bq in ll or ll in bq:
                        answer = ba
                        break

            # ── 3. Groq LLM ────────────────────────────────────────────
            if not answer and api_key:
                if tag == "select":
                    opts = _get_select_options(driver, By, inp)
                    ftype = "select"
                elif itype == "radio":
                    opts = _get_radio_options(driver, By, clean_label)
                    ftype = "radio"
                elif itype == "number":
                    opts = []
                    ftype = "number"
                else:
                    opts = []
                    ftype = "text"

                groq_ans, confident = _groq_answer_question(
                    clean_label, ftype, opts, profile, cv,
                    api_key, api_base, api_model,
                    answers_bank=answers,
                )
                if groq_ans and confident:
                    answer = groq_ans
                    if new_answers is not None:
                        new_answers.append({"question": clean_label, "answer": groq_ans})
                elif groq_ans and not confident:
                    logger.info("[Groq] uncertain — routing to pending: %r", clean_label)
                    return clean_label

            # ── Handle select ──────────────────────────────────────────
            if tag == "select":
                sel_value = (inp.get_attribute("value") or "").strip()
                if sel_value:
                    continue
                if not answer:
                    return clean_label
                # Log available options for debugging
                avail_opts = _get_select_options(driver, By, inp)
                logger.info("[Select debug] Q='%s' answer='%s' options=%s",
                           clean_label[:40], answer[:30], avail_opts[:5])
                if not _try_select_option(driver, By, inp, answer):
                    # Heuristic/bank answer didn't match any option.
                    # Fall through to Groq with the actual option list
                    # so the AI can pick the closest match.
                    if api_key:
                        opts = _get_select_options(driver, By, inp)
                        groq_ans, confident = _groq_answer_question(
                            clean_label, "select", opts, profile, cv,
                            api_key, api_base, api_model,
                            answers_bank=answers,
                        )
                        if groq_ans and confident:
                            if _try_select_option(driver, By, inp, groq_ans):
                                if new_answers is not None:
                                    new_answers.append({"question": clean_label, "answer": groq_ans})
                                continue
                    # Try SDUI dropdown approach (click-open, read listbox, pick best)
                    if _fill_sdui_dropdown(driver, By, inp, answer, label=clean_label):
                        logger.info("[Select→SDUI] Filled via SDUI dropdown for '%s'", clean_label[:50])
                        continue
                    # Last resort: force-select via JS the best matching or first real option
                    try:
                        from selenium.webdriver.support.ui import Select as Sel
                        s = Sel(inp)
                        real_opts = [o for o in s.options if (o.text or "").strip() and (o.text or "").strip().lower() not in ("select an option", "select", "-- select --", "choose one", "")]
                        if real_opts:
                            # Try to pick best by keyword overlap
                            ans_lower = answer.strip().lower()
                            ans_words = set(w for w in ans_lower.split() if len(w) > 2)
                            best_opt, best_score = real_opts[0], 0
                            for ro in real_opts:
                                ro_text = (ro.text or "").strip().lower()
                                if ans_lower in ro_text or ro_text in ans_lower:
                                    best_opt = ro; best_score = 50; break
                                ro_words = set(w for w in ro_text.split() if len(w) > 2)
                                overlap = len(ans_words & ro_words)
                                if overlap > best_score:
                                    best_score = overlap; best_opt = ro
                            # Force select via JS (works even when standard Selenium fails)
                            try:
                                driver.execute_script(
                                    "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
                                    inp, best_opt.get_attribute("value") or best_opt.text
                                )
                                logger.info("[Select JS fallback] Set '%s' = '%s'", clean_label[:40], (best_opt.text or "")[:30])
                                continue
                            except Exception:
                                s.select_by_visible_text(best_opt.text)
                                logger.info("[Select fallback] Picked '%s' for '%s'", best_opt.text, clean_label[:50])
                                continue
                    except Exception:
                        pass
                    return clean_label
                continue

            # ── Handle checkbox ────────────────────────────────────────
            if itype == "checkbox":
                if answer and answer.lower() in {"yes", "true", "y", "1", "agree"}:
                    if not inp.is_selected():
                        _click(driver, inp)
                continue

            # ── Handle radio ───────────────────────────────────────────
            if itype == "radio":
                if not answer:
                    return clean_label
                if not _try_select_radio(driver, By, clean_label, answer):
                    # Fallback: find any unfilled radio fieldset and click matching option
                    filled = False
                    try:
                        for fs in modal.find_elements(By.CSS_SELECTOR, "fieldset"):
                            if not _is_visible(fs):
                                continue
                            radios = fs.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                            if any(r.is_selected() for r in radios if _is_visible(r)):
                                continue  # already answered
                            answer_l = answer.strip().lower()
                            answer_norm = answer_l.replace("/", " or ").replace("&", " and ").replace("  ", " ")
                            for lab2 in fs.find_elements(By.CSS_SELECTOR, "label"):
                                lab_t = (lab2.text or "").strip().lower()
                                if not lab_t:
                                    continue
                                lab_norm = lab_t.replace("/", " or ").replace("&", " and ").replace("  ", " ")
                                if lab_t == answer_l or lab_norm == answer_norm or lab_t.startswith(answer_l) or answer_l in lab_t or answer_norm in lab_norm or lab_norm in answer_norm:
                                    _click(driver, lab2)
                                    filled = True
                                    logger.info("[Radio fallback] Clicked '%s' for Q '%s'", lab2.text, clean_label[:50])
                                    break
                            # If yes/no and no text match, click first option for "yes"
                            if not filled and answer_l in {"yes", "y", "true"}:
                                vis_labels = [l for l in fs.find_elements(By.CSS_SELECTOR, "label") if (l.text or "").strip() and _is_visible(l)]
                                if vis_labels:
                                    _click(driver, vis_labels[0])
                                    filled = True
                                    logger.info("[Radio fallback] Clicked first option for 'Yes'")
                            if filled:
                                break
                    except Exception:
                        pass
                    if not filled:
                        return clean_label
                continue

            # ── Plain text / number / tel field ────────────────────────
            if not answer:
                return clean_label

            # Type coercion for integer-only fields
            if _is_integer_field(inp):
                coerced = _coerce_to_int(answer)
                if coerced is None:
                    logger.warning("Cannot coerce %r to int for %r", answer, clean_label)
                    return clean_label
                answer = coerced

            # Typeahead/autocomplete fields need special handling
            if _is_typeahead(inp):
                _fill_typeahead(driver, By, inp, answer)
            else:
                _fill_text(inp, answer)

        except Exception as exc:
            logger.warning("form-walk error on label %r: %s", lab, exc)
            continue

    # ── PASS 2: aria-label / placeholder based inputs (not caught above) ─
    # Catches inputs that LinkedIn renders without a <label for="..."> association
    try:
        all_inputs = modal.find_elements(
            By.CSS_SELECTOR,
            "input:not([type='hidden']):not([type='submit']):not([type='button'])"
            ":not([type='checkbox']):not([type='radio']), select, textarea"
        )
        for inp in all_inputs:
            try:
                if not _is_visible(inp):
                    continue
                inp_id = inp.get_attribute("id") or ""
                if inp_id and inp_id in processed_ids:
                    continue

                # Already filled?
                current = (inp.get_attribute("value") or "").strip()
                tag   = (inp.tag_name or "").lower()
                itype = (inp.get_attribute("type") or "").lower()
                if current and tag != "select":
                    continue

                # Derive label from aria-label, placeholder, or name attribute
                raw_label = (
                    inp.get_attribute("aria-label") or
                    inp.get_attribute("placeholder") or
                    inp.get_attribute("name") or
                    ""
                ).strip()
                if not raw_label:
                    continue

                clean_label = _clean_label(raw_label)
                ll = clean_label.lower().strip()

                if inp_id:
                    processed_ids.add(inp_id)

                # ── 1. Profile heuristics ──────────────────────────────
                answer = _profile_answer(ll, cv, profile)

                # ── 2. Answers bank ────────────────────────────────────
                if not answer:
                    answer = bank.get(ll)
                if not answer:
                    for bq, ba in bank.items():
                        if bq in ll or ll in bq:
                            answer = ba
                            break

                # ── 3. Groq LLM ────────────────────────────────────────
                if not answer and api_key:
                    opts = _get_select_options(driver, By, inp) if tag == "select" else []
                    ftype = "select" if tag == "select" else ("number" if itype == "number" else "text")
                    groq_ans, confident = _groq_answer_question(
                        clean_label, ftype, opts, profile, cv,
                        api_key, api_base, api_model,
                        answers_bank=answers,
                    )
                    if groq_ans and confident:
                        answer = groq_ans
                        if new_answers is not None:
                            new_answers.append({"question": clean_label, "answer": groq_ans})
                    elif groq_ans and not confident:
                        logger.info("[Groq] uncertain (aria-label pass) — pending: %r", clean_label)
                        return clean_label

                if not answer:
                    # Unknown unlabelled field — skip rather than fail
                    logger.debug("Skipping unlabelled field %r (no answer found)", clean_label)
                    continue

                if tag == "select":
                    sel_value = (inp.get_attribute("value") or "").strip()
                    if sel_value:
                        continue
                    if not _try_select_option(driver, By, inp, answer):
                        logger.warning("Could not select %r for %r — skipping", answer, clean_label)
                    continue

                if _is_integer_field(inp):
                    coerced = _coerce_to_int(answer)
                    if coerced:
                        answer = coerced

                if _is_typeahead(inp):
                    _fill_typeahead(driver, By, inp, answer)
                else:
                    _fill_text(inp, answer)

            except Exception as exc:
                logger.debug("aria-label pass error: %s", exc)
                continue
    except Exception:
        pass

    # ── PASS 2.5: SDUI combobox / custom-select dropdowns ─────────────────
    # LinkedIn renders some dropdowns as <input role="combobox"> with a
    # <div role="listbox"> that appears on click. These are NOT <select>.
    try:
        for cb in modal.find_elements(By.CSS_SELECTOR,
                "input[role='combobox'], input[aria-autocomplete='list'], input[aria-autocomplete='both']"):
            try:
                if not _is_visible(cb):
                    continue
                cb_id = cb.get_attribute("id") or ""
                if cb_id and cb_id in processed_ids:
                    continue
                val = (cb.get_attribute("value") or "").strip()
                if val:
                    if cb_id:
                        processed_ids.add(cb_id)
                    continue  # already filled

                # Get label
                lbl = ""
                try:
                    if cb_id:
                        lab_el = modal.find_element(By.CSS_SELECTOR, f"label[for='{cb_id}']")
                        lbl = (lab_el.text or "").strip()
                except Exception:
                    pass
                if not lbl:
                    lbl = (cb.get_attribute("aria-label") or cb.get_attribute("placeholder") or "").strip()
                if not lbl:
                    continue

                if cb_id:
                    processed_ids.add(cb_id)

                clean_lbl = _clean_label(lbl)
                ll = clean_lbl.lower().strip()

                # 1. Heuristic
                answer = _profile_answer(ll, cv, profile)
                # 2. Bank
                if not answer:
                    answer = bank.get(ll)
                if not answer:
                    for bq, ba in bank.items():
                        if bq in ll or ll in bq:
                            answer = ba
                            break
                # 3. Groq
                if not answer and api_key:
                    groq_ans, confident = _groq_answer_question(
                        clean_lbl, "text", [], profile, cv,
                        api_key, api_base, api_model,
                        answers_bank=answers,
                    )
                    if groq_ans and confident:
                        answer = groq_ans
                        if new_answers is not None:
                            new_answers.append({"question": clean_lbl, "answer": groq_ans})

                if not answer:
                    return clean_lbl  # can't answer → pending

                # Fill via SDUI dropdown handler
                if not _fill_sdui_dropdown(driver, By, cb, answer, label=clean_lbl):
                    # Fallback: plain typeahead
                    _fill_typeahead(driver, By, cb, answer)
                logger.info("[Pass2.5 SDUI] Filled '%s' = '%s'", clean_lbl[:40], answer[:30])

            except Exception as exc:
                logger.debug("SDUI combobox pass error: %s", exc)
                continue
    except Exception:
        pass

    # ── PASS 3: Radio fieldsets without explicit label→input pairs ────────
    try:
        for fs in modal.find_elements(By.CSS_SELECTOR, "fieldset"):
            if not _is_visible(fs):
                continue
            try:
                legend = fs.find_element(By.CSS_SELECTOR, "legend, span")
                question_raw = (legend.text or "").strip()
            except Exception:
                continue
            if not question_raw:
                continue

            # Already answered?
            radios = fs.find_elements(By.CSS_SELECTOR, "input[type='radio']")
            if any(r.is_selected() for r in radios if _is_visible(r)):
                continue

            clean_q = _clean_label(question_raw)
            ql = clean_q.lower().strip()

            # 1. Profile heuristics
            ans = _profile_answer(ql, cv, profile)

            # 2. Answers bank
            if not ans:
                ans = bank.get(ql)
            if not ans:
                for bq, ba in bank.items():
                    if bq in ql or ql in bq:
                        ans = ba
                        break

            # 3. Groq LLM
            if not ans and api_key:
                opts = _get_radio_options(driver, By, clean_q)
                groq_ans, confident = _groq_answer_question(
                    clean_q, "radio", opts, profile, cv,
                    api_key, api_base, api_model,
                    answers_bank=answers,
                )
                if groq_ans and confident:
                    ans = groq_ans
                    if new_answers is not None:
                        new_answers.append({"question": clean_q, "answer": groq_ans})
                elif groq_ans and not confident:
                    logger.info("[Groq] uncertain radio — pending: %r", clean_q)
                    return clean_q

            if not ans:
                return clean_q
            # Pass clean_q (not the raw multi-line question) for legend matching
            if not _try_select_radio(driver, By, clean_q, ans):
                # Direct fallback: click the label inside THIS fieldset
                ans_l = ans.strip().lower()
                clicked = False
                for lab2 in fs.find_elements(By.CSS_SELECTOR, "label"):
                    lab_t = (lab2.text or "").strip().lower()
                    if lab_t and (lab_t == ans_l or lab_t.startswith(ans_l) or ans_l in lab_t):
                        _click(driver, lab2)
                        clicked = True
                        logger.info("[Pass3 fallback] Clicked '%s' for '%s'", lab2.text, clean_q[:50])
                        break
                if not clicked and ans_l in {"yes", "y", "true"}:
                    vis_labels = [l for l in fs.find_elements(By.CSS_SELECTOR, "label") if (l.text or "").strip() and _is_visible(l)]
                    if vis_labels:
                        _click(driver, vis_labels[0])
                        clicked = True
                        logger.info("[Pass3 fallback] Clicked first option for 'Yes'")
                if not clicked:
                    return clean_q
    except Exception:
        pass

    # ── PASS 4: Custom checkboxes, agreement terms, file uploads ─────────
    # These are the "invisible" fields that cause validation errors.
    # LinkedIn renders them as custom <div>, <label> without standard for= association.
    try:
        # 4a. Unchecked required checkboxes (terms, agreements, acknowledgements)
        for cb in modal.find_elements(By.CSS_SELECTOR,
                "input[type='checkbox']"):
            if not _is_visible(cb):
                continue
            if cb.is_selected():
                continue
            # Look at surrounding text to decide
            try:
                parent = cb.find_element(By.XPATH, "./..")
                text = (parent.text or "").lower()
            except Exception:
                text = ""
            # Auto-check any agreement / terms / acknowledge / consent checkbox
            if any(kw in text for kw in [
                "agree", "terms", "acknowledge", "consent", "confirm",
                "certif", "accept", "understand", "attest", "privacy",
                "data processing", "accurate", "truthful",
            ]):
                _click(driver, cb)
                logger.info("[Pass4] Auto-checked agreement checkbox: %s", text[:80])
            # If the checkbox has no surrounding text at all (LinkedIn custom),
            # and it's the ONLY unchecked checkbox — check it (likely terms)
            elif not text.strip():
                _click(driver, cb)
                logger.info("[Pass4] Checked orphan checkbox (likely terms)")
    except Exception:
        pass

    try:
        # 4b. "Follow company" checkbox — UNCHECK it if checked
        for cb in modal.find_elements(By.CSS_SELECTOR,
                "input[type='checkbox']"):
            if not _is_visible(cb):
                continue
            try:
                parent = cb.find_element(By.XPATH, "./..")
                text = (parent.text or "").lower()
            except Exception:
                text = ""
            if "follow" in text and cb.is_selected():
                _click(driver, cb)
                logger.info("[Pass4] Unchecked 'Follow company' checkbox")
    except Exception:
        pass

    try:
        # 4c. Resume/CV upload — if LinkedIn shows a resume upload section,
        # check if there's already an uploaded file. If not, try clicking
        # "Upload resume" to use the default one already on the profile.
        for el in modal.find_elements(By.CSS_SELECTOR,
                "button, label, span, div"):
            if not _is_visible(el):
                continue
            txt = (el.text or "").strip().lower()
            if "upload resume" in txt or "upload cv" in txt or "upload your resume" in txt:
                # Check if a file is already listed
                try:
                    uploaded = modal.find_element(By.CSS_SELECTOR,
                        ".jobs-document-upload-redesign-card__file-name, "
                        "[data-test-document-name], "
                        ".artdeco-inline-feedback")
                    if uploaded.text.strip():
                        logger.info("[Pass4] Resume already uploaded: %s", uploaded.text[:50])
                        break
                except Exception:
                    pass
                # No file listed — look for a "Use profile" or first available option
                for opt in modal.find_elements(By.CSS_SELECTOR, "button, label"):
                    opt_text = (opt.text or "").lower()
                    if "profile" in opt_text or "most recent" in opt_text or "use" in opt_text:
                        _click(driver, opt)
                        logger.info("[Pass4] Selected profile resume option")
                        time.sleep(0.5)
                        break
                break
    except Exception:
        pass

    return None


# ────────────────────────────────────────────────────────────────────────────
# Modal close helper
# ────────────────────────────────────────────────────────────────────────────

def _close_modal(driver, By):
    try:
        modal = _modal(driver, By)
        if not modal:
            return
        for sel in ["button[aria-label*='Dismiss']",
                    "button[aria-label*='dismiss']",
                    "button.artdeco-modal__dismiss"]:
            try:
                btn = modal.find_element(By.CSS_SELECTOR, sel)
                _click(driver, btn)
                break
            except Exception:
                pass
        time.sleep(0.7)
        try:
            for b in driver.find_elements(By.CSS_SELECTOR, "button"):
                if not _is_visible(b):
                    continue
                if (b.text or "").strip().lower() == "discard":
                    _click(driver, b)
                    break
        except Exception:
            pass
    except Exception:
        pass


def _looks_submitted(driver, By) -> bool:
    try:
        modal = _modal(driver, By)
        if not modal:
            return False
        text = (modal.text or "").lower()
    except Exception:
        return False
    return any(p in text for p in (
        "your application was sent",
        "application sent",
        "application submitted",
        "applied to",
    ))


def _get_validation_errors(driver, By) -> List[str]:
    """Collect any visible inline validation error messages from the modal."""
    errors = []
    try:
        modal = _modal(driver, By)
        if not modal:
            return []
        for sel in [
            ".artdeco-inline-feedback__message",
            ".fb-form-element__error",
            "[data-test-form-element-error-message]",
            ".jobs-easy-apply-form-element__error",
        ]:
            try:
                for el in modal.find_elements(By.CSS_SELECTOR, sel):
                    txt = (el.text or "").strip()
                    if txt and _is_visible(el):
                        errors.append(txt)
            except Exception:
                pass
    except Exception:
        pass
    return errors


def _pending_result(question: str, new_answers: List[dict], error: str = None) -> dict:
    """Uniform result for recoverable Easy Apply form blockers."""
    return {
        "status": "pending",
        "pending_question": question or "Easy Apply form needs review",
        "error": error,
        "new_answers": new_answers,
    }


def _field_pending_label(field: dict) -> str:
    label = (field.get("label") or field.get("id") or "required field").strip()
    ftype = (field.get("type") or "field").strip()
    options = [str(o).strip() for o in (field.get("options") or []) if str(o).strip()]
    if options:
        return f"{label} ({ftype}; options: {', '.join(options[:8])})"
    return f"{label} ({ftype})"


def _selection_pending_question(driver, By, snap: dict, fallback: str) -> str:
    """Turn generic LinkedIn validation into a user-actionable pending prompt."""
    fields = list((snap or {}).get("fields") or [])
    selection_types = {"select", "combobox", "radio", "checkbox", "typeahead"}
    candidates = []
    for f in fields:
        if (f.get("type") or "").lower() not in selection_types:
            continue
        if not f.get("required") and (f.get("type") or "").lower() not in {"select", "combobox", "radio"}:
            continue
        try:
            if _field_satisfied(driver, By, f):
                continue
        except Exception:
            pass
        candidates.append(f)

    if candidates:
        if len(candidates) == 1:
            return f"Please answer: {_field_pending_label(candidates[0])}"
        joined = "; ".join(_field_pending_label(f) for f in candidates[:4])
        return f"Please answer one of these required selections: {joined}"

    errors = "; ".join((snap or {}).get("validation_errors") or []) or fallback
    page = (snap or {}).get("step_title") or ""
    if page:
        return f"{page}: {errors}"
    return errors


def _field_satisfied(driver, By, field: dict) -> bool:
    """Best-effort verification that a required field now has a value/selection."""
    el = field.get("element")
    ftype = (field.get("type") or "text").lower()
    if el is None:
        return False

    def meaningful(text: str) -> bool:
        t = (text or "").strip().lower()
        return bool(t and t not in {
            "select",
            "select an option",
            "-- select --",
            "choose one",
            "please select",
            "required",
        })

    try:
        if ftype == "file":
            return True
        if ftype in ("radio",):
            try:
                fs = el.find_element(By.XPATH, "ancestor::fieldset[1]")
                radios = fs.find_elements(By.CSS_SELECTOR, "input[type='radio']")
            except Exception:
                radios = [el]
            return any(r.is_selected() for r in radios)
        if ftype == "checkbox":
            # Required checkboxes generally mean acknowledge/agree.
            return bool(el.is_selected())
        if ftype == "select":
            try:
                from selenium.webdriver.support.ui import Select
                selected = Select(el).first_selected_option
                return meaningful(selected.text) and meaningful(selected.get_attribute("value") or selected.text)
            except Exception:
                return meaningful(el.get_attribute("value") or "")
        if ftype in ("combobox", "typeahead"):
            value = (el.get_attribute("value") or "").strip()
            text = (el.text or "").strip()
            return meaningful(value or text)
        return meaningful(el.get_attribute("value") or "")
    except Exception:
        return False


def _last_chance_repair(driver, By, snap: dict, failed_fields: List[dict],
                        profile: dict, cv: dict, api_key: str, api_base: str,
                        api_model: str, filler, brain, new_answers: List[dict]) -> bool:
    """Ask the LLM one more time using validation context and retry failed fields."""
    if not failed_fields or not api_key:
        return False

    repair_snapshot = dict(snap or {})
    errors = list(repair_snapshot.get("validation_errors") or [])
    visible_errors = _get_validation_errors(driver, By)
    for err in visible_errors:
        if err not in errors:
            errors.append(err)
    if not errors:
        labels = ", ".join((f.get("label") or f.get("id") or "field") for f in failed_fields)
        errors.append(f"These required Easy Apply fields did not accept the previous answer: {labels}")
    repair_snapshot["validation_errors"] = errors

    llm_answers = brain.llm_answer_fields(
        repair_snapshot, failed_fields, profile, cv, api_key, api_base, api_model
    )

    repaired_any = False
    for f in failed_fields:
        llm = llm_answers.get(f["id"])
        if not llm or not llm.get("value") or not llm.get("confident"):
            continue
        value = llm["value"]
        if filler.fill_field(driver, By, f, value) and _field_satisfied(driver, By, f):
            repaired_any = True
            if f.get("label"):
                new_answers.append({"question": f["label"], "answer": value})
    return repaired_any


# ────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ────────────────────────────────────────────────────────────────────────────

def apply_easy(
    driver,
    job_url: str,
    cv: dict,
    answers: List[dict],
    profile: dict = None,
    api_key: str = "",
    api_base: str = "https://api.groq.com/openai/v1",
    api_model: str = "llama-3.3-70b-versatile",
    max_steps: int = 25,
) -> dict:
    """
    Submit one Easy Apply form using the AI-first engine.
    Driver must already be authenticated to LinkedIn.

    Per-step flow:
      1. Snapshot the modal (every field, every option, validation errors)
      2. Resolve fields: profile heuristics → answers bank → LLM (one call)
      3. Smart fillers click/type/select per field type
      4. Click Next
      5. If validation errors appear: re-snapshot, ask LLM to correct, retry
      6. On submit page: confirm submission
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    # Local imports of the new AI-first modules
    from . import form_inspector as inspector
    from . import form_brain     as brain
    from . import form_filler    as filler

    if profile is None:
        profile = {}

    new_answers: List[dict] = []

    try:
        apply_url = job_url.rstrip("/") + "/apply/?openSDUIApplyFlow=true"
        logger.info("Navigating to apply URL: %s", apply_url)
        driver.get(apply_url)
        time.sleep(3)
    except Exception as exc:
        return {"status": "error", "error": f"Navigation failed: {exc}",
                "pending_question": None, "new_answers": []}

    if "/login" in (driver.current_url or "") or "/checkpoint" in (driver.current_url or ""):
        return {"status": "error", "error": "LinkedIn session expired (redirected to login)",
                "pending_question": None, "new_answers": []}

    # Detect already-applied
    try:
        body = (driver.find_element(By.TAG_NAME, "body").text or "").lower()
        if "applied " in body and ("you applied" in body or "you've applied" in body):
            return {"status": "submitted", "error": None, "pending_question": None,
                    "new_answers": [], "note": "Already applied earlier"}
    except Exception:
        pass

    # Wait for SDUI apply dialog
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR,
            "div[role='dialog'], .jobs-easy-apply-modal, div[role='dialog'].artdeco-modal")))
        time.sleep(1)
    except TimeoutException:
        logger.info("SDUI dialog not found, trying button click fallback")
        btn = _find_easy_apply_button(driver, By)
        if not btn:
            return {"status": "not_easy_apply", "pending_question": None,
                    "error": None, "new_answers": []}
        _click(driver, btn)
        try:
            WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.CSS_SELECTOR,
                "div[role='dialog'], .jobs-easy-apply-modal")))
        except TimeoutException:
            return {"status": "error", "error": "Apply form did not open",
                    "pending_question": None, "new_answers": []}

    # ── AI-first form loop ────────────────────────────────────────────────
    seen_step_signatures: List[str] = []   # track form pages we've completed
    validation_retry_count = 0             # how many times we've retried THIS page
    repair_attempts_by_signature: dict[str, int] = {}

    for step in range(max_steps):
        snap = inspector.snapshot(driver, By)
        if not snap:
            return _pending_result(
                "Easy Apply form disappeared before submission could be verified",
                new_answers,
                "Modal disappeared mid-form",
            )

        # Build a stable signature for this page (labels + options) so we can
        # detect when we've stalled vs genuinely advanced.
        sig = "|".join(f"{f['label']}::{f['type']}::{','.join(f.get('options') or [])}"
                       for f in snap["fields"])
        is_same_page = bool(sig and seen_step_signatures and seen_step_signatures[-1] == sig)
        if is_same_page:
            validation_retry_count += 1
        else:
            validation_retry_count = 0
            seen_step_signatures.append(sig)

        # Hard stop: tried this page 3 times and it still won't advance
        if validation_retry_count >= 3:
            errors = snap.get("validation_errors") or []
            err_detail = "; ".join(errors) if errors else "form won't advance — unknown required field"
            logger.warning("Page stuck after 3 retries: %s", err_detail)
            pending_question = _selection_pending_question(driver, By, snap, err_detail)
            _close_modal(driver, By)
            return _pending_result(pending_question, new_answers, f"Form field we couldn't fill: {err_detail}")

        # ── 1. Resolve every field ────────────────────────────────────────
        # Order: profile → bank → LLM (one call for all remaining)
        unresolved: List[dict] = []
        prefilled_answers: dict = {}   # {field_id: value}
        pending_label: Optional[str] = None

        for f in snap["fields"]:
            # Skip fields that already have a value (carried over from previous step)
            if f.get("current") and f["type"] not in ("radio", "checkbox", "select", "combobox"):
                continue
            # Skip file inputs (LinkedIn uses your stored resume)
            if f["type"] == "file":
                continue
            # 1. Profile heuristics
            ans = brain.profile_lookup(f["label"], cv, profile)
            if ans:
                prefilled_answers[f["id"]] = ans
                continue
            # 2. Answers bank
            ans = brain.bank_lookup(f["label"], answers)
            if ans:
                prefilled_answers[f["id"]] = ans
                continue
            # 3. Defer to LLM
            unresolved.append(f)

        # ── 2. One LLM call for everything we couldn't resolve locally ───
        llm_answers: dict = {}
        if unresolved and api_key:
            llm_answers = brain.llm_answer_fields(
                snap, unresolved, profile, cv,
                api_key, api_base, api_model,
            )

        # ── 3. Decide final value per field, route to pending if uncertain
        final_answers: dict = {}
        for f in snap["fields"]:
            fid = f["id"]
            # Field already has a value in the DOM (pre-filled by LinkedIn) — nothing to do
            if f.get("current") and f["type"] not in ("radio", "checkbox", "select", "combobox"):
                continue
            if fid in prefilled_answers:
                final_answers[fid] = prefilled_answers[fid]
                continue
            llm = llm_answers.get(fid)
            if llm and llm.get("value") and llm.get("confident"):
                final_answers[fid] = llm["value"]
                # Save Groq-generated answer for the bank
                if f.get("label"):
                    new_answers.append({"question": f["label"], "answer": llm["value"]})
                continue
            if llm and llm.get("value") and not llm.get("confident"):
                # LLM responded but isn't confident — pending
                pending_label = f["label"] or "Unknown question"
                logger.info("[AI] Uncertain on %r — routing to pending", pending_label)
                break
            if f["type"] == "checkbox":
                # Optional checkboxes are fine to skip
                continue
            if not f.get("required") and f["type"] in ("text", "textarea", "email", "url"):
                # Optional free-text — leave empty
                continue
            # Required field with no answer → pending
            pending_label = f["label"] or "Unknown question"
            logger.info("[AI] No answer for required %r — pending", pending_label)
            break

        if pending_label:
            _close_modal(driver, By)
            return _pending_result(pending_label, new_answers)

        # ── 4. Fill every field with its resolved value ──────────────────
        failed_required: List[dict] = []
        for f in snap["fields"]:
            fid = f["id"]
            value = final_answers.get(fid)
            if value is None:
                continue
            ok = filler.fill_field(driver, By, f, value)
            if not ok:
                logger.warning("Filler couldn't write %r → %r (type=%s)",
                              f.get("label"), str(value)[:40], f["type"])
            if f.get("required") and not _field_satisfied(driver, By, f):
                failed_required.append(f)

        if failed_required:
            repair_count = repair_attempts_by_signature.get(sig, 0)
            if repair_count < 2:
                repair_attempts_by_signature[sig] = repair_count + 1
                if _last_chance_repair(
                    driver, By, snap, failed_required, profile, cv,
                    api_key, api_base, api_model, filler, brain, new_answers
                ):
                    still_failed = [f for f in failed_required if not _field_satisfied(driver, By, f)]
                    if not still_failed:
                        failed_required = []
                    else:
                        failed_required = still_failed
            if failed_required:
                labels = "; ".join(_field_pending_label(f) for f in failed_required)
                _close_modal(driver, By)
                return _pending_result(
                    f"Required Easy Apply field did not accept an answer: {labels}",
                    new_answers,
                )

        # ── 5. Click Next / Review / Submit ──────────────────────────────
        nxt = _next_or_submit_button(driver, By)
        if not nxt:
            _close_modal(driver, By)
            return _pending_result(
                "Easy Apply form has no visible Next, Review, or Submit button",
                new_answers,
                "No Next/Submit button found",
            )
        kind, el = nxt
        _click(driver, el)
        time.sleep(1.6)

        if kind == "submit":
            for _ in range(14):
                if _looks_submitted(driver, By):
                    return {"status": "submitted", "pending_question": None,
                            "error": None, "new_answers": new_answers}
                time.sleep(0.5)
            if _modal(driver, By) is None:
                return {"status": "submitted", "pending_question": None,
                        "error": None, "new_answers": new_answers,
                        "note": "Submitted but no confirmation modal observed"}
            _close_modal(driver, By)
            return _pending_result(
                "Submit clicked but LinkedIn did not show a confirmation",
                new_answers,
                "Submit clicked but no confirmation",
            )

    _close_modal(driver, By)
    return _pending_result(
        "Easy Apply form did not reach submit after the maximum number of steps",
        new_answers,
        "Too many steps without submit",
    )
