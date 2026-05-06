"""
Lightweight JSON-backed state store for JobsLand.

Keeps the app coherent end-to-end without dragging in a full ORM:
- profile (imported from LinkedIn)
- cv (uploaded file metadata + extracted skills/years)
- preferences (country, role keywords, recency)
- jobs (discovered, applied, external, pending)
- answers (Q&A bank)
- automation runtime (running, today/hour counters, last_run)
"""
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict
from backend.config import DATA_DIR

_LOCK = threading.RLock()
_PATH = Path(DATA_DIR) / "state.json"

DEFAULT: Dict[str, Any] = {
    # Real automation mode. When true AND a LinkedIn session is saved, the engine
    # drives a real Selenium browser to search and submit. When false, automation
    # does not run; no simulated jobs or applications are generated.
    "live_mode": True,
    "profile": {
        "name": None,
        "title": None,
        "email": None,
        "photo": None,
        "imported_at": None,
    },
    "users": {},             # email -> local password account metadata
    "cv": {
        "filename": None,
        "uploaded_at": None,
        "skills": [],
        "years": 0,
        "summary": None,
    },
    "preferences": {
        "ready": False,
        "country": None,
        "city": None,
        "countries": [],
        "locations": [],
        "search_keywords": [],
        "roles": [],
        "recency_days": 7,
        "industries": [],
    },
    "job_sources": {
        "linkedin": {
            "id": "linkedin",
            "name": "LinkedIn",
            "connected": False,
            "connected_at": None,
            "capabilities": ["Profile sync", "Easy Apply", "Executive roles"],
            "region": "Global",
            "notes": "Required for LinkedIn profile sync and LinkedIn Easy Apply automation.",
        },
        "indeed": {
            "id": "indeed",
            "name": "Indeed",
            "connected": False,
            "connected_at": None,
            "capabilities": ["Indeed Apply", "Broad role discovery"],
            "region": "Global",
            "notes": "Adds broader market coverage and quick-apply opportunities where available.",
        },
        "naukrigulf": {
            "id": "naukrigulf",
            "name": "Naukrigulf",
            "connected": False,
            "connected_at": None,
            "capabilities": ["Gulf roles", "External apply"],
            "region": "GCC",
            "notes": "Strong source for UAE, Saudi Arabia, Qatar, Oman, Kuwait, and Bahrain roles.",
        },
        "gulftalent": {
            "id": "gulftalent",
            "name": "GulfTalent",
            "connected": False,
            "connected_at": None,
            "capabilities": ["Gulf roles", "Senior hiring"],
            "region": "GCC",
            "notes": "Useful for management, data, digital, and transformation roles in the Gulf.",
        },
        "bayt": {
            "id": "bayt",
            "name": "Bayt",
            "connected": False,
            "connected_at": None,
            "capabilities": ["Gulf roles", "External apply"],
            "region": "MENA",
            "notes": "Adds MENA coverage and another source of role discovery.",
        },
        "glassdoor": {
            "id": "glassdoor",
            "name": "Glassdoor",
            "connected": False,
            "connected_at": None,
            "capabilities": ["Company research", "External apply"],
            "region": "Global",
            "notes": "Useful for validating companies and finding external application links.",
        },
    },
    "jobs": {
        # job_id -> { id, title, company, location, score, easy_apply, url, posted_days_ago, status }
        # status: discovered | applied | skipped | pending | external | failed
        "items": {},
    },
    "applied_ids": [],     # de-dup memory for already-applied jobs
    "answers": [],         # [{ id, question, answer, created_at }]
    "automation": {
        "running": False,
        "started_at": None,
        "last_tick": None,
        "today_date": None,
        "today_count": 0,
        "hour_window_start": None,
        "hour_count": 0,
        "logs": [],         # ring buffer (last 200)
        "runs": [],         # completed run summaries with logs
        "archived_started_at": None,
    },
    "chat": {
        # scripted preference-intake state
        "step": "greet",
        "history": [],
    },
}


def _load() -> dict:
    if not _PATH.exists():
        return json.loads(json.dumps(DEFAULT))
    try:
        with open(_PATH, "r") as f:
            data = json.load(f)
        # shallow-merge so newly-added keys appear with defaults
        merged = json.loads(json.dumps(DEFAULT))
        for k, v in data.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k].update(v)
            else:
                merged[k] = v
        return merged
    except Exception:
        return json.loads(json.dumps(DEFAULT))


def _save(state: dict) -> None:
    tmp = _PATH.with_name(f"{_PATH.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, default=str)
    tmp.replace(_PATH)


_state: dict = _load()
# Process-start invariant: nothing is running on a fresh process.
_state.setdefault("automation", {})["running"] = False
_save(_state)


def get() -> dict:
    with _LOCK:
        return _state


def save() -> None:
    with _LOCK:
        _save(_state)


def update(mutator):
    """mutator(state) -> None ; saves automatically."""
    with _LOCK:
        mutator(_state)
        _save(_state)


def reset() -> None:
    global _state
    with _LOCK:
        _state = json.loads(json.dumps(DEFAULT))
        _save(_state)


def push_log(level: str, msg: str) -> None:
    with _LOCK:
        logs = _state["automation"]["logs"]
        logs.append({"ts": time.time(), "level": level, "msg": msg})
        _state["automation"]["last_tick"] = time.time()
        if len(logs) > 200:
            del logs[: len(logs) - 200]
        _save(_state)
