"""
Real LinkedIn Easy Apply submitter.

Given a Selenium driver + job URL + CV/answer-bank, this module:
1. Navigates to the job page.
2. Clicks the Easy Apply button.
3. Walks the multi-step form, filling text/numeric/dropdown/radio inputs from
   the CV and the saved answer bank.
4. Hits Next/Review/Submit until either:
    - submission is confirmed (success modal) → returns "submitted"
    - an unanswered question is hit          → modal is discarded, returns "pending"
    - any unrecoverable error                → returns "error"

Returns:
    {
      "status": "submitted" | "pending" | "not_easy_apply" | "error",
      "pending_question": str | None,
      "error": str | None,
    }
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional, List

logger = logging.getLogger(__name__)


# ── small helpers ────────────────────────────────────────────────────────
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
    # LinkedIn 2026: classes are obfuscated, so also check for role=dialog
    for sel in [".jobs-easy-apply-modal", "div[role='dialog'].artdeco-modal", ".artdeco-modal", "div[role='dialog']"]:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            if _is_visible(el):
                return el
        except Exception:
            pass
    return None


# ── easy apply button ───────────────────────────────────────────────────
def _find_easy_apply_button(driver, By):
    candidates = []
    # LinkedIn 2026: "Easy Apply" may be an <a> tag with aria-label, not a <button>
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
    # Fallback: find by XPath text content
    if not candidates:
        try:
            for el in driver.find_elements(By.XPATH,
                    '//button[contains(., "Easy Apply")] | //a[contains(., "Easy Apply")]'):
                if _is_visible(el):
                    candidates.append(el)
        except Exception:
            pass
    return candidates[0] if candidates else None


# ── form walking ────────────────────────────────────────────────────────
def _next_or_submit_button(driver, By):
    """Find the modal's progress button. Returns ('next'|'review'|'submit', el) or None."""
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


def _phone_from_cv(cv: dict) -> str:
    raw = (cv.get("summary") or "") + " " + " ".join(cv.get("skills") or [])
    m = re.search(r"(\+?\d[\d\s\-]{8,}\d)", raw)
    return (m.group(1) if m else "")


def _email_from_cv(cv: dict) -> str:
    raw = (cv.get("summary") or "")
    m = re.search(r"[\w\.\-+]+@[\w\.\-]+\.\w+", raw)
    return (m.group(0) if m else "")


def _fill_text(el, value: str) -> bool:
    try:
        el.clear()
        el.send_keys(value)
        return True
    except Exception:
        return False


def _try_select_option(driver, By, select_el, target: str) -> bool:
    """Pick an <option> whose visible text matches `target` (case-insensitive)."""
    try:
        from selenium.webdriver.support.ui import Select
        sel = Select(select_el)
        target_lower = (target or "").strip().lower()
        # Prefer exact match
        for opt in sel.options:
            if (opt.text or "").strip().lower() == target_lower:
                sel.select_by_visible_text(opt.text); return True
        # Yes/No fallback for booleans
        for opt in sel.options:
            t = (opt.text or "").strip().lower()
            if target_lower in {"yes", "y", "true"} and t == "yes":
                sel.select_by_visible_text(opt.text); return True
            if target_lower in {"no", "n", "false"} and t == "no":
                sel.select_by_visible_text(opt.text); return True
        return False
    except Exception:
        return False


def _try_select_radio(driver, By, label_text: str, target: str) -> bool:
    """LinkedIn renders radios as `<fieldset><legend>Q?</legend><label>Yes/No</label>...`."""
    target_lower = (target or "").strip().lower()
    try:
        modal = _modal(driver, By)
        if not modal:
            return False
        # Find a fieldset whose legend contains label_text
        for fs in modal.find_elements(By.CSS_SELECTOR, "fieldset"):
            try:
                legend = fs.find_element(By.CSS_SELECTOR, "legend, span").text.lower()
            except Exception:
                continue
            if label_text.lower() not in legend:
                continue
            for lab in fs.find_elements(By.CSS_SELECTOR, "label"):
                lab_text = (lab.text or "").strip().lower()
                if not lab_text:
                    continue
                if lab_text == target_lower or lab_text.startswith(target_lower):
                    _click(driver, lab); return True
                if target_lower in {"yes","y","true"} and lab_text == "yes":
                    _click(driver, lab); return True
                if target_lower in {"no","n","false"} and lab_text == "no":
                    _click(driver, lab); return True
            return False
    except Exception:
        return False
    return False


def _walk_form_step(driver, By, cv: dict, answers: List[dict]) -> Optional[str]:
    """
    Try to fill every visible field in the modal that's currently empty.

    Returns:
        None     — every required field on this step is filled (caller may proceed)
        str      — text of the first unanswered question we couldn't resolve
                   (caller should discard the modal)
    """
    bank = {(a.get("question") or "").strip().lower(): (a.get("answer") or "")
            for a in (answers or []) if a.get("question")}

    modal = _modal(driver, By)
    if not modal:
        return None

    # Iterate label→input pairs (LinkedIn uses `for` + matching id).
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

            tag  = (inp.tag_name or "").lower()
            itype = (inp.get_attribute("type") or "").lower()

            # If already filled, skip.
            current = (inp.get_attribute("value") or "").strip()
            if current and tag != "select":
                continue

            # LinkedIn SDUI often duplicates label text with newlines + "Required" suffix
            # e.g. "Are you comfortable?\nAre you comfortable?\nRequired"
            # Clean it to just the question text
            ll_lines = [l.strip() for l in label_text.split("\n") if l.strip() and l.strip().lower() != "required"]
            clean_label = ll_lines[0] if ll_lines else label_text
            ll = clean_label.lower().strip()
            answer = bank.get(ll)
            # Fuzzy match: try matching against bank keys that contain the question
            if not answer:
                for bq, ba in bank.items():
                    if bq in ll or ll in bq:
                        answer = ba
                        break

            # Heuristic auto-answers from CV first.
            if not answer:
                if "year" in ll and "experience" in ll and cv.get("years"):
                    answer = str(cv.get("years"))
                elif ("phone" in ll or "mobile" in ll) and _phone_from_cv(cv):
                    answer = _phone_from_cv(cv)
                elif "email" in ll and _email_from_cv(cv):
                    answer = _email_from_cv(cv)
                elif "first name" in ll:
                    answer = (cv.get("first_name") or
                              ((cv.get("name") or "").split(" ", 1)[0]) or "")
                elif "last name" in ll:
                    parts = (cv.get("name") or "").split(" ", 1)
                    answer = cv.get("last_name") or (parts[1] if len(parts) > 1 else "")
                elif "name" == ll.strip():
                    answer = cv.get("name") or ""

            if tag == "select":
                # If select already has a value chosen, skip it
                sel_value = (inp.get_attribute("value") or "").strip()
                if sel_value:
                    continue
                if not answer:
                    # No saved answer for this dropdown → pending
                    return clean_label
                if not _try_select_option(driver, By, inp, answer):
                    return clean_label
                continue

            if itype == "checkbox":
                if answer and answer.lower() in {"yes", "true", "y", "1", "agree"}:
                    if not inp.is_selected():
                        _click(driver, inp)
                continue

            if itype == "radio":
                if not answer:
                    return clean_label
                if not _try_select_radio(driver, By, label_text, answer):
                    return clean_label
                continue

            # Plain text/number/email field
            if not answer:
                return clean_label
            _fill_text(inp, answer)
        except Exception as exc:
            logger.warning("form-walk error on label %r: %s", lab, exc)
            continue

    # Also handle radio fieldsets without explicit labels (some LinkedIn screens)
    try:
        for fs in modal.find_elements(By.CSS_SELECTOR, "fieldset"):
            if not _is_visible(fs):
                continue
            try:
                legend = fs.find_element(By.CSS_SELECTOR, "legend, span")
                question = (legend.text or "").strip()
            except Exception:
                continue
            if not question:
                continue
            # Already answered? (any radio inside checked)
            radios = fs.find_elements(By.CSS_SELECTOR, "input[type='radio']")
            if any(r.is_selected() for r in radios if _is_visible(r)):
                continue
            # Clean SDUI question text (same as label cleaning above)
            q_lines = [l.strip() for l in question.split("\n") if l.strip() and l.strip().lower() != "required"]
            clean_q = q_lines[0] if q_lines else question
            ans = bank.get(clean_q.strip().lower())
            # Fuzzy match
            if not ans:
                for bq, ba in bank.items():
                    if bq in clean_q.lower() or clean_q.lower() in bq:
                        ans = ba
                        break
            if not ans:
                return clean_q
            if not _try_select_radio(driver, By, question, ans):
                return clean_q
    except Exception:
        pass

    return None


def _close_modal(driver, By):
    """Close the apply modal (and confirm 'Discard' if prompted)."""
    try:
        modal = _modal(driver, By)
        if not modal:
            return
        for sel in ["button[aria-label*='Dismiss']",
                    "button[aria-label*='dismiss']",
                    "button.artdeco-modal__dismiss"]:
            try:
                btn = modal.find_element(By.CSS_SELECTOR, sel)
                _click(driver, btn); break
            except Exception:
                pass
        time.sleep(0.7)
        # confirmation dialog
        try:
            for b in driver.find_elements(By.CSS_SELECTOR, "button"):
                if not _is_visible(b): continue
                if (b.text or "").strip().lower() == "discard":
                    _click(driver, b); break
        except Exception:
            pass
    except Exception:
        pass


def _looks_submitted(driver, By) -> bool:
    """Detect LinkedIn's post-submit confirmation."""
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


# ── public entrypoint ───────────────────────────────────────────────────
def apply_easy(driver, job_url: str, cv: dict, answers: List[dict],
               max_steps: int = 8) -> dict:
    """Submit one Easy Apply form. Driver must already be authenticated to LinkedIn."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    try:
        # LinkedIn 2026: Easy Apply now uses SDUI. Navigate directly to the
        # apply URL which renders the form inline as a dialog.
        apply_url = job_url.rstrip("/") + "/apply/?openSDUIApplyFlow=true"
        logger.info("Navigating to apply URL: %s", apply_url)
        driver.get(apply_url)
        time.sleep(3)
    except Exception as exc:
        return {"status": "error", "error": f"Navigation failed: {exc}", "pending_question": None}

    if "/login" in (driver.current_url or "") or "/checkpoint" in (driver.current_url or ""):
        return {"status": "error", "error": "LinkedIn session expired (redirected to login)", "pending_question": None}

    # Detect already-applied state
    try:
        body = (driver.find_element(By.TAG_NAME, "body").text or "").lower()
        if "applied " in body and ("you applied" in body or "you've applied" in body):
            return {"status": "submitted", "error": None, "pending_question": None,
                    "note": "Already applied earlier"}
    except Exception:
        pass

    # Wait for the SDUI apply dialog to appear
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR,
            "div[role='dialog'], .jobs-easy-apply-modal, div[role='dialog'].artdeco-modal")))
        time.sleep(1)
    except TimeoutException:
        # Fallback: try clicking the Easy Apply button the old way
        logger.info("SDUI dialog not found, trying button click fallback")
        btn = _find_easy_apply_button(driver, By)
        if not btn:
            return {"status": "not_easy_apply", "pending_question": None, "error": None}
        _click(driver, btn)
        try:
            WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.CSS_SELECTOR,
                "div[role='dialog'], .jobs-easy-apply-modal")))
        except TimeoutException:
            return {"status": "error", "error": "Apply form did not open", "pending_question": None}

    for step in range(max_steps):
        unanswered = _walk_form_step(driver, By, cv, answers)
        if unanswered:
            _close_modal(driver, By)
            return {"status": "pending", "pending_question": unanswered, "error": None}

        nxt = _next_or_submit_button(driver, By)
        if not nxt:
            _close_modal(driver, By)
            return {"status": "error", "error": "No Next/Submit button found",
                    "pending_question": None}
        kind, el = nxt
        _click(driver, el)
        time.sleep(1.2)

        if kind == "submit":
            # Wait for confirmation
            for _ in range(12):
                if _looks_submitted(driver, By):
                    return {"status": "submitted", "pending_question": None, "error": None}
                time.sleep(0.5)
            # Modal closed without explicit confirmation — treat as failure to be safe.
            if _modal(driver, By) is None:
                return {"status": "submitted", "pending_question": None, "error": None,
                        "note": "Submitted but no confirmation modal observed"}
            _close_modal(driver, By)
            return {"status": "error", "error": "Submit clicked but no confirmation",
                    "pending_question": None}

    _close_modal(driver, By)
    return {"status": "error", "error": "Too many steps without submit",
            "pending_question": None}
