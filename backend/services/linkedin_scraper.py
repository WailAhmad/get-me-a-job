"""
Real LinkedIn job-search scraper.

Drives a Selenium Chrome instance using the user's saved automation profile
(see services/session_manager.py) and pulls real job postings off
linkedin.com/jobs/search. Every job returned has a real numeric `id` that
resolves to a live URL on linkedin.com.

Returns dicts shaped like the rest of the engine expects:
    {
      "id": str,
      "title": str,
      "company": str,
      "location": str,
      "easy_apply": bool,
      "url": str,
      "url_verified": True,
      "submission_verified": False,
      "source": "LinkedIn",
      "source_id": "linkedin",
      "source_mode": "live",
      "posted_days_ago": int (best-effort),
      "discovered_at": float (epoch),
      "status": "discovered",
    }
"""
from __future__ import annotations

import logging
import re
import time
import urllib.parse
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# LinkedIn geoIds — keep this list pragmatic. Unknown countries fall back to
# a free-text `location=` parameter, which still works (just less reliable).
GEO_IDS = {
    "uae": "104305776",
    "united arab emirates": "104305776",
    "saudi arabia": "100459316",
    "ksa": "100459316",
    "qatar": "104170880",
    "kuwait": "105912427",
    "bahrain": "100425431",
    "oman": "103619019",
    "egypt": "106155005",
    "jordan": "101282786",
    "united kingdom": "101165590",
    "uk": "101165590",
    "united states": "103644278",
    "usa": "103644278",
    "germany": "101282230",
    "singapore": "102454443",
}


def _tpr_param(days: int) -> str:
    """LinkedIn's `f_TPR` parameter for posted-within filter (in seconds)."""
    if days <= 1:  return "r86400"
    if days <= 7:  return "r604800"
    if days <= 14: return "r1209600"
    return "r2592000"


def _make_driver(headless: bool = True):
    """Open Chrome with a COPY of the saved automation profile.

    We copy the profile to a fresh temp dir on each use to avoid
    lock conflicts with other Chrome instances. Chrome decrypts cookies
    using its Safe Storage key from macOS Keychain (NOT path-dependent),
    so the copy still has working cookies.
    """
    import shutil
    import tempfile
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from backend.services import session_manager as sm

    # Find the profile with valid cookies
    candidates = [
        Path(sm.get_profile_path()).parent / "chrome_profile_automation",
        sm._get_login_dir(),
        Path(sm.get_profile_path()),
    ]
    source_dir = None
    for candidate in candidates:
        if sm._check_cookies_file(candidate / "Default" / "Cookies"):
            source_dir = candidate
            break

    # Create a fresh copy to avoid lock conflicts
    temp_dir = Path(tempfile.mkdtemp(prefix="jobsland_chrome_"))
    if source_dir:
        logger.info("Copying profile from %s to %s", source_dir, temp_dir)
        # Remove the empty temp dir first, copytree needs it to not exist
        shutil.rmtree(temp_dir, ignore_errors=True)
        ignore = shutil.ignore_patterns(
            "SingletonLock", "SingletonSocket", "SingletonCookie",
            "DevToolsActivePort", "LOCK", "Crashpad",
            "ShaderCache", "GrShaderCache", "GPUCache", "BrowserMetrics*",
            "RunningChromeVersion", "chrome_debug.log", "*.tmp"
        )
        shutil.copytree(str(source_dir), str(temp_dir), ignore=ignore, symlinks=False, dirs_exist_ok=True)
    else:
        logger.warning("No profile with LinkedIn cookies found — search will be unauthenticated")

    import os as _os
    _chrome_bin = _os.environ.get("CHROME_BIN")
    _chromedriver = _os.environ.get("CHROMEDRIVER_PATH")

    options = Options()
    if _chrome_bin:
        options.binary_location = _chrome_bin
    options.add_argument(f"--user-data-dir={temp_dir}")
    options.add_argument("--profile-directory=Default")
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1440,1024")
    options.add_argument("--lang=en-US")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-component-update")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    if _chromedriver:
        from selenium.webdriver.chrome.service import Service as ChromeService
        driver = webdriver.Chrome(service=ChromeService(executable_path=_chromedriver), options=options)
    else:
        driver = webdriver.Chrome(options=options)
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
    except Exception:
        pass
    # Store temp dir for cleanup
    driver._temp_profile_dir = str(temp_dir)
    return driver


def _cleanup_driver(driver) -> None:
    """Close Chrome and remove its temporary profile copy."""
    if not driver:
        return
    tmp = getattr(driver, '_temp_profile_dir', None)
    try:
        driver.quit()
    except Exception:
        pass
    if tmp:
        try:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass


def _build_search_url(keywords: str, country: str, days: int, start: int = 0) -> str:
    params = {
        "keywords": keywords or "",
        "f_TPR": _tpr_param(days),
        "sortBy": "DD",
        "start": start,
    }
    geo = GEO_IDS.get((country or "").strip().lower())
    if geo:
        params["geoId"] = geo
    else:
        params["location"] = country or ""
    return "https://www.linkedin.com/jobs/search/?" + urllib.parse.urlencode(params)


def _scroll_results_panel(driver, By):
    """Scroll the left-side jobs list to lazy-load more cards."""
    candidates = [
        ".jobs-search-results-list",
        "div.scaffold-layout__list",
        "ul.scaffold-layout__list-container",
        ".jobs-search-results__list",
    ]
    panel = None
    for sel in candidates:
        try:
            panel = driver.find_element(By.CSS_SELECTOR, sel)
            if panel:
                break
        except Exception:
            pass
    for _ in range(10):
        try:
            if panel:
                driver.execute_script("arguments[0].scrollTop += 700", panel)
            else:
                driver.execute_script("window.scrollBy(0, 700)")
        except Exception:
            pass
        time.sleep(0.35)


def _safe_text(card, By, selectors: List[str]) -> str:
    for sel in selectors:
        try:
            el = card.find_element(By.CSS_SELECTOR, sel)
            text = (el.text or "").strip()
            if text:
                return text
        except Exception:
            pass
    return ""


def _extract_card(card, By) -> Optional[dict]:
    try:
        job_id = card.get_attribute("data-job-id") or card.get_attribute("data-occludable-job-id")
        if not job_id:
            try:
                href = card.find_element(By.CSS_SELECTOR, "a[href*='/jobs/view/']").get_attribute("href") or ""
                m = re.search(r"/jobs/view/(\d+)", href)
                job_id = m.group(1) if m else None
            except Exception:
                pass
        if not job_id or not str(job_id).isdigit():
            return None

        title = _safe_text(card, By, [
            ".job-card-list__title--link",
            ".job-card-list__title",
            ".job-card-container__link",
            "a[data-control-name='job_card_title']",
            ".artdeco-entity-lockup__title a",
            ".artdeco-entity-lockup__title",
            "a.job-card-container__link",
            # 2025/2026 LinkedIn DOM updates
            ".job-card-list__title--link span",
            ".job-card-container__link span",
            ".scaffold-layout__list-item a[href*='/jobs/view/'] span",
            "a[href*='/jobs/view/'] span",
            "a[href*='/jobs/view/']",
            "h3 a",
            "h3",
            "strong",
        ])

        # Fallback: extract from full card text (first meaningful line = title)
        if not title or title.lower() in ("", "unknown role"):
            try:
                full_text = (card.text or "").strip()
                lines = [l.strip() for l in full_text.split("\n") if l.strip()]
                # Skip lines that are clearly not titles
                skip_patterns = ["easy apply", "promoted", "ago", "applicant", "actively recruiting"]
                for line in lines:
                    ll = line.lower()
                    if any(sp in ll for sp in skip_patterns):
                        continue
                    if len(line) > 3 and len(line) < 120:
                        title = line
                        break
            except Exception:
                pass

        # LinkedIn sometimes prefixes a screen-reader "Job - " label and
        # appends badge text like "with verification"
        title = re.sub(r"^(job\s*-\s*)", "", title, flags=re.I).strip()
        title = re.sub(r"\s*with verification\b.*", "", title, flags=re.I).strip()
        title = re.sub(r"\n.*", "", title).strip()  # keep only the first line

        company = _safe_text(card, By, [
            ".job-card-container__primary-description",
            ".job-card-container__company-name",
            ".artdeco-entity-lockup__subtitle",
            ".artdeco-entity-lockup__subtitle span",
            "[data-test-job-card-company-name]",
            ".topcard__flavor",
            # 2025/2026 fallbacks
            ".job-card-list__company-name",
            ".artdeco-entity-lockup__subtitle a",
        ])

        # Company fallback: try second text line if no selector matched
        if not company or company.lower() in ("", "unknown company"):
            try:
                full_text = (card.text or "").strip()
                lines = [l.strip() for l in full_text.split("\n") if l.strip()]
                skip_patterns = ["easy apply", "promoted", "ago", "applicant", "actively recruiting"]
                found_title = False
                for line in lines:
                    ll = line.lower()
                    if any(sp in ll for sp in skip_patterns):
                        continue
                    if not found_title:
                        found_title = True
                        continue  # skip title line, take the next
                    if len(line) > 1 and len(line) < 80:
                        company = line
                        break
            except Exception:
                pass

        location = _safe_text(card, By, [
            ".job-card-container__metadata-wrapper",
            ".job-card-container__metadata-item",
            ".artdeco-entity-lockup__caption",
            ".artdeco-entity-lockup__caption span",
            ".job-card-container__metadata-item--workplace-type",
        ])

        # Easy Apply hint — LinkedIn shows the text "Easy Apply" inside the card
        # when applicable.
        easy = False
        try:
            blob = (card.text or "").lower()
            if "easy apply" in blob:
                easy = True
        except Exception:
            pass

        # Posted ago — LinkedIn cards say "2 days ago", "Reposted 1 week ago" etc.
        posted_days = None
        try:
            blob = (card.text or "").lower()
            m = re.search(r"(\d+)\s*(minute|hour|day|week|month)s?\s*ago", blob)
            if m:
                n = int(m.group(1)); unit = m.group(2)
                if unit.startswith("minute") or unit.startswith("hour"):
                    posted_days = 0
                elif unit.startswith("day"):
                    posted_days = n
                elif unit.startswith("week"):
                    posted_days = n * 7
                elif unit.startswith("month"):
                    posted_days = n * 30
        except Exception:
            pass

        # Detect if user already applied (LinkedIn shows "Applied" badge)
        already_applied = False
        try:
            blob = (card.text or "").lower()
            if re.search(r"\bapplied\b", blob) and "easy apply" not in blob.split("applied")[0][-20:]:
                already_applied = True
        except Exception:
            pass

        return {
            "id": str(job_id),
            "title": title or "Unknown role",
            "company": company or "Unknown company",
            "location": location or "Unknown",
            "easy_apply": easy,
            "already_applied": already_applied,
            "url": f"https://www.linkedin.com/jobs/view/{job_id}/",
            "url_verified": True,
            "submission_verified": False,
            "source": "LinkedIn",
            "source_id": "linkedin",
            "source_mode": "live",
            "posted_days_ago": posted_days if posted_days is not None else 0,
        }
    except Exception as exc:
        logger.warning("extract_card failed: %s", exc)
        return None


def search_jobs(keywords: str, country: str, recency_days: int,
                max_results: int = 25, headless: bool = True, driver=None,
                on_progress=None) -> List[dict]:
    """Run a single LinkedIn jobs search and return up to `max_results` real jobs."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    own_driver = driver is None
    if own_driver:
        driver = _make_driver(headless=headless)
    found: List[dict] = []
    seen_ids = set()
    try:
        for start in range(0, max(max_results, 25), 25):
            url = _build_search_url(keywords, country, recency_days, start)
            logger.info("LinkedIn search → %s", url)
            try:
                driver.get(url)
            except Exception as exc:
                logger.warning("driver.get failed: %s", exc)
                break

            # Quick auth check — if we got punted to the login page the session
            # is stale and we should bail loudly.
            cur = driver.current_url or ""
            if "/login" in cur or "/checkpoint" in cur or "/uas/login" in cur:
                logger.warning("LinkedIn redirected to login — session is not valid")
                raise PermissionError("LinkedIn session is not valid (redirected to login)")

            try:
                WebDriverWait(driver, 14).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR,
                        "[data-job-id], .job-card-container, .job-search-card, .scaffold-layout__list-item, .jobs-search-no-results-banner"))
                )
            except TimeoutException:
                logger.info("No jobs results loaded within timeout (start=%d)", start)
                break

            # No-results banner → bail
            try:
                driver.find_element(By.CSS_SELECTOR, ".jobs-search-no-results-banner")
                logger.info("No results banner; stopping pagination")
                break
            except Exception:
                pass

            _scroll_results_panel(driver, By)

            cards = driver.find_elements(By.CSS_SELECTOR,
                "li[data-occludable-job-id], [data-job-id], li.scaffold-layout__list-item, li.jobs-search-results__list-item, div.job-search-card")
            logger.info("Discovered %d cards on page (start=%d)", len(cards), start)

            page_added = 0
            for card in cards:
                job = _extract_card(card, By)
                if not job:
                    continue
                if job["id"] in seen_ids:
                    continue
                seen_ids.add(job["id"])
                found.append(job)
                page_added += 1
                if len(found) >= max_results:
                    break
            
            if on_progress:
                on_progress(len(found), keywords, country)
            
            if page_added == 0:
                logger.info("Page returned 0 new cards — stopping")
                break
            if len(found) >= max_results:
                break
        return found
    finally:
        if own_driver:
            _cleanup_driver(driver)


def search_jobs_multi(keywords_list: List[str], countries: List[str],
                      recency_days: int, max_per_combo: int = 12,
                      hard_cap: int = 80, headless: bool = True,
                      on_progress=None) -> List[dict]:
    """Run one search per (keyword × country), dedupe by job id."""
    seen: dict = {}
    keywords_list = [k.strip() for k in (keywords_list or []) if k and k.strip()] or [""]
    countries = [c.strip() for c in (countries or []) if c and c.strip()] or ["UAE"]
    total_combos = len(keywords_list) * len(countries)
    combo_idx = 0
    driver = _make_driver(headless=headless)
    try:
        for kw in keywords_list:
            for country in countries:
                combo_idx += 1
                if len(seen) >= hard_cap:
                    return list(seen.values())
                if on_progress:
                    on_progress("searching", kw, country, combo_idx, total_combos, len(seen))
                try:
                    results = search_jobs(kw, country, recency_days,
                                          max_results=max_per_combo, headless=headless,
                                          driver=driver)
                    for r in results:
                        seen[r["id"]] = r
                        if len(seen) >= hard_cap:
                            return list(seen.values())
                    if on_progress:
                        on_progress("batch_done", kw, country, combo_idx, total_combos, len(seen))
                except PermissionError:
                    raise
                except Exception as exc:
                    logger.exception("search_jobs failed for %r @ %r: %s", kw, country, exc)
                    if on_progress:
                        on_progress("error", kw, country, combo_idx, total_combos, len(seen))
        return list(seen.values())
    finally:
        _cleanup_driver(driver)
