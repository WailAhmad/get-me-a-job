"""
Settings router — LinkedIn session management
"""
import logging
from fastapi import APIRouter
from backend import state
from backend.services import session_manager as sm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])

# Global store for the login browser state
_login_state: dict = {}


@router.get("/")
def get_all():
    s = state.get()
    return {
        "daily_cap": 100,
        "hourly_cap": 10,
        "live_mode": bool(s.get("live_mode")),
        "linkedin_session": sm.has_valid_session(),
    }


@router.get("/live-mode")
def get_live_mode():
    s = state.get()
    return {
        "live_mode": bool(s.get("live_mode")),
        "linkedin_session": sm.has_valid_session(),
        "effective": bool(s.get("live_mode")) and sm.has_valid_session(),
    }


@router.put("/live-mode")
def set_live_mode(body: dict):
    enabled = bool(body.get("enabled"))
    has_session = sm.has_valid_session()
    if enabled and not has_session:
        return {
            "success": False,
            "live_mode": False,
            "message": "Connect LinkedIn first — live mode requires a saved session.",
        }
    def m(s):
        s["live_mode"] = enabled
    state.update(m)
    return {
        "success": True,
        "live_mode": enabled,
        "effective": enabled and has_session,
        "message": "Live mode is ON — automation will now submit real LinkedIn applications." if enabled
                   else "Live mode is OFF — automation runs in demo mode only.",
    }


@router.get("/ai-providers")
def ai_providers():
    return [
        {"id": "anthropic", "label": "Anthropic Claude"},
        {"id": "openai",    "label": "OpenAI"},
        {"id": "ollama",    "label": "Ollama (local)"},
    ]


@router.get("/linkedin-session")
def get_session_status():
    has_session = sm.has_valid_session()
    if has_session:
        def m(s):
            source = s.setdefault("job_sources", {}).setdefault("linkedin", {})
            source["connected"] = True
        state.update(m)
    return {"has_session": has_session}


@router.post("/linkedin-session/open")
def open_login():
    global _login_state
    try:
        result = sm.open_login_browser()
        if result.get("success"):
            _login_state = {"driver": result.get("_driver"), "temp_dir": result.get("_temp_dir")}
            return {"success": True, "message": result["message"]}
        return {"success": False, "message": result.get("message", "Failed to open browser")}
    except Exception as e:
        logger.error("open_login error: %s", e)
        return {"success": False, "message": str(e)}


@router.get("/linkedin-session/login-status")
def check_login_status():
    global _login_state
    driver = _login_state.get("driver")
    if not driver:
        return {"logged_in": False, "message": "No login browser open"}
    try:
        url = driver.current_url
        if any(p in url for p in ["/feed", "/jobs", "/mynetwork", "/messaging", "/notifications"]):
            # Auto-save the session
            temp_dir = _login_state.get("temp_dir", "")
            if temp_dir:
                sm.save_login_session(temp_dir)
                def m(s):
                    source = s.setdefault("job_sources", {}).setdefault("linkedin", {})
                    source["connected"] = True
                state.update(m)
            try: driver.quit()
            except: pass
            _login_state = {}
            return {"logged_in": True, "message": "Authenticated! Entering your dashboard…"}
        return {"logged_in": False, "message": f"Waiting… ({url[:60]})"}
    except Exception as e:
        return {"logged_in": False, "message": str(e)}


@router.post("/linkedin-session/confirm")
def confirm_login():
    global _login_state
    driver = _login_state.get("driver")
    if not driver:
        return {"success": False, "message": "No login browser open"}
    try:
        url = driver.current_url
        if any(p in url for p in ["/feed", "/jobs", "/mynetwork", "/messaging", "/notifications"]):
            temp_dir = _login_state.get("temp_dir", "")
            if temp_dir:
                sm.save_login_session(temp_dir)
                def m(s):
                    source = s.setdefault("job_sources", {}).setdefault("linkedin", {})
                    source["connected"] = True
                state.update(m)
            try: driver.quit()
            except: pass
            _login_state = {}
            return {"success": True, "message": "LinkedIn session saved successfully!"}
        return {"success": False, "message": f"LinkedIn doesn't appear logged in yet. Current URL: {url[:60]}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/linkedin-session/verify")
def verify_session():
    try:
        ok = sm.verify_session_valid()
        return {"success": ok, "message": "Session is valid ✓" if ok else "Session appears expired — please reconnect"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.delete("/linkedin-session")
def clear_session():
    global _login_state
    import shutil
    from pathlib import Path
    from backend.config import CHROME_PROFILE_PATH
    driver = _login_state.get("driver")
    if driver:
        try: driver.quit()
        except: pass
        _login_state = {}
    p = Path(CHROME_PROFILE_PATH) / "Default"
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)
    def m(s):
        source = s.setdefault("job_sources", {}).setdefault("linkedin", {})
        source["connected"] = False
        source["connected_at"] = None
    state.update(m)
    return {"success": True, "message": "Session cleared"}


# ── Catch-all (MUST be last so it doesn't shadow specific routes) ─────
@router.put("/{key}")
def set_key(key: str, body: dict):
    return {"success": True, "key": key, "value": body.get("value")}
