"""Open one LinkedIn job page and extract the description + apply method."""
from __future__ import annotations
import asyncio
from typing import Any, Dict, Optional

from agent.logger import get_logger

log = get_logger("li.job")


# Reads the visible JD body. LinkedIn's selectors change every few months —
# we try a stack of them and concatenate the longest non-empty result.
_EXTRACT_JS = r"""
() => {
  const sels = [
    '.jobs-description__content',
    '.jobs-description-content__text',
    '.jobs-box__html-content',
    '.jobs-description',
    'article.jobs-description__container',
    '#job-details',
  ];
  let best = '';
  for (const sel of sels) {
    document.querySelectorAll(sel).forEach(el => {
      const t = (el.innerText || '').trim();
      if (t.length > best.length) best = t;
    });
  }

  // Apply method
  const allBtns = Array.from(document.querySelectorAll('button'));
  const easy = allBtns.some(b => /easy apply/i.test(
    (b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')
  ));
  const externalApply = allBtns.some(b => /apply on company website/i.test(
    (b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')
  ));
  const alreadyApplied = /(you applied|you've applied|application submitted)/i.test(
    document.body.innerText || ''
  );

  // Header
  const titleEl = document.querySelector(
    '.jobs-unified-top-card__job-title, .job-details-jobs-unified-top-card__job-title, h1'
  );
  const companyEl = document.querySelector(
    '.jobs-unified-top-card__company-name, .job-details-jobs-unified-top-card__company-name, a[data-test-app-aware-link]'
  );
  const locEl = document.querySelector(
    '.jobs-unified-top-card__bullet, .job-details-jobs-unified-top-card__primary-description-container, .jobs-unified-top-card__primary-description'
  );

  return {
    description: best,
    title:    (titleEl?.innerText || '').trim(),
    company:  (companyEl?.innerText || '').trim(),
    location: (locEl?.innerText || '').trim(),
    easy_apply: easy,
    external_apply: externalApply,
    already_applied: alreadyApplied,
  };
}
"""


async def fetch_job_details(page, job_url: str, *,
                            timeout_ms: int = 15000) -> Optional[Dict[str, Any]]:
    """Navigate to a job URL and pull the JD + apply-method flags.

    Returns None if the page didn't load or LinkedIn redirected us out
    (logged-out, soft-blocked, etc.). The caller decides how to handle.
    """
    try:
        await page.goto(job_url, wait_until="domcontentloaded", timeout=timeout_ms)
    except Exception as exc:
        log.warning("goto failed for %s: %s", job_url, exc)
        return None

    cur = page.url or ""
    if any(p in cur for p in ("/login", "/checkpoint", "/uas/login", "/authwall")):
        log.warning("redirected to login while opening %s", job_url)
        raise PermissionError("LinkedIn session expired during job-page fetch")

    # Wait for either the description or top-card to render.
    try:
        await page.wait_for_selector(
            ".jobs-description, .jobs-description__content, .job-details-jobs-unified-top-card__job-title, h1",
            timeout=timeout_ms,
        )
    except Exception:
        log.info("description didn't render for %s", job_url)

    # LinkedIn lazy-loads the description; let it settle.
    await asyncio.sleep(0.6)

    try:
        info = await page.evaluate(_EXTRACT_JS)
    except Exception as exc:
        log.warning("extraction JS failed for %s: %s", job_url, exc)
        return None

    if not info or not (info.get("description") or "").strip():
        log.info("empty JD for %s", job_url)
    else:
        log.debug("JD length=%d  easy=%s  external=%s  applied=%s",
                  len(info["description"]), info.get("easy_apply"),
                  info.get("external_apply"), info.get("already_applied"))
    return info or {}
