"""
Debug endpoints for live-mode development.

These let you exercise the real LinkedIn scraper and applier in isolation,
without running the full automation engine. They are intentionally
unauthenticated and intended for local use only — do not expose in prod.
"""
from __future__ import annotations

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend import state
from backend.services import session_manager as sm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/linkedin", tags=["linkedin-debug"])


class SearchIn(BaseModel):
    keywords: str = ""
    country: str = "UAE"
    recency_days: int = 7
    max_results: int = 10
    headless: bool = True


@router.post("/test-search")
def test_search(body: SearchIn):
    """Run one real LinkedIn jobs search and return what we extracted."""
    if not sm.has_valid_session():
        raise HTTPException(400, "LinkedIn session is not connected.")
    from backend.services import linkedin_scraper as ls
    try:
        logger.info("test-search: keywords=%s country=%s days=%d max=%d headless=%s",
                     body.keywords, body.country, body.recency_days, body.max_results, body.headless)
        jobs = ls.search_jobs(
            keywords=body.keywords,
            country=body.country,
            recency_days=body.recency_days,
            max_results=body.max_results,
            headless=body.headless,
        )
        logger.info("test-search: returned %d jobs", len(jobs))
        return {"count": len(jobs), "jobs": jobs}
    except PermissionError as exc:
        logger.warning("test-search: PermissionError: %s", exc)
        raise HTTPException(401, str(exc))
    except Exception as exc:
        logger.exception("test_search failed")
        raise HTTPException(500, f"{type(exc).__name__}: {exc}")


class ApplyIn(BaseModel):
    job_url: str
    headless: bool = True


@router.post("/test-apply")
def test_apply(body: ApplyIn):
    """Open a real LinkedIn job URL and try to Easy Apply (using saved CV + answers)."""
    if not sm.has_valid_session():
        raise HTTPException(400, "LinkedIn session is not connected.")
    from backend.services import linkedin_scraper as ls
    from backend.services import linkedin_applier as la
    s = state.get()
    driver = ls._make_driver(headless=body.headless)
    try:
        try:
            return la.apply_easy(driver, body.job_url, s["cv"], s["answers"])
        except Exception as exc:
            logger.exception("test_apply failed")
            raise HTTPException(500, f"{type(exc).__name__}: {exc}")
    finally:
        try: driver.quit()
        except Exception: pass


@router.get("/diagnose")
def diagnose():
    """Quick health-check for the live-mode prerequisites."""
    info = {
        "linkedin_session": sm.has_valid_session(),
        "live_mode_setting": bool(state.get().get("live_mode")),
    }
    try:
        from backend.services import linkedin_scraper as ls  # noqa: F401
        info["scraper_module"] = "ok"
    except Exception as exc:
        info["scraper_module"] = f"import error: {exc}"
    try:
        from backend.services import linkedin_applier as la  # noqa: F401
        info["applier_module"] = "ok"
    except Exception as exc:
        info["applier_module"] = f"import error: {exc}"
    try:
        import selenium  # noqa: F401
        info["selenium"] = "installed"
    except Exception:
        info["selenium"] = "not installed"
    return info
