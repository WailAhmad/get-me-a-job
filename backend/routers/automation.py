"""
Automation engine.

Runs in a background thread. Discovers candidate jobs, scores them
against the CV semantically (keyword-overlap stand-in), and:

- Easy Apply jobs   → auto-apply (subject to per-day / per-hour caps),
                       except when an unknown question appears, which goes
                       to Pending Review and waits for a human answer.
- Non-Easy-Apply    → routed to External Jobs, ranked by score + recency.
- Already applied   → memorised by job_id; never re-applied or re-shown.

This implementation is a high-fidelity simulation: it produces real,
persistent rows in state.json so the UI behaves identically to a future
real-LinkedIn version. Swap `_discover_jobs` with a Selenium scraper to go
live without touching the rest of the engine.
"""
import asyncio
import json
import random
import threading
import time
from datetime import datetime, timezone
from collections import deque
from typing import Tuple, List
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend import state
from backend.services import session_manager as sm

router = APIRouter(prefix="/automation", tags=["automation"])

# ── Caps ──────────────────────────────────────────────────────────────
# No caps — apply to all matched jobs. Counters kept for stats only.

# ── Sample data pool (used for the simulated discovery step) ──────────
ROLES_POOL = [
    "AI Product Manager", "Data Science Manager", "ML Engineer",
    "Senior Data Analyst", "Strategy Manager", "Digital Transformation Lead",
    "Operations Manager", "Business Intelligence Lead", "Head of Analytics",
    "Director of AI", "Product Owner", "Chief Data Officer",
    "Risk Analytics Lead", "AI Solutions Architect", "Data Engineering Manager",
]
COMPANIES = [
    "ADNOC", "Emirates NBD", "Accenture Middle East", "PwC Dubai",
    "Amazon MENA", "Google Gulf", "Mastercard UAE", "Oliver Wyman",
    "McKinsey Riyadh", "KPMG Qatar", "Noon.com", "Chalhoub Group",
    "Aramco Digital", "Etihad", "Careem", "Talabat", "Stc",
]
SOURCE_URLS = {
    "linkedin": "https://www.linkedin.com/jobs/view/{id}",
    "indeed": "https://www.indeed.com/viewjob?jk={id}",
    "naukrigulf": "https://www.naukrigulf.com/job/{id}",
    "gulftalent": "https://www.gulftalent.com/jobs/{id}",
    "bayt": "https://www.bayt.com/en/job/{id}",
    "glassdoor": "https://www.glassdoor.com/job-listing/{id}",
}
KNOWN_QUESTIONS = [
    "How many years of experience do you have with Python?",
    "Are you authorised to work in the country?",
    "What is your notice period?",
    "Do you have a Bachelor's degree?",
]
UNKNOWN_QUESTIONS = [
    "What is your expected monthly salary in local currency?",
    "Are you willing to relocate within 2 weeks?",
    "Do you require visa sponsorship now or in the future?",
    "How many years of experience do you have managing P&L?",
]


# ── Cap helpers ───────────────────────────────────────────────────────
def _today_key() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _increment_counters():
    """Increments today/hour counters for stats tracking (no caps)."""
    now = time.time()
    today = _today_key()
    s = state.get()
    auto = s["automation"]
    hour_start = auto.get("hour_window_start") or 0
    if auto.get("today_date") != today:
        auto["today_date"] = today
        auto["today_count"] = 0
    if not hour_start or (now - hour_start) > 3600:
        auto["hour_window_start"] = now
        auto["hour_count"] = 0
    auto["today_count"] += 1
    auto["hour_count"] += 1
    state.save()


# ── Scoring ───────────────────────────────────────────────────────────
# Learned from 50+ real applications by the user (AI & Data Strategy Leader)

# PRIMARY domain keywords — at least one MUST appear for a match
_PRIMARY_DOMAIN = {
    "ai": 18, "artificial intelligence": 20, "machine learning": 18, "ml ": 12,
    "data": 14, "data science": 18, "analytics": 12, "data engineer": 14,
    "digital transformation": 16, "cognitive": 14,
    "intelligence": 10, "emerging technolog": 12,
    "databricks": 14, "nlp": 12, "deep learning": 14,
    "computer vision": 12, "llm": 14, "generative ai": 16,
    # Broader tech keywords — the user is a technology leader
    "technology": 10, "information technology": 14, "it ": 8,
    "governance": 10, "data governance": 16,
    "transformation": 10, "digital": 8,
    "automation": 10, "platform": 8, "cloud": 8,
    "product": 6, "solutions": 8, "architecture": 10,
    "innovation": 10, "strategy": 8,
}

# MODIFIER keywords — bonus points on top of primary match
_MODIFIER_DOMAIN = {
    "smart": 4, "agile": 4, "enterprise": 4,
    "product manager": 6, "product owner": 6,
    "infrastructure": 4, "delivery": 3, "consulting": 4,
    "program": 4, "portfolio": 4, "operations": 3,
}

# Seniority levels matching user's profile (15 years, PhD, Head/Director-level)
_SENIORITY_KEYWORDS = {
    "head of": 16, "director": 14, "vice president": 16, "vp ": 14,
    "chief": 18, "cdo": 16, "cto": 14, "cio": 12,
    "senior manager": 10, "senior leader": 12, "lead": 8,
    "architect": 10, "principal": 8, "manager": 4,
    "senior": 6, "sr.": 4, "sr ": 4,
}

# Hard blacklist — these roles are NEVER relevant regardless of other keywords
_BLACKLIST = [
    # Sales (ALL forms)
    "sales", "account executive", "business development representative",
    "bdr", "sdr", "business developer", "business development",
    "industrial services",
    # Legal
    "legal", "lawyer", "attorney", "paralegal", "counsel",
    # HR
    "human resources", "hr manager", "hr director", "recruiter",
    "talent acquisition", "hr business partner", "hr coordinator",
    "people operations",
    # Marketing (non-digital)
    "marketing manager", "marketing director", "social media manager",
    "seo specialist", "content writer", "copywriter",
    "growth marketing", "marketing executive", "funnels",
    # Finance/Accounting
    "accounting", "accountant", "auditor", "bookkeeper", "tax",
    "financial analyst", "finance manager",
    # Construction/Engineering (non-software)
    "construction", "civil engineer", "mechanical engineer", "structural",
    "electrical engineer", "chemical engineer",
    # Medical / Pharmaceutical / Lab
    "medical", "nurse", "doctor", "physician", "clinical", "healthcare",
    "pharmacist", "dentist", "laboratory", "lab technician", "flavour",
    "pharma", "cosmetic", "analytical laboratory",
    # Education
    "teacher", "teaching", "professor", "lecturer", "tutor",
    # Operations/Logistics
    "logistics", "warehouse", "supply chain", "procurement",
    "customer service", "customer support", "call center",
    # CRM / Pure development (not AI/Data leadership)
    "crm development", "crm operations", "scrum master",
    # Cloud/Linux operations (not AI)
    "linux operations", "cloud operations engineer",
    "operations support systems",
    # Aviation/Specialized
    "airworthiness", "aviation compliance", "flight",
    "plm ", "3d model", "cad ",
    # Entry-level / irrelevant
    "campus creator", "internship", "junior developer", "entry level",
    "intern ", "graduate trainee",
    # Administrative
    "receptionist", "administrative assistant", "secretary", "clerk",
    # Hospitality
    "chef", "cook", "restaurant", "hospitality", "barista",
    # Blue collar
    "driver", "delivery driver", "courier",
    "security guard", "janitor", "cleaner",
    "petroleum", "geologist", "drilling",
    # DevOps / pure infra (not AI)
    "devops", "site reliability", "sre ", "network engineer",
    "system administrator", "sysadmin", "workflow engineer",
    "engineering specialist", "automation engineer", "digitalization engineer",
    # Freelance / contract training
    "freelance", "freelancer", "trainer",
    # Design (non-product)
    "graphic designer", "ui designer", "ux designer",
    "interior designer", "fashion",
    # QA / Testing (not AI)
    "qa engineer", "quality assurance", "test engineer", "tester",
    # IAM / Security (not AI)
    "iam lead", "iam engineer", "identity access",
    # Backend/Frontend development (not AI leadership)
    "backend engineer", "frontend engineer", "full stack developer",
    "react developer", "angular developer", "node developer",
    # Archives / Library / Museum
    "archives", "archivist", "librarian", "museum", "curator",
    # Real estate
    "real estate", "property manager", "leasing",
    # Insurance
    "insurance", "underwriter", "actuary", "claims",
    # Retail
    "retail", "store manager", "merchandiser", "cashier",
    # Sports
    "sports", "fitness", "coach", "athletic",
    # Agriculture
    "agriculture", "farming", "livestock", "veterinar",
    # Media (non-data)
    "journalist", "reporter", "editor", "news", "media specialist",
    "data visualization",
    # Translation
    "translator", "interpreter", "linguist",
    # Shipping / Maritime
    "maritime", "shipping", "vessel", "marine",
]

# Valid GCC + common target locations
_GCC_LOCATIONS = [
    "uae", "united arab emirates", "dubai", "abu dhabi", "sharjah", "ajman",
    "saudi", "riyadh", "jeddah", "dammam", "khobar",
    "qatar", "doha",
    "kuwait",
    "bahrain", "manama",
    "oman", "muscat",
]


def _location_matches_criteria(job: dict, prefs: dict) -> bool:
    """Check if the job location matches the user's target countries."""
    loc = (job.get("location") or "").lower()
    if not loc or loc == "unknown":
        return True  # can't determine, give benefit of doubt

    target_countries = prefs.get("countries") or []
    if not target_countries:
        country = (prefs.get("country") or "").lower()
        if country == "gcc":
            target_countries = ["UAE", "Saudi Arabia", "Qatar", "Kuwait", "Bahrain", "Oman"]
        elif country:
            target_countries = [country]
        else:
            return True

    # Build location terms from preferences
    valid_terms = []
    for c in target_countries:
        cl = c.lower()
        valid_terms.append(cl)
        # Add common city names for each country
        if cl in ("uae", "united arab emirates"):
            valid_terms.extend(["dubai", "abu dhabi", "sharjah", "ajman", "ras al", "fujairah"])
        elif cl in ("saudi arabia", "ksa"):
            valid_terms.extend(["riyadh", "jeddah", "dammam", "khobar", "mecca", "medina"])
        elif cl == "qatar":
            valid_terms.extend(["doha"])
        elif cl == "kuwait":
            valid_terms.extend(["kuwait city"])
        elif cl == "bahrain":
            valid_terms.extend(["manama"])
        elif cl == "oman":
            valid_terms.extend(["muscat"])

    # "Remote" without a specific country — reject (could be anywhere)
    if "remote" in loc and not any(t in loc for t in valid_terms):
        return False

    # Check if location contains any valid term
    for term in valid_terms:
        if term in loc:
            return True

    return False


def _score(job: dict, cv: dict, prefs: dict = None) -> int:
    """Score job relevance: requires PRIMARY domain keyword + seniority + location match."""
    title = (job.get("title") or "").lower()

    if not title or title == "unknown role":
        return 25

    text = title + " " + (job.get("company") or "").lower()

    # ── Hard blacklist check ──
    for bl in _BLACKLIST:
        if bl in title:
            return 15

    # ── Location check ──
    if prefs and not _location_matches_criteria(job, prefs):
        return 20

    # Helper: match with word boundaries for short keywords to avoid false positives
    # e.g. "ai" should NOT match inside "Majid", "it" should NOT match inside "Deloitte"
    import re
    _boundary_cache = {}
    def _kw_in(kw, text):
        if len(kw.strip()) <= 3:
            # Use word boundary for short keywords
            pattern = _boundary_cache.get(kw)
            if not pattern:
                pattern = re.compile(r'\b' + re.escape(kw.strip()) + r'\b', re.IGNORECASE)
                _boundary_cache[kw] = pattern
            return bool(pattern.search(text))
        return kw in text

    # ── PRIMARY domain relevance (REQUIRED) ──
    primary_score = 0
    primary_count = 0
    for kw, weight in _PRIMARY_DOMAIN.items():
        if _kw_in(kw, text):
            primary_score += weight
            primary_count += 1

    # ── MODIFIER domain (bonus only) ──
    modifier_score = 0
    for kw, weight in _MODIFIER_DOMAIN.items():
        if _kw_in(kw, text):
            modifier_score += weight

    # ── Seniority match ──
    seniority_score = 0
    for kw, weight in _SENIORITY_KEYWORDS.items():
        if _kw_in(kw, text):
            seniority_score = max(seniority_score, weight)

    # ── CV skill overlap bonus (max ~10 points) ──
    skills = [s.lower() for s in cv.get("skills", [])]
    skill_overlap = sum(1 for s in skills if _kw_in(s, text))
    skill_score = min(10, skill_overlap * 2)

    # ── NO primary domain match ──
    # If seniority is high (Director+, CTO, VP etc.) give them a chance
    # BUT cap at 50 so they never auto-qualify as "strong match" without domain relevance
    if primary_count == 0:
        if seniority_score >= 14:  # Director, VP, Chief level
            raw = 30 + seniority_score // 2 + modifier_score + skill_score
            return max(20, min(50, raw))  # Cap at 50 — never reaches 60 threshold
        return max(15, min(35, 20 + modifier_score + seniority_score // 3))

    # AI/data keywords alone are not enough: IC/specialist roles without any
    # seniority signal should stay below the application threshold.
    if seniority_score == 0:
        raw = 35 + min(primary_score, 18) + min(modifier_score, 4) + skill_score
        return max(25, min(58, raw))

    # ── Combine: base 40 + primary + modifier bonus + seniority + skills ──
    raw = 40 + min(primary_score, 28) + min(modifier_score, 10) + seniority_score + skill_score

    return max(15, min(98, raw))


def _live_search_keywords(user_roles: List[str]) -> List[str]:
    """Convert preference role families into concise LinkedIn-indexed searches."""
    phrase_map = {
        "ai & data leadership": ["Head of AI", "Head of Data", "AI Director", "Chief Data Officer"],
        "data & ai leadership": ["Head of AI", "Head of Data", "AI Director", "Chief Data Officer"],
        "data & ai product": ["AI Product", "Product AI", "AI Platform"],
        "ai solutions architecture": ["AI Architect", "Solutions Architect AI"],
        "machine learning leadership": ["Machine Learning Director", "Head of Machine Learning"],
        "ai platform": ["AI Platform"],
        "data governance": ["Data Governance"],
        "digital transformation": ["Digital Transformation"],
        "ai automation": ["AI Automation"],
    }

    # High-yield LinkedIn terms. Keep this short: each term runs once per country.
    defaults = [
        "Head of AI",
        "Head of Data",
        "AI Director",
        "Chief Data Officer",
        "Data Governance",
        "Digital Transformation",
        "AI Product",
        "AI Platform",
        "AI Architect",
        "Machine Learning Director",
    ]

    keywords: List[str] = []
    seen = set()

    def add(term: str) -> None:
        term = (term or "").strip()
        if not term:
            return
        key = term.lower()
        if key not in seen:
            keywords.append(term)
            seen.add(key)

    for role in user_roles or []:
        role = (role or "").strip()
        if not role:
            continue
        mapped = phrase_map.get(role.lower())
        if mapped:
            for term in mapped:
                add(term)
        elif len(role) <= 35 and "&" not in role:
            add(role)

    for term in defaults:
        add(term)

    return keywords[:10]


# ── Job discovery (replace with real LinkedIn scrape later) ───────────
def _connected_sources() -> List[dict]:
    sources = state.get().get("job_sources", {})
    connected = [dict(src) for src in sources.values() if src.get("connected")]
    if not connected:
        connected = [dict(state.DEFAULT["job_sources"]["linkedin"])]
    return connected


def _discover_jobs(prefs: dict, cv: dict) -> List[dict]:
    s = state.get()
    applied_ids = set(s.get("applied_ids", []))
    existing = s["jobs"]["items"]
    sources = _connected_sources()

    n = random.randint(35, 65)
    jobs = []
    target_roles = prefs.get("roles") or ROLES_POOL[:4]
    for _ in range(n):
        role_seed = random.choice(target_roles).split(",")[0].strip() or random.choice(ROLES_POOL)
        title = random.choice([role_seed, f"Senior {role_seed}", f"{role_seed} Lead"])
        company = random.choice(COMPANIES)
        # stable 12-digit id from title+company so URL pattern checks pass
        jid = f"{abs(hash(title+company)) % 10**12:012d}"
        if jid in applied_ids or jid in existing:
            continue
        source = random.choice(sources)
        source_id = source.get("id", "linkedin")
        source_name = source.get("name", "LinkedIn")
        easy = random.random() < (0.72 if source_id in {"linkedin", "indeed"} else 0.38)
        posted = random.randint(0, max(1, prefs.get("recency_days") or 7))
        locations = prefs.get("locations") or prefs.get("countries") or [prefs.get("country") or "UAE"]
        loc = random.choice(locations) if isinstance(locations, list) and locations else (prefs.get("country") or "UAE")
        job = {
            "id": jid,
            "title": title,
            "company": company,
            "location": loc,
            "easy_apply": easy,
            "source": source_name,
            "source_id": source_id,
            "apply_type": "Easy Apply" if easy and source_id == "linkedin" else ("Indeed Apply" if easy and source_id == "indeed" else ("Quick Apply" if easy else "External Apply")),
            "url": SOURCE_URLS.get(source_id, SOURCE_URLS["linkedin"]).format(id=jid),
            # Demo jobs use hash-based fake IDs — URLs are NOT real.
            "url_verified": False,
            "submission_verified": False,
            "source_mode": "demo",
            "posted_days_ago": posted,
            "discovered_at": time.time(),
            "status": "discovered",
        }
        job["score"] = _score(job, cv, prefs)
        jobs.append(job)
    return jobs


# ── Live mode (real LinkedIn) ─────────────────────────────────────────
def _is_live_mode() -> bool:
    """Live mode runs the real LinkedIn scraper + applier.

    Off by default; flip on via state.live_mode = True (Settings UI) or env var.
    Also requires a saved LinkedIn session.
    """
    s = state.get()
    if not s.get("live_mode"):
        import os
        if os.environ.get("JOBS_LAND_LIVE_MODE", "").lower() not in {"1", "true", "yes"}:
            return False
    try:
        from backend.services import session_manager as sm
        return sm.has_valid_session()
    except Exception:
        return False


def _live_discover_jobs(prefs: dict, cv: dict) -> List[dict]:
    """Run a real LinkedIn jobs search using the saved session."""
    from backend.services import linkedin_scraper as ls

    countries = prefs.get("countries") or [prefs.get("country") or "UAE"]
    if prefs.get("country") == "GCC" and not prefs.get("countries"):
        countries = ["UAE", "Saudi Arabia", "Qatar", "Kuwait", "Bahrain", "Oman"]
    
    # Build concise LinkedIn-style keywords. Stored preferences can contain broad
    # semantic role families, but LinkedIn search performs better with concrete titles.
    user_roles = prefs.get("roles") or ["AI Product Manager"]
    keywords = _live_search_keywords(user_roles)
    
    days = max(1, int(prefs.get("recency_days") or 7))

    # Push detailed progress messages during search
    def _on_search_progress(event, kw, country, idx, total, found_so_far):
        label = f'"{kw}"' if kw else '"All Jobs"'
        if event == "searching":
            _push("info", f"🔍 [{idx}/{total}] Searching {label} in {country}…")
        elif event == "batch_done":
            _push("info", f"   ✓ Found results for {label} in {country} — {found_so_far} unique jobs so far.")
        elif event == "error":
            _push("warn", f"   ⚠️ Search for {label} in {country} had an issue — moving to next.")

    raw = ls.search_jobs_multi(
        keywords_list=keywords,
        countries=countries,
        recency_days=days,
        max_per_combo=25,
        hard_cap=300,
        headless=True,
        on_progress=_on_search_progress,
    )

    s = state.get()
    applied_ids = set(s.get("applied_ids", []))
    existing = s["jobs"]["items"]

    out: List[dict] = []
    _last_push_count = [0]  # track for incremental UI updates

    def _score_and_stage(j):
        """Score one job and add to output."""
        if j["id"] in existing:
            return
        j["discovered_at"] = time.time()
        j["apply_type"] = "Easy Apply" if j.get("easy_apply") else "External Apply"
        j["score"] = _score(j, cv, prefs)
        
        # Mark already-applied jobs (LinkedIn shows "Applied" badge)
        if j.get("already_applied") or j["id"] in applied_ids:
            j["status"] = "already_applied"
            j["applied_at"] = j["discovered_at"]
            j["submission_verified"] = True
            if j["id"] not in applied_ids:
                applied_ids.add(j["id"])
        else:
            j["status"] = "discovered"
        out.append(j)

    def _push_incremental():
        """Push matched jobs to state so dashboard updates live."""
        new_count = len(out)
        if new_count == _last_push_count[0]:
            return  # no new jobs since last push
        _last_push_count[0] = new_count
        matched_so_far = [j for j in out if j.get("score", 0) >= 60 or j.get("status") == "already_applied"]
        easy_so_far = [j for j in matched_so_far if j.get("easy_apply") and j.get("status") != "already_applied"]
        # Update live counters in automation state so dashboard polls see them
        def _live_update(st):
            st["automation"]["live_matched"] = len(matched_so_far)
            st["automation"]["live_easy_apply"] = len(easy_so_far)
            st["automation"]["live_found"] = new_count
        state.update(_live_update)

    for j in raw:
        _score_and_stage(j)

    _push_incremental()
    return out


def _live_apply_easy(job: dict, driver=None) -> dict:
    """Drive a Selenium browser to actually submit one Easy Apply form.

    A caller can pass a driver to reuse the same silent browser across multiple
    applications in one run.

    The applier now uses a 3-tier resolution chain for every form question:
      1. Profile heuristics (phone, email, name, years, city…)
      2. Saved answers bank (fuzzy-matched)
      3. Groq LLM — answers from the uploaded CV/profile; uncertain = pending
    Any new LLM-generated answers are written back to the answers bank so future
    runs benefit from them automatically.
    """
    from backend.services import linkedin_scraper as ls
    from backend.services import linkedin_applier as la
    from backend.config import AI_API_KEY, AI_BASE_URL, AI_MODEL

    own_driver = driver is None
    if own_driver:
        driver = ls._make_driver(headless=True)
    try:
        s = state.get()
        profile = s.get("profile") or {}

        # Enrich cv dict with contact fields. CV contact wins over sign-in profile
        # so replacing the CV also replaces the candidate identity.
        cv = {**s["cv"]}
        contact = cv.get("contact") or {}
        if not cv.get("phone"):
            cv["phone"] = contact.get("phone") or profile.get("phone") or ""
        if not cv.get("email"):
            cv["email"] = contact.get("email") or profile.get("email") or ""
        if not cv.get("linkedin"):
            cv["linkedin"] = contact.get("linkedin") or ""
        if not cv.get("name"):
            cv["name"]  = profile.get("name") or ""

        result = la.apply_easy(
            driver,
            job["url"],
            cv,
            s["answers"],
            profile=profile,
            api_key=AI_API_KEY,
            api_base=AI_BASE_URL,
            api_model=AI_MODEL,
        )

        # Persist any new Groq-generated answers so future forms reuse them
        new_answers = result.get("new_answers") or []
        if new_answers:
            def _add_answers(st):
                bank = st.get("answers") or []
                existing_q = {(a.get("question") or "").strip().lower() for a in bank}
                next_id = max((a.get("id") or 0) for a in bank) + 1 if bank else 100
                for na in new_answers:
                    q = (na.get("question") or "").strip()
                    if not q or q.lower() in existing_q:
                        continue
                    bank.append({
                        "id": next_id,
                        "question": q,
                        "answer": na.get("answer") or "",
                        "created_at": time.time(),
                        "source": "groq",
                    })
                    existing_q.add(q.lower())
                    next_id += 1
                st["answers"] = bank
            state.update(_add_answers)
            _push("info", f"   💡 Groq auto-answered {len(new_answers)} new question(s) — saved to answers bank.")

        return result
    finally:
        if own_driver:
            ls._cleanup_driver(driver)


def _is_infrastructure_apply_error(error: str) -> bool:
    """True only for browser/session/system failures, not recoverable form issues."""
    e = (error or "").lower()
    if not e:
        return False
    recoverable_form_errors = [
        "too many steps without submit",
        "no next/submit button",
        "no next",
        "submit clicked but no confirmation",
        "form field we couldn't fill",
        "field did not accept",
        "please enter a valid answer",
        "modal disappeared mid-form",
        "form won't advance",
    ]
    if any(term in e for term in recoverable_form_errors):
        return False
    infrastructure_errors = [
        "linkedin session expired",
        "redirected to login",
        "checkpoint",
        "captcha",
        "challenge",
        "navigation failed",
        "apply form did not open",
        "browser",
        "webdriver",
        "chrome",
        "no such window",
        "disconnected",
        "connection refused",
        "timeout",
        "timed out",
    ]
    return any(term in e for term in infrastructure_errors)


# ── Engine ────────────────────────────────────────────────────────────
def _push(level: str, msg: str):
    state.push_log(level, msg)


def _summarize_logs(logs: list[dict]) -> dict:
    summary = {"discovered": 0, "verified_applied": 0, "external": 0, "pending": 0, "skipped": 0, "warnings": 0}
    for log in logs:
        level = log.get("level")
        msg = log.get("msg", "")
        if "Discovered " in msg:
            try:
                summary["discovered"] += int(msg.split("Discovered ", 1)[1].split(" ", 1)[0])
            except Exception:
                pass
        if level == "success" and "Applied to" in msg:
            summary["verified_applied"] += 1
        elif level == "external":
            summary["external"] += 1
        elif level == "pending":
            summary["pending"] += 1
        elif level == "skip":
            summary["skipped"] += 1
        elif level in {"warn", "warning"}:
            summary["warnings"] += 1
    return summary


def _archive_current_run(status: str = "completed") -> dict | None:
    s = state.get()
    auto = s["automation"]
    logs = list(auto.get("logs", []))
    started_at = auto.get("started_at")
    if not logs or not started_at:
        return None
    if auto.get("archived_started_at") == started_at:
        runs = auto.get("runs", [])
        return runs[0] if runs else None

    run = {
        "id": f"run-{int(started_at)}",
        "started_at": started_at,
        "ended_at": time.time(),
        "status": status,
        "summary": _summarize_logs(logs),
        "logs": logs[-200:],
    }

    def m(st):
        runs = st["automation"].setdefault("runs", [])
        runs.insert(0, run)
        del runs[20:]
        st["automation"]["archived_started_at"] = started_at

    state.update(m)
    return run


def _engine_loop():
    s = state.get()
    cv = s["cv"]
    prefs = s["preferences"]
    profile = s["profile"]
    name = cv.get("name") or profile.get("name") or "the uploaded CV candidate"
    live = _is_live_mode()

    if not live:
        _push("warn", "Automation cannot run because real LinkedIn mode is not active. Connect LinkedIn in Settings and enable live mode.")
        _archive_current_run("failed")
        def finish_no_live(st):
            st["automation"]["running"] = False
            st["automation"]["last_tick"] = time.time()
        state.update(finish_no_live)
        return

    _push("info", f"🟢 LIVE MODE — submitting real applications on linkedin.com as {name}.")
    time.sleep(0.6)
    _push("success", f"📄 CV loaded: {len(cv.get('skills',[]))} skills · {cv.get('years',0)} years experience.")
    time.sleep(0.4)
    target = prefs.get("country")
    if prefs.get("countries") and target in {"GCC", "Europe", "GCC + Europe", "Europe + GCC"}:
        shown = ", ".join(prefs.get("countries", [])[:8])
        suffix = "…" if len(prefs.get("countries", [])) > 8 else ""
        target = f"{target} ({shown}{suffix})"
    _push("info", f"🎯 Targeting {target} · roles: {', '.join(prefs.get('roles',[])[:3])} · last {prefs.get('recency_days')} days.")
    time.sleep(0.4)

    # ── Discovery ─────────────────────────────────────────────────────
    discovered: List[dict] = []
    if live:
        try:
            _push("info", "🔍 Running real LinkedIn jobs search…")
            discovered = _live_discover_jobs(prefs, cv)
            _push("success", f"✅ Pulled {len(discovered)} real jobs from LinkedIn.")
        except PermissionError as exc:
            _push("warn", f"⚠️ {exc}. Real run stopped; no fake/demo jobs were generated.")
            _archive_current_run("failed")
            def finish_perm(st):
                st["automation"]["running"] = False
                st["automation"]["last_tick"] = time.time()
            state.update(finish_perm)
            return
        except Exception as exc:
            _push("warn", f"⚠️ Live discovery failed ({exc}). Real run stopped; no fake/demo jobs were generated.")
            logger_msg = f"live discovery exception: {exc!r}"
            try:
                import logging as _lg
                _lg.getLogger(__name__).exception("Live discovery failed")
            except Exception:
                pass
            _archive_current_run("failed")
            def finish_exc(st):
                st["automation"]["running"] = False
                st["automation"]["last_tick"] = time.time()
            state.update(finish_exc)
            return

    # Separate already-applied from new discoveries
    already_applied_jobs = [j for j in discovered if j.get("status") == "already_applied"]
    new_jobs = [j for j in discovered if j.get("status") != "already_applied"]

    # ALL jobs are committed — low-scorers get status "skipped" so the user
    # can see what was found and why it wasn't pursued.
    for j in new_jobs:
        if j.get("score", 0) < 60 and j.get("status") not in ("already_applied", "external"):
            j["status"] = "skipped"

    # Tag each job with the current run_id so we can distinguish new vs old
    run_id = state.get()["automation"].get("started_at") or time.time()

    def commit_jobs(st):
        st["automation"]["current_run_id"] = run_id
        for j in discovered:          # store every job, not just matched ones
            j["run_id"] = run_id
            st["jobs"]["items"][j["id"]] = j
        # Add already-applied IDs to applied_ids
        for j in already_applied_jobs:
            if j["id"] not in st["applied_ids"]:
                st["applied_ids"].append(j["id"])
    state.update(commit_jobs)

    matched_jobs = [j for j in discovered if j.get("score", 0) >= 60 or j.get("status") == "already_applied"]
    
    parts = [f"🔎 Discovered {len(discovered)} jobs"]
    if already_applied_jobs:
        parts.append(f"({len(already_applied_jobs)} already applied)")
    if new_jobs:
        matched = [j for j in new_jobs if j.get("score", 0) >= 60]
        parts.append(f"— {len(matched)} matched your profile")
    _push("info", " ".join(parts) + ".")
    time.sleep(0.4)

    # rank by score + recency
    discovered.sort(key=lambda j: (j.get("score", 0), -(j.get("posted_days_ago") or 99)), reverse=True)

    skip_count = 0
    apply_driver = None
    for job in discovered:
        if not state.get()["automation"]["running"]:
            _push("warn", "⛔ Automation stopped by user.")
            if apply_driver:
                from backend.services import linkedin_scraper as ls
                ls._cleanup_driver(apply_driver)
            _archive_current_run("stopped")
            def finish_stop(st):
                st["automation"]["running"] = False
                st["automation"]["last_tick"] = time.time()
            state.update(finish_stop)
            return

        # Skip already-applied jobs (detected from LinkedIn "Applied" badge)
        if job.get("status") == "already_applied":
            _push("info", f"✅ '{job['title']}' at {job['company']} — already applied ({job['score']}% match).")
            time.sleep(0.15)
            continue

        if job["id"] in state.get().get("applied_ids", []):
            continue

        if job["score"] < 60:
            skip_count += 1
            # Already committed as "skipped" — just move on
            continue

        if not job["easy_apply"]:
            def m(st, jid=job["id"]):
                st["jobs"]["items"][jid]["status"] = "external"
            state.update(m)
            _push("external", f"🌐 External: '{job['title']}' at {job['company']} ({job['score']}% match) — saved to External Jobs.")
            time.sleep(0.2)
            continue

        # Track stats (no caps)
        _increment_counters()

        # Tiered match label
        score = job['score']
        if score >= 80:
            match_label = "🎯 Excellent match"
        elif score >= 70:
            match_label = "✨ Strong match"
        else:
            match_label = "👍 Good match"
        _push("match", f"{match_label} ({score}%): '{job['title']}' at {job['company']} — applying now.")

        # ── Real submission ────────────────────────────────────
        try:
            if apply_driver is None:
                from backend.services import linkedin_scraper as ls
                apply_driver = ls._make_driver(headless=True)
            result = _live_apply_easy(job, apply_driver)
        except Exception as exc:
            result = {"status": "error", "error": str(exc), "pending_question": None}

        status = result.get("status")
        if status == "submitted":
            def m(st, jid=job["id"], note=result.get("note")):
                j = st["jobs"]["items"][jid]
                j["status"] = "applied"
                j["applied_at"] = time.time()
                j["submission_verified"] = True
                if note: j["note"] = note
                if jid not in st["applied_ids"]:
                    st["applied_ids"].append(jid)
            state.update(m)
            _push("success", f"🎉 Submitted application to '{job['title']}' at {job['company']}.")
        elif status == "pending":
            question = result.get("pending_question") or "Question we couldn't answer"
            def m(st, jid=job["id"], q=question):
                j = st["jobs"]["items"][jid]
                j["status"] = "pending"
                j["pending_question"] = q
                j["pending_kind"] = "answer"
            state.update(m)
            def rollback(st):
                st["automation"]["today_count"] = max(0, st["automation"]["today_count"]-1)
                st["automation"]["hour_count"] = max(0, st["automation"]["hour_count"]-1)
            state.update(rollback)
            _push("pending", f"⏸️ '{job['title']}' at {job['company']} — needs your answer: \"{question}\".")
        elif status == "not_easy_apply":
            def m(st, jid=job["id"]):
                j = st["jobs"]["items"][jid]
                j["easy_apply"] = False
                j["status"] = "external"
            state.update(m)
            def rollback(st):
                st["automation"]["today_count"] = max(0, st["automation"]["today_count"]-1)
                st["automation"]["hour_count"] = max(0, st["automation"]["hour_count"]-1)
            state.update(rollback)
            _push("external", f"🌐 '{job['title']}' at {job['company']} is not Easy Apply after all — moved to External.")
        else:
            err = result.get("error") or "unknown error"
            def rollback(st):
                st["automation"]["today_count"] = max(0, st["automation"]["today_count"]-1)
                st["automation"]["hour_count"] = max(0, st["automation"]["hour_count"]-1)
            state.update(rollback)
            if _is_infrastructure_apply_error(err):
                def m(st, jid=job["id"], e=err):
                    j = st["jobs"]["items"][jid]
                    j["status"] = "failed"
                    j["error"] = e
                state.update(m)
                _push("warn", f"⚠️ Apply failed for '{job['title']}' at {job['company']}: {err}")
            else:
                question = result.get("pending_question") or err or "Easy Apply form needs review"
                def m(st, jid=job["id"], q=question):
                    j = st["jobs"]["items"][jid]
                    j["status"] = "pending"
                    j["pending_question"] = q
                    j["pending_kind"] = "answer"
                    j["error"] = None
                state.update(m)
                _push("pending", f"⏸️ '{job['title']}' at {job['company']} — needs review: \"{question}\".")
        time.sleep(random.uniform(2.5, 5.0))   # be polite to LinkedIn

    if apply_driver:
        from backend.services import linkedin_scraper as ls
        ls._cleanup_driver(apply_driver)
    if skip_count > 5:
        _push("info", f"📊 {skip_count} jobs didn't match your profile and were filtered out.")
    _push("info", "🏁 Cycle complete — I'll check LinkedIn again in 1 hour.")
    _archive_current_run("completed")

    def finish(st):
        st["automation"]["running"] = False
        st["automation"]["last_tick"] = time.time()
    state.update(finish)


def _start_thread():
    t = threading.Thread(target=_engine_loop, daemon=True)
    t.start()


# ── Hourly scheduler ──────────────────────────────────────────────────
_scheduler_started = False


def _hourly_tick():
    global _scheduler_started
    while True:
        def set_next(st):
            st["automation"]["next_run_at"] = time.time() + 3600
        state.update(set_next)
        time.sleep(3600)
        s = state.get()
        prefs = s["preferences"]
        cv = s["cv"]
        if (prefs.get("ready") and cv.get("filename")
                and not s["automation"]["running"]
                and _is_live_mode()):
            def m(st):
                st["automation"]["running"] = True
                st["automation"]["started_at"] = time.time()
                st["automation"]["next_run_at"] = time.time() + 3600
            state.update(m)
            _start_thread()


def _ensure_scheduler():
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    t = threading.Thread(target=_hourly_tick, daemon=True)
    t.start()


# ── Endpoints ─────────────────────────────────────────────────────────
@router.get("/status")
def status():
    s = state.get()
    auto = s["automation"]
    return {
        "running": auto["running"],
        "today_count": auto.get("today_count", 0),
        "hour_count": auto.get("hour_count", 0),
        "last_tick": auto.get("last_tick"),
        "next_run_at": auto.get("next_run_at"),
    }


@router.post("/start")
def start():
    s = state.get()
    if not s["cv"].get("filename"):
        raise HTTPException(400, "Please upload your CV first.")
    if not s["preferences"].get("ready"):
        raise HTTPException(400, "Please talk to Jobby first to set your search preferences.")
    if not sm.has_valid_session():
        raise HTTPException(400, "Please connect your LinkedIn account in Settings before running automation.")
    if s["automation"]["running"]:
        return {"success": False, "message": "Already running"}

    def m(st):
        st["automation"]["running"] = True
        st["automation"]["started_at"] = time.time()
        st["automation"]["logs"] = []
        st["automation"]["archived_started_at"] = None
    state.update(m)
    _ensure_scheduler()
    _start_thread()
    return {"success": True}


@router.post("/stop")
def stop():
    _archive_current_run("stopped")
    def m(st):
        st["automation"]["running"] = False
    state.update(m)
    return {"success": True}


@router.post("/archive-current")
def archive_current():
    run = _archive_current_run("completed")
    return {"success": True, "run": run}


@router.post("/clear-jobs")
def clear_jobs():
    """Wipe discovered jobs and applied-id memory so the next run starts clean.
    Useful when older runs have left stuck pending/unverified candidates around."""
    def m(st):
        st["jobs"]["items"] = {}
        st["applied_ids"] = []
        st["automation"]["today_count"] = 0
        st["automation"]["hour_count"] = 0
        st["automation"]["hour_window_start"] = None
    state.update(m)
    return {"success": True}


@router.get("/runs")
def runs():
    s = state.get()
    return {"runs": s["automation"].get("runs", [])}


@router.get("/logs/poll")
def logs_poll(since: float = 0):
    s = state.get()
    logs = [e for e in s["automation"]["logs"] if e["ts"] > since]
    return {"logs": logs, "running": s["automation"]["running"]}


@router.get("/logs")
async def logs_sse():
    async def generate():
        sent = 0
        while True:
            s = state.get()
            snapshot = list(s["automation"]["logs"])
            new = snapshot[sent:]
            for entry in new:
                yield f"data: {json.dumps(entry)}\n\n"
            sent = len(snapshot)
            if not s["automation"]["running"] and sent == len(snapshot) and sent > 0:
                yield "data: {\"done\": true}\n\n"
                break
            await asyncio.sleep(0.5)
    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
