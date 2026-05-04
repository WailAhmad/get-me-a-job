"""
Dashboard router — aggregate counts for the main cards.
Returns last-run stats and today stats separately so the UI can
label them clearly.
"""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter
from backend import state

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
def stats():
    s = state.get()
    items = list(s["jobs"]["items"].values())
    today = datetime.now(timezone.utc).date()
    week_ago = today - timedelta(days=7)

    # ── Identify the latest run ──────────────────────────────────────────────
    current_run_id = s["automation"].get("current_run_id")
    all_run_ids = sorted(
        {j.get("run_id") for j in items if j.get("run_id")},
        reverse=True,
    )
    # "last run" = the most-recent completed run (or current if still running)
    last_run_id = all_run_ids[0] if all_run_ids else current_run_id
    last_run_jobs = [j for j in items if j.get("run_id") == last_run_id] if last_run_id else []

    # ── Helpers ──────────────────────────────────────────────────────────────
    def is_today(ts):
        return ts and datetime.fromtimestamp(ts, tz=timezone.utc).date() == today

    def is_this_week(ts):
        return ts and datetime.fromtimestamp(ts, tz=timezone.utc).date() >= week_ago

    # ── All-time buckets ─────────────────────────────────────────────────────
    all_applied          = [j for j in items if j.get("status") == "applied"]
    all_verified         = [j for j in all_applied if j.get("submission_verified")]
    all_already_applied  = [j for j in items if j.get("status") == "already_applied"]
    all_external         = [j for j in items if j.get("status") == "external"]
    all_failed           = [j for j in items if j.get("status") == "failed"]
    all_pending          = [j for j in items if j.get("status") == "pending"]
    pending_questions    = [j for j in all_pending if j.get("pending_kind") != "verify_source"]
    pending_verify       = [j for j in all_pending if j.get("pending_kind") == "verify_source"]

    # ── Last Run ─────────────────────────────────────────────────────────────
    lr_found         = len(last_run_jobs)  # total raw discovered
    lr_matched_jobs  = [j for j in last_run_jobs
                            if j.get("score", 0) >= 60 or j.get("status") == "already_applied"]
    lr_matched       = len(lr_matched_jobs)
    # Easy Apply count = matched jobs that actually went through Easy Apply flow (not reclassified to external)
    lr_easy_apply    = len([j for j in lr_matched_jobs if j.get("easy_apply") and j.get("status") not in ("already_applied", "external", "skipped")])
    lr_external      = len([j for j in last_run_jobs if j.get("status") == "external"])
    lr_failed        = len([j for j in last_run_jobs if j.get("status") == "failed"])
    lr_applied       = len([j for j in last_run_jobs if j.get("status") == "applied" and j.get("submission_verified")])
    lr_already       = len([j for j in last_run_jobs if j.get("status") == "already_applied"])
    lr_pending       = len([j for j in last_run_jobs if j.get("status") == "pending"])
    lr_easy_pending  = len([j for j in lr_matched_jobs if j.get("easy_apply") and j.get("status") == "pending"])
    lr_easy_queue    = len([j for j in lr_matched_jobs if j.get("easy_apply") and j.get("status") == "discovered"])
    lr_skipped       = len([j for j in last_run_jobs if j.get("status") == "skipped"])
    lr_filtered      = lr_found - lr_matched  # jobs that didn't match

    # ── Today ────────────────────────────────────────────────────────────────
    today_applied    = sum(1 for j in all_verified  if is_today(j.get("applied_at")))
    today_failed     = sum(1 for j in all_failed    if is_today(j.get("discovered_at")))
    today_scanned    = sum(1 for j in items          if is_today(j.get("discovered_at")))
    today_matched    = sum(1 for j in items          if is_today(j.get("discovered_at")) and (j.get("score", 0) >= 60 or j.get("status") == "already_applied"))
    today_external   = sum(1 for j in all_external   if is_today(j.get("discovered_at")))

    # ── This week ────────────────────────────────────────────────────────────
    week_applied     = sum(1 for j in all_verified  if is_this_week(j.get("applied_at")))

    return {
        # ── last-run section ─────────────────────────────────────────────
        "last_run_id":          last_run_id,
        "last_run_found":       lr_found,
        "last_run_matched":     lr_matched,
        "last_run_filtered":    lr_filtered,
        "last_run_easy_apply":  lr_easy_apply,
        "last_run_external":    lr_external,
        "last_run_failed":      lr_failed,
        "last_run_applied":     lr_applied,
        "last_run_already":     lr_already,
        "last_run_pending":     lr_pending,
        "last_run_easy_pending": lr_easy_pending,
        "last_run_easy_queue":   lr_easy_queue,
        "last_run_skipped":     lr_skipped,

        # ── live search counters (update during scanning) ────────────────
        "live_matched":         s["automation"].get("live_matched", 0),
        "live_easy_apply":      s["automation"].get("live_easy_apply", 0),
        "live_found":           s["automation"].get("live_found", 0),

        # ── today section ────────────────────────────────────────────────
        "today_matched":        today_matched,
        "today_scanned":        today_scanned,
        "today_applied":        today_applied,
        "today_failed":         today_failed,
        "today_external":       today_external,

        # ── all-time ─────────────────────────────────────────────────────
        "total_all_time":       len(items),
        "auto_applied":         len(all_verified),
        "applied_this_week":    week_applied,
        "already_applied":      len(all_already_applied),
        "external_jobs":        len(all_external),
        "apply_failed":         len(all_failed),
        "pending":              len(all_pending),
        "pending_questions":    len(pending_questions),
        "pending_verify":       len(pending_verify),

        # ── rate-limit counters (no caps — unlimited) ────────────────────
        "today_count":          s["automation"].get("today_count", 0),
        "hour_count":           s["automation"].get("hour_count", 0),

        # ── setup flags ──────────────────────────────────────────────────
        "cv_uploaded":          bool(s["cv"].get("filename")),
        "preferences_ready":    bool(s["preferences"].get("ready")),

        # ── legacy keys kept for any other consumer ───────────────────────
        "jobs_found":           lr_matched,  # primary number = matched jobs
        "verified_applied":     len(all_verified),
        "applied_today":        today_applied,
        "total_applied_today":  today_applied,
    }
