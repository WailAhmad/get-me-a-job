"""
LinkedIn Session Manager — uses a fresh temp dir for login to avoid
Chrome 'Your preferences cannot be read' dialog.

On Replit, Chrome is provided by nixpkgs (chromium) and CHROME_BIN /
CHROMEDRIVER_PATH env vars point to the binaries.
"""
import os
import logging
import shutil
from pathlib import Path
from backend.config import CHROME_PROFILE_PATH

# On Replit, nixpkgs installs chromium to a nix store path.
# CHROME_BIN and CHROMEDRIVER_PATH are set in replit.nix env block.
_CHROME_BIN = os.environ.get("CHROME_BIN")          # e.g. /nix/store/.../bin/chromium
_CHROMEDRIVER = os.environ.get("CHROMEDRIVER_PATH")  # e.g. /nix/store/.../bin/chromedriver


def _make_chrome_options(headless: bool = True, profile_dir: str = None):
    """Build Chrome options that work both locally (macOS) and on Replit (nixpkgs)."""
    from selenium.webdriver.chrome.options import Options
    options = Options()

    # Point to Replit's chromium if available
    if _CHROME_BIN:
        options.binary_location = _CHROME_BIN

    if profile_dir:
        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument("--profile-directory=Default")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-features=TranslateUI")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_experimental_option("prefs", {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "profile.default_content_setting_values.notifications": 2,
    })

    if headless:
        options.add_argument("--headless=new")

    return options


def _make_driver(headless: bool = True, profile_dir: str = None):
    """Create a Chrome WebDriver, using Replit's chromedriver if available."""
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service

    options = _make_chrome_options(headless=headless, profile_dir=profile_dir)

    if _CHROMEDRIVER:
        service = Service(executable_path=_CHROMEDRIVER)
        return webdriver.Chrome(service=service, options=options)
    return webdriver.Chrome(options=options)

logger = logging.getLogger(__name__)


def get_profile_path() -> str:
    path = Path(CHROME_PROFILE_PATH)
    path.mkdir(parents=True, exist_ok=True)
    return str(path.resolve())


def _remove_stale_locks(profile_path: Path):
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie", "DevToolsActivePort", "LOCK"):
        for lock in profile_path.rglob(name):
            try:
                if lock.is_dir(): shutil.rmtree(lock, ignore_errors=True)
                else: lock.unlink(missing_ok=True)
            except Exception: pass


def _get_login_dir() -> Path:
    """Return the login profile directory (where the user actually authenticated)."""
    return Path(CHROME_PROFILE_PATH).parent / "chrome_profile_login"


def _check_cookies_file(cookies_file: Path) -> bool:
    """True if the cookies file exists and is a valid non-empty SQLite DB."""
    if not cookies_file.exists():
        return False
    try:
        with open(cookies_file, "rb") as f:
            header = f.read(16)
        if header[:6] != b"SQLite":
            return False
        import sqlite3
        conn = sqlite3.connect(str(cookies_file))
        c = conn.cursor()
        c.execute('SELECT count(*) FROM cookies WHERE host_key LIKE "%linkedin%"')
        count = c.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def has_valid_session() -> bool:
    """True only when a Cookies file with LinkedIn entries exists.
    
    Checks both the main profile and the login profile, since on macOS
    Chrome encrypts cookies per-profile-path and the login profile is
    the one where the user actually authenticated.
    """
    # Check login profile first (where cookies actually work)
    login_cookies = _get_login_dir() / "Default" / "Cookies"
    if _check_cookies_file(login_cookies):
        return True
    # Fallback to main profile
    main_cookies = Path(CHROME_PROFILE_PATH) / "Default" / "Cookies"
    if _check_cookies_file(main_cookies):
        return True
    # Check automation profile
    automation_cookies = Path(CHROME_PROFILE_PATH).parent / "chrome_profile_automation" / "Default" / "Cookies"
    return _check_cookies_file(automation_cookies)


def open_login_browser() -> dict:
    """Open a visible Chrome window using a clean dedicated login profile."""
    try:
        login_dir = Path(CHROME_PROFILE_PATH).parent / "chrome_profile_login"
        if login_dir.exists():
            _remove_stale_locks(login_dir)
        (login_dir / "Default").mkdir(parents=True, exist_ok=True)
        logger.info("Login browser using dedicated profile: %s", login_dir)

        # On Replit there's no physical display — force headless
        headless = bool(os.environ.get("REPL_ID"))
        driver = _make_driver(headless=headless, profile_dir=str(login_dir))
        if not headless:
            driver.maximize_window()
        driver.get("https://www.linkedin.com/login")

        return {"success": True, "message": "Browser opened. Log in to LinkedIn — we'll detect it automatically.", "_driver": driver, "_temp_dir": str(login_dir)}
    except Exception as e:
        logger.error("Failed to open login browser: %s", e)
        return {"success": False, "message": str(e)}


def save_login_session(temp_dir: str) -> bool:
    """Copy Default/ from login dir to the permanent profile path.
    
    IMPORTANT: We do NOT delete the login dir anymore — the scraper
    reuses it directly because macOS Chrome encrypts cookies with a key
    tied to the user-data-dir path. Copying breaks decryption.
    """
    try:
        src = Path(temp_dir) / "Default"
        dst = Path(get_profile_path()) / "Default"
        if not src.exists(): return False
        if dst.exists(): shutil.rmtree(dst, ignore_errors=True)
        ignore = shutil.ignore_patterns("SingletonLock", "SingletonSocket", "SingletonCookie", "DevToolsActivePort", "LOCK", "Crashpad", "ShaderCache", "GrShaderCache", "GPUCache")
        shutil.copytree(src, dst, ignore=ignore)
        # Don't delete the login dir — the scraper uses it directly
        # shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info("LinkedIn session saved (login profile preserved for scraper).")
        return True
    except Exception as e:
        logger.error("Failed to save login session: %s", e)
        return False


def get_automation_profile_path() -> str:
    source = Path(get_profile_path())
    target = source.parent / "chrome_profile_automation"
    if source.exists() and not target.exists():
        ignore = shutil.ignore_patterns("SingletonLock", "SingletonSocket", "SingletonCookie", "DevToolsActivePort", "LOCK", "Crashpad", "ShaderCache", "GrShaderCache", "GPUCache")
        shutil.copytree(source, target, ignore=ignore, dirs_exist_ok=True)
    target.mkdir(parents=True, exist_ok=True)
    _remove_stale_locks(target)
    return str(target.resolve())


def verify_session_valid(driver=None) -> bool:
    own_driver = driver is None
    try:
        if own_driver:
            import time
            driver = _make_driver(headless=True, profile_dir=str(get_automation_profile_path()))
        driver.get("https://www.linkedin.com/feed/")
        import time; time.sleep(3)
        return "feed" in driver.current_url
    except Exception as e:
        logger.error("Session verification error: %s", e)
        return False
    finally:
        if own_driver and driver:
            try: driver.quit()
            except: pass
