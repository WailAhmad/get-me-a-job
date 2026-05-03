"""Profile router — app account/session and live LinkedIn profile import."""
import logging
import time
from typing import Optional
from fastapi import APIRouter, HTTPException
from backend import state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/profile", tags=["profile"])

def _is_placeholder_profile(profile: dict) -> bool:
    name = (profile.get("name") or "").strip().lower()
    title = (profile.get("title") or "").strip().lower()
    photo = (profile.get("photo") or "").strip()
    if not name or name in {"you", "join linkedin", "linkedin"}:
        return True
    if name == "wael ahmad" and (
        photo == "/photos/wael_avatar.png"
        or title in {"ai & data leader", "google account connected", "apple account connected"}
    ):
        return True
    return False


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
    if _is_placeholder_profile(p) and p.get("connection_type") != "local":
        return {"name": None, "title": None, "photo": None, "imported_at": None}
    return p


@router.get("/status")
def profile_status():
    p = state.get()["profile"]
    connected = bool(p.get("imported_at")) and p.get("connection_type") != "local" and not _is_placeholder_profile(p)
    return {"connected": connected, "profile": p if connected else None}


@router.post("/logout")
def logout():
    """Clear the profile session so the user must sign in again."""
    def m(s):
        s["profile"] = {"name": None, "title": None, "photo": None, "imported_at": None}
    state.update(m)
    return {"success": True}


@router.post("/connect")
def connect_profile():
    raise HTTPException(410, "Local workspace sign-in was removed. Use email verification or configured OAuth.")


@router.post("/google/connect")
def connect_google_profile():
    raise HTTPException(410, "Mock Google sign-in was removed. Use /api/auth/google/start with real OAuth credentials.")


@router.post("/apple/connect")
def connect_apple_profile():
    raise HTTPException(410, "Mock Apple sign-in was removed. Use /api/auth/apple/start with real OAuth credentials.")


@router.post("/import")
def import_profile():
    """Called right after LinkedIn auth to import name/title/photo."""
    extracted = _extract_via_selenium()
    if not extracted:
        raise HTTPException(409, "Could not import a real LinkedIn profile. Connect and verify LinkedIn in Settings first.")
    def m(s):
        s["profile"] = {
            **s.get("profile", {}),
            **extracted,
            "linkedin_synced_at": time.time(),
            "connection_type": s.get("profile", {}).get("connection_type") or "profile",
        }
    state.update(m)
    return {"success": True, "profile": state.get()["profile"]}
