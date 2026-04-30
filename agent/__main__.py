"""`python -m agent` entrypoint.

Modes:
    --login          Open Chrome on-screen so you can sign into LinkedIn once.
                     Cookies persist in data/chrome_user_data/. Run this once.

    --search-only    DRY RUN. Boots stealth Chrome, runs the real LinkedIn
                     search, scores up to N jobs against your profile via
                     Groq, prints a ranked report. Submits NOTHING.

    (no args)        Phase-1 boot stub (sync data + open stealth session).
                     Real autonomous loop arrives in Phase 6.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
import time
from typing import Any, Dict, List

from agent import config, data_sync
from agent.browser.chrome_launcher import launch_chrome
from agent.browser.stealth_session import session
from agent.logger import get_logger

log = get_logger("main")


# ── Mode: --login ─────────────────────────────────────────────────────
async def cmd_login() -> int:
    """Open Chrome on-screen and wait for the user to sign in."""
    log.info("Opening Chrome for one-time LinkedIn sign-in…")

    ws = launch_chrome(visible=True)
    async with session(ws) as (_pw, _br, _ctx, page):
        await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")

        log.info("→ Sign in to LinkedIn in the open Chrome window.")
        log.info("→ I'll detect when you reach the feed/jobs page and exit.")

        deadline = time.time() + 300   # 5 minutes
        while time.time() < deadline:
            url = page.url or ""
            if any(p in url for p in ("/feed", "/jobs", "/mynetwork", "/messaging", "/notifications")):
                log.info("✓ LinkedIn login detected. Cookies saved to %s", config.PROFILE_DIR)
                await asyncio.sleep(2.0)
                return 0
            await asyncio.sleep(2.0)

        log.warning("Login window timed out after 5 minutes.")
        return 1


# ── Mode: --search-only ───────────────────────────────────────────────
async def cmd_search_only(max_results: int, score: bool) -> int:
    """Run the real LinkedIn search + (optionally) score, but don't apply."""
    from agent.linkedin import search as li_search
    from agent.linkedin import job_page as li_job

    data = data_sync.sync()
    titles    = data.get("targets", {}).get("titles") or []
    locations = data.get("targets", {}).get("locations") or []
    days      = int(data.get("targets", {}).get("recency_days") or 7)
    excl      = data.get("targets", {}).get("exclude_companies") or []

    log.info("Search-only mode")
    log.info("  titles    : %d", len(titles))
    log.info("  locations : %d", len(locations))
    log.info("  recency   : last %d days", days)
    log.info("  hard cap  : %d", max_results)

    ws = launch_chrome()
    async with session(ws) as (_pw, _br, _ctx, page):
        try:
            jobs = await li_search.search_many(
                page,
                titles=titles,
                locations=locations,
                recency_days=days,
                max_per_combo=8,
                hard_cap=max_results,
                exclude_companies=excl,
            )
        except PermissionError as exc:
            log.error("%s", exc)
            return 2

        log.info("Discovered %d unique jobs.", len(jobs))
        if not jobs:
            return 0

        # Print the raw list first so we have something even if scoring fails.
        print()
        print("=" * 90)
        print(f"  {'#':<3} {'Score':>5}  {'Easy':<4}  {'Title':<40}  {'Company':<22}  Posted")
        print("-" * 90)

        if not score:
            for i, j in enumerate(jobs, 1):
                print(f"  {i:<3} {'-':>5}  "
                      f"{('✓' if j['easy_apply'] else '·'):<4}  "
                      f"{j['title'][:40]:<40}  "
                      f"{j['company'][:22]:<22}  "
                      f"{j.get('posted_text') or '?'}")
            print("=" * 90)
            return 0

        # Score the top easy-apply jobs only (saves Groq quota; we apply only those anyway).
        from agent.ai.scoring import score_job
        easy = [j for j in jobs if j.get("easy_apply")]
        rest = [j for j in jobs if not j.get("easy_apply")]
        log.info("Scoring %d Easy Apply candidates with Groq…", len(easy))

        scored: List[Dict[str, Any]] = []
        for j in easy:
            try:
                details = await li_job.fetch_job_details(page, j["url"])
                jd = (details or {}).get("description") or ""
                jd_short = jd[:5000]   # keep prompt small
                result = score_job(data, {**j, "description": jd_short})
                scored.append({**j, "score": result.score,
                               "rationale": result.rationale,
                               "title_alignment": result.title_alignment,
                               "matched_skills": result.matched_skills})
            except Exception as exc:
                log.warning("scoring failed for %s: %s", j["url"], exc)
                scored.append({**j, "score": 0, "rationale": f"error: {exc}"})

        scored.sort(key=lambda r: r.get("score", 0), reverse=True)

        for i, j in enumerate(scored, 1):
            mark = "✓" if (j["easy_apply"] and j.get("score", 0) >= 85) else " "
            print(f"  {i:<3} {j.get('score',0):>5}  "
                  f"{('✓' if j['easy_apply'] else '·'):<4}  "
                  f"{j['title'][:40]:<40}  "
                  f"{j['company'][:22]:<22}  "
                  f"{mark} {j.get('posted_text') or '?'}")
        print("=" * 90)

        # Show non-easy at the bottom for awareness.
        if rest:
            print(f"\n  ({len(rest)} non-Easy-Apply jobs not scored — would route to External)")

        # Save to a JSON snapshot for inspection.
        snap = config.DATA_DIR / "search_snapshot.json"
        snap.write_text(json.dumps({"discovered": jobs, "scored": scored},
                                   indent=2, ensure_ascii=False))
        log.info("snapshot → %s", snap)
        return 0


# ── Mode: default boot stub ───────────────────────────────────────────
async def cmd_boot() -> int:
    log.info("Jobs Land Agent v0.1 booting")
    log.info("data dir = %s", config.DATA_DIR)
    log.info("CDP port = %d", config.CDP_PORT)

    data = data_sync.sync()
    log.info("profile loaded: %s %s — %d titles, %d locations, threshold=%d",
             data.get("identity", {}).get("first_name"),
             data.get("identity", {}).get("last_name"),
             len(data.get("targets", {}).get("titles", [])),
             len(data.get("targets", {}).get("locations", [])),
             data.get("preferences", {}).get("min_match_score"))

    ws = launch_chrome()
    async with session(ws) as (_pw, _br, _ctx, page):
        await page.goto("about:blank", wait_until="load")
        log.info("stealth session ready (Chrome %s)", page.url)
    log.info("boot complete (phase-1 stub) — exiting cleanly")
    return 0


# ── CLI entrypoint ────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m agent")
    parser.add_argument("--login", action="store_true",
                        help="One-time on-screen LinkedIn sign-in.")
    parser.add_argument("--search-only", action="store_true",
                        help="Real LinkedIn search; print ranked report; no applies.")
    parser.add_argument("--no-score", action="store_true",
                        help="In --search-only, skip Groq scoring (just discovery).")
    parser.add_argument("--max", type=int, default=40,
                        help="Hard cap on discovered jobs in --search-only (default 40).")
    args = parser.parse_args()

    if args.login:
        return asyncio.run(cmd_login())
    if args.search_only:
        return asyncio.run(cmd_search_only(max_results=args.max, score=not args.no_score))
    return asyncio.run(cmd_boot())


if __name__ == "__main__":
    sys.exit(main())
