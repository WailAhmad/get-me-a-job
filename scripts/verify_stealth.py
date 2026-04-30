"""Sanity check: open bot.sannysoft.com via the stealth session.

Saves a screenshot to data/stealth_check.png and prints the key fingerprint
signals. If `webdriver` is `None` and the test grid is mostly green, we're
good to go.

Usage:
    backend/.venv/bin/python scripts/verify_stealth.py
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

# Ensure repo root is on sys.path when invoked as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.browser.chrome_launcher import launch_chrome
from agent.browser.stealth_session import session
from agent.logger import get_logger
from agent import config

log = get_logger("verify")


async def _run() -> int:
    ws = launch_chrome()
    async with session(ws) as (_pw, _br, _ctx, page):
        await page.goto("https://bot.sannysoft.com/", wait_until="networkidle")
        out_png = config.DATA_DIR / "stealth_check.png"
        await page.screenshot(path=str(out_png), full_page=True)

        webdriver = await page.evaluate("navigator.webdriver")
        ua        = await page.evaluate("navigator.userAgent")
        plugins   = await page.evaluate("navigator.plugins.length")
        languages = await page.evaluate("navigator.languages")
        webgl_v   = await page.evaluate("""
            () => {
              const c = document.createElement('canvas').getContext('webgl');
              const ext = c && c.getExtension('WEBGL_debug_renderer_info');
              return ext ? c.getParameter(ext.UNMASKED_VENDOR_WEBGL) : null;
            }
        """)

        log.info("webdriver = %r  (expect: None or False)", webdriver)
        log.info("userAgent = %s", ua)
        log.info("plugins   = %d  (expect: > 0)", plugins)
        log.info("languages = %s", languages)
        log.info("webgl vendor = %s", webgl_v)
        log.info("screenshot → %s", out_png)
        # webdriver should be falsy (None or False — both indicate the boolean flag
        # is *not* set to True, which is the only thing LinkedIn checks for).
        passed = (not webdriver) and (plugins > 0)
        log.info("RESULT: %s", "PASS ✓" if passed else "FAIL ✗")
        return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
