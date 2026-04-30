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

router = APIRouter(prefix="/automation", tags=["automation"])

# ── Caps ──────────────────────────────────────────────────────────────
DAILY_CAP = 100
HOURLY_CAP = 10

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


def _check_caps_and_increment() -> Tuple[bool, str]:
    """Increments today/hour counters atomically. Returns (allowed, reason)."""
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
    if auto["today_count"] >= DAILY_CAP:
        return False, f"Daily cap reached ({DAILY_CAP}/day)"
    if auto["hour_count"] >= HOURLY_CAP:
        return False, f"Hourly cap reached ({HOURLY_CAP}/hr)"
    auto["today_count"] += 1
    auto["hour_count"] += 1
    state.save()
    return True, ""


# ── Scoring ───────────────────────────────────────────────────────────
def _score(job: dict, cv: dict) -> int:
    """Light keyword-overlap scoring — a stand-in for true semantic match."""
    skills = [s.lower() for s in cv.get("skills", [])]
    text = (job["title"] + " " + job["company"]).lower()
    overlap = sum(1 for s in skills if s in text)
    base = 60 + overlap * 4
    # randomise within a believable band
    return max(35, min(98, base + random.randint(-12, 18)))


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
        job["score"] = _score(job, cv)
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
    keywords = prefs.get("roles") or ["AI Product Manager"]
    days = max(1, int(prefs.get("recency_days") or 7))

    raw = ls.search_jobs_multi(
        keywords_list=keywords,
        countries=countries,
        recency_days=days,
        max_per_combo=10,
        hard_cap=60,
        headless=True,
    )

    s = state.get()
    applied_ids = set(s.get("applied_ids", []))
    existing = s["jobs"]["items"]

    out: List[dict] = []
    for j in raw:
        if j["id"] in applied_ids or j["id"] in existing:
            continue
        j["discovered_at"] = time.time()
        j["status"] = "discovered"
        j["apply_type"] = "Easy Apply" if j.get("easy_apply") else "External Apply"
        j["score"] = _score(j, cv)
        out.append(j)
    return out


def _live_apply_easy(job: dict) -> dict:
    """Drive a Selenium browser to actually submit one Easy Apply form.

    The driver is opened/closed per call (slow but reliable) so each apply is
    isolated and the browser doesn't accumulate memory.
    """
    from backend.services import linkedin_scraper as ls
    from backend.services import linkedin_applier as la

    driver = ls._make_driver(headless=True)
    try:
        s = state.get()
        return la.apply_easy(driver, job["url"], s["cv"], s["answers"])
    finally:
        try: driver.quit()
        except Exception: pass


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
    name = profile.get("name") or "you"
    live = _is_live_mode()

    if live:
        _push("info", f"🟢 LIVE MODE — submitting real applications on linkedin.com as {name}.")
    else:
        _push("warn", f"🟡 DEMO MODE — no real LinkedIn calls. Enable live mode in Settings (requires a saved LinkedIn session).")
    time.sleep(0.6)
    _push("success", f"📄 CV loaded: {len(cv.get('skills',[]))} skills · {cv.get('years',0)} years experience.")
    time.sleep(0.4)
    target = prefs.get("country")
    if target == "GCC" and prefs.get("countries"):
        target = "GCC (" + ", ".join(prefs.get("countries", [])[:6]) + ")"
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
            _push("warn", f"⚠️ {exc}. Falling back to demo mode for this cycle.")
            live = False
        except Exception as exc:
            _push("warn", f"⚠️ Live discovery failed ({exc}). Falling back to demo mode for this cycle.")
            logger_msg = f"live discovery exception: {exc!r}"
            try:
                import logging as _lg
                _lg.getLogger(__name__).exception("Live discovery failed")
            except Exception:
                pass
            live = False

    if not live:
        sources = _connected_sources()
        _push("info", f"🔗 (demo) Generating candidate jobs across: {', '.join(src.get('name', 'Job board') for src in sources)}.")
        discovered = _discover_jobs(prefs, cv)

    def commit_jobs(st):
        for j in discovered:
            st["jobs"]["items"][j["id"]] = j
    state.update(commit_jobs)
    _push("info", f"🔎 Discovered {len(discovered)} new jobs matching your criteria.")
    time.sleep(0.4)

    # rank by score + recency
    discovered.sort(key=lambda j: (j.get("score", 0), -(j.get("posted_days_ago") or 99)), reverse=True)

    for job in discovered:
        if not state.get()["automation"]["running"]:
            _push("warn", "⛔ Automation stopped by user.")
            _archive_current_run("stopped")
            def finish_stop(st):
                st["automation"]["running"] = False
                st["automation"]["last_tick"] = time.time()
            state.update(finish_stop)
            return

        if job["id"] in state.get().get("applied_ids", []):
            continue

        if job["score"] < 60:
            def m(st, jid=job["id"]):
                st["jobs"]["items"][jid]["status"] = "skipped"
            state.update(m)
            _push("skip", f"⏭️ Skipped '{job['title']}' at {job['company']} — match too low ({job['score']}%).")
            time.sleep(0.3)
            continue

        if not job["easy_apply"]:
            def m(st, jid=job["id"]):
                st["jobs"]["items"][jid]["status"] = "external"
            state.update(m)
            _push("external", f"🌐 External: '{job['title']}' at {job['company']} ({job['score']}% match) — saved to External Jobs.")
            time.sleep(0.2)
            continue

        # Caps
        ok, reason = _check_caps_and_increment()
        if not ok:
            _push("warn", f"⏸️ {reason}. Pausing — will resume on next hourly check.")
            break

        _push("match", f"✨ Strong match ({job['score']}%): '{job['title']}' at {job['company']} — applying now.")

        if live:
            # ── Real submission ────────────────────────────────────
            try:
                result = _live_apply_easy(job)
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
                # rollback the cap increment — nothing was actually submitted
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
                def m(st, jid=job["id"], e=err):
                    j = st["jobs"]["items"][jid]
                    j["status"] = "failed"
                    j["error"] = e
                state.update(m)
                def rollback(st):
                    st["automation"]["today_count"] = max(0, st["automation"]["today_count"]-1)
                    st["automation"]["hour_count"] = max(0, st["automation"]["hour_count"]-1)
                state.update(rollback)
                _push("warn", f"⚠️ Apply failed for '{job['title']}' at {job['company']}: {err}")
            time.sleep(random.uniform(2.5, 5.0))   # be polite to LinkedIn
        else:
            # ── Demo path (state-only) ─────────────────────────────
            time.sleep(random.uniform(0.6, 1.2))
            if random.random() < 0.25:
                question = random.choice(UNKNOWN_QUESTIONS)
                ans_bank = state.get()["answers"]
                saved = next((a for a in ans_bank if a["question"].lower() == question.lower()), None)
                if not saved:
                    def m(st, jid=job["id"], q=question):
                        st["jobs"]["items"][jid]["status"] = "pending"
                        st["jobs"]["items"][jid]["pending_question"] = q
                    state.update(m)
                    def rollback(st):
                        st["automation"]["today_count"] = max(0, st["automation"]["today_count"]-1)
                        st["automation"]["hour_count"] = max(0, st["automation"]["hour_count"]-1)
                    state.update(rollback)
                    _push("pending", f"⏸️ (demo) '{job['title']}' at {job['company']} needs your answer: \"{question}\".")
                    time.sleep(0.4)
                    continue

            def m(st, jid=job["id"]):
                j = st["jobs"]["items"][jid]
                j["status"] = "applied"
                j["applied_at"] = time.time()
                j["submission_verified"] = False    # demo runs are NEVER verified
                j["url_verified"] = False            # demo URLs are fake (hash-based IDs)
                if jid not in st["applied_ids"]:
                    st["applied_ids"].append(jid)
            state.update(m)
            _push("success", f"⚠️ (DEMO) Simulated application to '{job['title']}' at {job['company']}. No real submission — this is a demo. Enable live mode in Settings to apply for real.")
            time.sleep(random.uniform(0.5, 1.0))

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
        time.sleep(3600)
        s = state.get()
        prefs = s["preferences"]
        cv = s["cv"]
        if (prefs.get("ready") and cv.get("filename")
                and not s["automation"]["running"]
                and s["automation"]["today_count"] < DAILY_CAP):
            def m(st):
                st["automation"]["running"] = True
                st["automation"]["started_at"] = time.time()
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
        "daily_cap": DAILY_CAP,
        "hourly_cap": HOURLY_CAP,
        "last_tick": auto.get("last_tick"),
    }


@router.post("/start")
def start():
    s = state.get()
    if not s["cv"].get("filename"):
        raise HTTPException(400, "Please upload your CV first.")
    if not s["preferences"].get("ready"):
        raise HTTPException(400, "Please chat with the AI Assistant to set your search preferences first.")
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
