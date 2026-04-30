"""Auto-sync `agent/data.json` from the FastAPI app's `data/state.json`.

Single source of truth = `state.json` (CV upload + chat preferences + answer
bank live there). Whenever the agent boots — and on demand — we refresh
`data.json` so the Playwright agent and the React UI never drift.

This is a lossless merge: keys the user manually added to `data.json` (e.g.
salary expectation, visa) are preserved if `state.json` doesn't have them.
"""
from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any, Dict

from agent import config
from agent.logger import get_logger

log = get_logger("sync")


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Could not parse %s: %s", path, exc)
        return {}


def _example() -> Dict[str, Any]:
    return _load(config.DATA_EXAMPLE)


def _deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        elif v in (None, "", [], {}):
            # don't let an empty value overwrite a populated one
            out.setdefault(k, v)
        else:
            out[k] = v
    return out


def _split_name(full: str | None) -> tuple[str, str]:
    if not full:
        return "", ""
    parts = full.strip().split(" ", 1)
    return (parts[0], parts[1] if len(parts) > 1 else "")


def build_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Project the FastAPI state onto the data.json schema."""
    profile = state.get("profile") or {}
    cv = state.get("cv") or {}
    prefs = state.get("preferences") or {}

    first, last = _split_name(profile.get("name"))

    titles = prefs.get("roles") or []
    locations = (
        prefs.get("locations")
        or prefs.get("countries")
        or ([prefs.get("country")] if prefs.get("country") else [])
    )
    locations = [l for l in locations if l]

    return {
        "identity": {
            "first_name": first or "",
            "last_name":  last  or "",
            "email":      profile.get("email") or "",
            "phone":      profile.get("phone") or "",
            "country_code": "",
            "city":        prefs.get("city") or "",
            "country":     prefs.get("country") or (locations[0] if locations else ""),
        },
        "profile": {
            "headline":         profile.get("title") or cv.get("headline") or "",
            "summary":          cv.get("summary") or "",
            "years_experience": int(cv.get("years") or 0),
            "current_title":    profile.get("title") or "",
            "current_company":  profile.get("company") or "",
            "skills":           list(cv.get("skills") or []),
            "education":        list(cv.get("education") or []),
        },
        "targets": {
            "titles":            titles,
            "locations":         locations,
            "recency_days":      int(prefs.get("recency_days") or 7),
            "exclude_companies": list(prefs.get("exclude_companies") or []),
        },
        "preferences": {
            "min_match_score":   config.MIN_SCORE,
            "max_per_hour":      config.MAX_PER_HOUR,
            "max_per_day":       config.MAX_PER_DAY,
            "delay_seconds":     list(config.DELAY_BETWEEN),
        },
        "answers_seed": list(state.get("answers") or []),  # used to warm the QA bank
        "ai": {
            "provider": "groq",
            "api_key_env": "AI_API_KEY",
            "model":    config.GROQ_MODEL,
            "base_url": config.GROQ_BASE_URL,
        },
        "_synced_at": time.time(),
        "_source":    str(config.STATE_JSON),
    }


def sync() -> Dict[str, Any]:
    """Rebuild data.json from state.json. Returns the merged data."""
    state = _load(config.STATE_JSON)
    derived = build_from_state(state) if state else {}
    existing = _load(config.DATA_JSON)
    template = _example()

    # Merge order: template (defaults) ← derived (from state) ← existing (user edits)
    merged = _deep_merge(template, derived)
    merged = _deep_merge(merged, existing)

    config.DATA_JSON.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    log.info("data.json synced from state.json (titles=%d, locations=%d)",
             len(merged.get("targets", {}).get("titles", [])),
             len(merged.get("targets", {}).get("locations", [])))
    return merged


def load() -> Dict[str, Any]:
    """Read data.json, syncing from state.json if missing or stale."""
    if not config.DATA_JSON.exists():
        return sync()
    return _load(config.DATA_JSON)


if __name__ == "__main__":
    sync()
    print("✓ Synced", config.DATA_JSON)
