"""
Profile router — pulls name / title / photo from the active LinkedIn session.

Falls back to a sensible default for Wael so the UI is always populated;
when a real Selenium session is connected, we extract the live profile.
"""
import logging
import time
from typing import Optional
from fastapi import APIRouter
from backend import state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/profile", tags=["profile"])

DEFAULT_PROFILE = {
    "name": "Wael Ahmad",
    "title": "AI & Data Leader",
    "photo": "/avatar_wael.png",
}

DEFAULT_GOOGLE_PROFILE = {
    "name": "Wael Ahmad",
    "title": "Google account connected",
    "photo": "/avatar_wael.png",
}

DEFAULT_APPLE_PROFILE = {
    "name": "Wael Ahmad",
    "title": "Apple account connected",
    "photo": "/avatar_wael.png",
}


def _is_placeholder_profile(profile: dict) -> bool:
    name = (profile.get("name") or "").strip().lower()
    return not name or name in {"you", "join linkedin", "linkedin"}


def _extract_via_selenium() -> Optional[dict]:
    """Best-effort extraction from a live LinkedIn session. Returns None on failure."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from backend.services import session_manager as sm

        options = Options()
        options.add_argument(f"--user-data-dir={sm.get_automation_profile_path()}")
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=options)
        try:
            driver.get("https://www.linkedin.com/in/me/")
            time.sleep(3)
            name = ""
            for selector in ["h1", ".text-heading-xlarge", ".pv-text-details__left-panel h1"]:
                try:
                    name = driver.find_element(By.CSS_SELECTOR, selector).text.strip()
                    if name:
                        break
                except Exception:
                    pass
            try:
                title = driver.find_element(By.CSS_SELECTOR, ".text-body-medium").text.strip()
            except Exception:
                title = ""
            try:
                photo = None
                for selector in [
                    "img.pv-top-card-profile-picture__image--show",
                    "img.pv-top-card-profile-picture__image",
                    ".pv-top-card-profile-picture img",
                    "img.global-nav__me-photo",
                ]:
                    try:
                        photo = driver.find_element(By.CSS_SELECTOR, selector).get_attribute("src")
                        if photo:
                            break
                    except Exception:
                        pass
            except Exception:
                photo = None
            if name and not _is_placeholder_profile({"name": name}):
                return {"name": name, "title": title or "Professional", "photo": photo}
        finally:
            try: driver.quit()
            except Exception: pass
    except Exception as e:
        logger.warning("Profile extract via selenium failed: %s", e)
    return None


@router.get("/")
def get_profile():
    s = state.get()
    p = s["profile"]
    if not _is_placeholder_profile(p):
        return p
    return {**DEFAULT_PROFILE, "imported_at": None}


@router.get("/status")
def profile_status():
    p = state.get()["profile"]
    connected = bool(p.get("imported_at")) and not _is_placeholder_profile(p)
    return {"connected": connected, "profile": p if connected else None}


@router.post("/connect")
def connect_profile():
    """
    Profile-only sign-in gate.

    This deliberately does not create a LinkedIn automation browser session.
    It lets onboarding proceed before CV upload, while Settings can later connect
    the separate automation session needed for job browsing/applying.
    """
    current = state.get()["profile"]
    profile = current if not _is_placeholder_profile(current) else DEFAULT_PROFILE

    def m(s):
        s["profile"] = {**profile, "imported_at": time.time(), "connection_type": "profile"}

    state.update(m)
    return {"success": True, "profile": state.get()["profile"]}


@router.post("/google/connect")
def connect_google_profile():
    """
    Profile-only Google sign-in gate.

    This creates the app account/session for onboarding. In production this is
    where Google OAuth would exchange an authorization code and store the
    Google profile name/photo/email.
    """
    current = state.get()["profile"]
    profile = current if not _is_placeholder_profile(current) else DEFAULT_GOOGLE_PROFILE

    def m(s):
        s["profile"] = {
            **profile,
            "imported_at": time.time(),
            "connection_type": "google",
            "auth_provider": "google",
        }

    state.update(m)
    return {"success": True, "profile": state.get()["profile"]}


@router.post("/apple/connect")
def connect_apple_profile():
    """
    Profile-only Apple sign-in gate.

    In production this is where Sign in with Apple would validate the identity
    token and store the user's Apple profile/email.
    """
    current = state.get()["profile"]
    profile = current if not _is_placeholder_profile(current) else DEFAULT_APPLE_PROFILE

    def m(s):
        s["profile"] = {
            **profile,
            "imported_at": time.time(),
            "connection_type": "apple",
            "auth_provider": "apple",
        }

    state.update(m)
    return {"success": True, "profile": state.get()["profile"]}


@router.post("/import")
def import_profile():
    """Called right after LinkedIn auth to import name/title/photo."""
    extracted = _extract_via_selenium() or DEFAULT_PROFILE
    def m(s):
        s["profile"] = {
            **s.get("profile", {}),
            **extracted,
            "linkedin_synced_at": time.time(),
            "connection_type": s.get("profile", {}).get("connection_type") or "profile",
        }
    state.update(m)
    return {"success": True, "profile": state.get()["profile"]}
