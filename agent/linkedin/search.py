"""Real LinkedIn jobs search using Playwright + stealth.

For each (title × location) pair from data.json the agent navigates to
linkedin.com/jobs/search?... , scrolls the result panel to lazy-load cards,
and extracts real job IDs + metadata. No fake URLs.

Returns dicts shaped for the rest of the engine:

    {
      "id":          "3812345678",                    # real LinkedIn job_id
      "url":         "https://www.linkedin.com/jobs/view/3812345678/",
      "title":       "Head of AI",
      "company":     "Mastercard",
      "location":    "Dubai, United Arab Emirates",
      "easy_apply":  True,
      "posted_text": "2 days ago",
      "posted_days_ago": 2,
      "source":      "LinkedIn",
      "source_mode": "live",
    }
"""
from __future__ import annotations
import asyncio
import re
import urllib.parse
from typing import Any, Dict, List, Optional

from agent.logger import get_logger

log = get_logger("li.search")


# ── LinkedIn geo IDs (best-effort; falls back to free-text location) ──
GEO_IDS = {
    "bahrain":              "100425431",
    "united arab emirates": "104305776",
    "uae":                  "104305776",
    "saudi arabia":         "100459316",
    "ksa":                  "100459316",
    "qatar":                "104170880",
    "kuwait":               "105912427",
    "oman":                 "103619019",
    "egypt":                "106155005",
    "ireland":              "104738515",
    "united kingdom":       "101165590",
    "uk":                   "101165590",
    "england":              "101165590",
    "netherlands":          "102890719",
    "germany":              "101282230",
    "united states":        "103644278",
    "usa":                  "103644278",
    "singapore":            "102454443",
    "remote":               None,   # we'll add f_WT=2 instead of geoId
}


def _tpr_param(days: int) -> str:
    """LinkedIn `f_TPR` (time posted, in seconds)."""
    if days <= 1:  return "r86400"
    if days <= 7:  return "r604800"
    if days <= 14: return "r1209600"
    return "r2592000"


def _build_search_url(keywords: str, location: str, days: int, start: int = 0) -> str:
    params: Dict[str, Any] = {
        "keywords": keywords or "",
        "f_TPR":    _tpr_param(days),
        "sortBy":   "DD",     # date posted, descending
        "start":    start,
    }
    loc_key = (location or "").strip().lower()
    if loc_key == "remote":
        params["f_WT"] = "2"        # remote-only filter
    elif loc_key in GEO_IDS and GEO_IDS[loc_key]:
        params["geoId"] = GEO_IDS[loc_key]
    else:
        params["location"] = location or ""
    return "https://www.linkedin.com/jobs/search/?" + urllib.parse.urlencode(params)


def _parse_posted(text: str) -> Optional[int]:
    """Convert '2 days ago' / '3 hours ago' / 'Reposted 1 week ago' → days."""
    if not text:
        return None
    blob = text.lower()
    m = re.search(r"(\d+)\s*(minute|hour|day|week|month)s?\s*ago", blob)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    if unit in ("minute", "hour"): return 0
    if unit == "day":              return n
    if unit == "week":             return n * 7
    if unit == "month":            return n * 30
    return None


# ── Per-page extraction (runs entirely in the browser via page.evaluate) ──
_EXTRACT_JS = r"""
() => {
  const out = [];
  const cards = document.querySelectorAll(
    '[data-job-id], li.scaffold-layout__list-item, li.jobs-search-results__list-item, div.job-search-card'
  );
  cards.forEach(card => {
    const jid = card.getAttribute('data-job-id')
             || card.getAttribute('data-occludable-job-id')
             || (card.querySelector('a[href*="/jobs/view/"]')?.href || '')
                  .match(/\/jobs\/view\/(\d+)/)?.[1];
    if (!jid || !/^\d+$/.test(jid)) return;

    const text = (card.innerText || '').toLowerCase();
    const easyApply = text.includes('easy apply');

    const pick = sels => {
      for (const sel of sels) {
        const el = card.querySelector(sel);
        const t = el?.innerText?.trim();
        if (t) return t;
      }
      return '';
    };

    let title = pick([
      '.job-card-list__title--link',
      '.job-card-list__title',
      '.job-card-container__link',
      '.artdeco-entity-lockup__title a',
      '.artdeco-entity-lockup__title',
      'h3 a',
      'h3',
      'a[href*="/jobs/view/"]',
    ]);
    title = title.replace(/^job\s*-\s*/i, '').replace(/\s*\(.*\)\s*$/, '').trim();
    // LinkedIn duplicates the title text inside aria-hidden — collapse line breaks
    title = title.split('\n').map(s => s.trim()).filter(Boolean)[0] || title;

    const company = pick([
      '.job-card-container__primary-description',
      '.job-card-container__company-name',
      '.artdeco-entity-lockup__subtitle',
      '[data-test-job-card-company-name]',
    ]);

    const location = pick([
      '.job-card-container__metadata-wrapper',
      '.job-card-container__metadata-item',
      '.artdeco-entity-lockup__caption',
    ]);

    // posted text — visible inside the metadata block
    let postedText = '';
    const m = (card.innerText || '').match(
      /(\d+\s*(minute|hour|day|week|month)s?\s*ago)/i
    );
    if (m) postedText = m[1];

    out.push({
      id: jid,
      title,
      company,
      location,
      easy_apply: easyApply,
      posted_text: postedText,
    });
  });
  return out;
}
"""


_PANEL_SELECTORS = [
    ".jobs-search-results-list",
    "div.scaffold-layout__list",
    "ul.scaffold-layout__list-container",
    ".jobs-search-results__list",
]


async def _scroll_results_panel(page) -> None:
    """Scroll the result list to lazy-load cards.

    Re-queries the panel each iteration so a navigation in the middle (which
    detaches handles) doesn't blow us up — we just stop scrolling silently.
    """
    panel_js = """
        (sels) => {
          for (const sel of sels) {
            const el = document.querySelector(sel);
            if (el) { el.scrollTop += 700; return true; }
          }
          window.scrollBy(0, 700);
          return false;
        }
    """
    for _ in range(10):
        try:
            await page.evaluate(panel_js, _PANEL_SELECTORS)
        except Exception as exc:
            log.debug("scroll evaluate stopped: %s", exc)
            return
        await asyncio.sleep(0.4)


async def _auth_state(page) -> str:
    """Returns 'authed' | 'logged_out' | 'checkpoint'."""
    url = page.url or ""
    if any(p in url for p in ("/login", "/uas/login")):
        return "logged_out"
    if any(p in url for p in ("/checkpoint", "/authwall")):
        return "checkpoint"
    # Some logged-out routes still serve content but show the "Join" overlay.
    try:
        guest = await page.evaluate(
            "() => /Agree\\s*&\\s*Join/i.test(document.body.innerText || '')"
        )
        if guest:
            return "logged_out"
    except Exception:
        pass
    return "authed"


async def assert_authenticated(page) -> None:
    """Visit /feed and raise PermissionError if LinkedIn isn't logged in."""
    try:
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=25000)
    except Exception as exc:
        log.warning("could not load /feed for auth check: %s", exc)
    state = await _auth_state(page)
    if state != "authed":
        raise PermissionError(
            f"LinkedIn session is not authenticated (state={state}). "
            "Run `python -m agent --login` and complete the sign-in."
        )
    log.info("✓ LinkedIn session is authenticated")


async def search_one(page, keywords: str, location: str,
                     recency_days: int, max_results: int = 25) -> List[Dict[str, Any]]:
    """One search query — paginates `start=0,25,50,…` until empty / cap."""
    found: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for start in range(0, max(max_results, 25), 25):
        url = _build_search_url(keywords, location, recency_days, start)
        log.info("→ %s @ %s  (start=%d)", keywords, location, start)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception as exc:
            log.warning("goto failed: %s", exc)
            break

        if not await _is_logged_in(page):
            raise PermissionError(
                "LinkedIn session expired (page redirected to login). "
                "Run `python -m agent --login` to sign in once."
            )

        # Wait for either cards or the no-results banner.
        try:
            await page.wait_for_selector(
                "[data-job-id], .job-card-container, .job-search-card, "
                ".jobs-search-no-results-banner",
                timeout=14000,
            )
        except Exception:
            log.info("No cards visible (timeout) — stopping")
            break

        if await page.query_selector(".jobs-search-no-results-banner"):
            log.info("No-results banner — stopping")
            break

        await _scroll_results_panel(page)

        try:
            cards = await page.evaluate(_EXTRACT_JS)
        except Exception as exc:
            log.warning("extraction JS failed: %s", exc)
            break

        page_added = 0
        for c in cards:
            jid = c.get("id")
            if not jid or jid in seen:
                continue
            seen.add(jid)
            posted_days = _parse_posted(c.get("posted_text") or "")
            found.append({
                "id":               jid,
                "title":            c.get("title") or "",
                "company":          c.get("company") or "",
                "location":         c.get("location") or "",
                "easy_apply":       bool(c.get("easy_apply")),
                "url":              f"https://www.linkedin.com/jobs/view/{jid}/",
                "posted_text":      c.get("posted_text") or "",
                "posted_days_ago":  posted_days if posted_days is not None else 0,
                "source":           "LinkedIn",
                "source_id":        "linkedin",
                "source_mode":      "live",
                "url_verified":     True,
                "submission_verified": False,
            })
            page_added += 1
            if len(found) >= max_results:
                break

        log.info("  + %d new cards (total %d)", page_added, len(found))
        if page_added == 0 or len(found) >= max_results:
            break

    return found


async def search_many(page, *, titles: List[str], locations: List[str],
                      recency_days: int, max_per_combo: int = 12,
                      hard_cap: int = 80,
                      exclude_companies: Optional[List[str]] = None
                      ) -> List[Dict[str, Any]]:
    """Run all (title × location) pairs. Returns deduped + filtered list."""
    titles    = [t.strip() for t in (titles    or []) if t and t.strip()] or [""]
    locations = [l.strip() for l in (locations or []) if l and l.strip()] or ["Remote"]
    excl = {(c or "").strip().lower() for c in (exclude_companies or []) if c}

    seen: Dict[str, Dict[str, Any]] = {}
    for title in titles:
        for loc in locations:
            if len(seen) >= hard_cap:
                break
            try:
                results = await search_one(page, title, loc, recency_days,
                                           max_results=max_per_combo)
            except PermissionError:
                raise
            except Exception as exc:
                log.exception("search failed for %r @ %r: %s", title, loc, exc)
                continue
            for r in results:
                if r["id"] in seen:
                    continue
                if excl and (r.get("company") or "").strip().lower() in excl:
                    log.debug("excluded company: %s", r.get("company"))
                    continue
                seen[r["id"]] = r
                if len(seen) >= hard_cap:
                    break
        if len(seen) >= hard_cap:
            break

    log.info("search complete: %d unique jobs across %d × %d queries",
             len(seen), len(titles), len(locations))
    return list(seen.values())
