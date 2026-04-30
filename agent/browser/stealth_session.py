"""Connect Playwright to running Chrome via CDP, apply stealth, return a Page.

Stealth is provided by `tf-playwright-stealth`, the actively maintained fork
of `playwright-stealth`. It patches the typical bot tells (`navigator.webdriver`,
plugin/language lists, chrome runtime, WebGL vendor strings, permissions API).
"""
from __future__ import annotations
from contextlib import asynccontextmanager
from typing import AsyncIterator, Tuple

from agent.logger import get_logger

log = get_logger("stealth")


@asynccontextmanager
async def session(ws_endpoint: str) -> AsyncIterator[Tuple[object, object, object, object]]:
    """Yield (playwright, browser, context, page) and clean up on exit.

    Usage:
        async with session(ws) as (pw, browser, ctx, page):
            await page.goto("https://www.linkedin.com/jobs/")
    """
    from playwright.async_api import async_playwright
    try:
        from playwright_stealth import Stealth  # tf-playwright-stealth >=1.1
        _stealth = Stealth()
        apply_stealth = _stealth.apply_stealth_async
    except ImportError:
        try:
            from playwright_stealth import stealth_async as apply_stealth  # legacy fallback
        except ImportError as exc:
            raise RuntimeError(
                "Could not import playwright_stealth. "
                "Run: pip install tf-playwright-stealth"
            ) from exc

    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.connect_over_cdp(ws_endpoint)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await apply_stealth(page)
        log.debug("stealth applied; page=%s", page.url)
        yield pw, browser, ctx, page
    finally:
        try:
            await pw.stop()
        except Exception:
            pass
