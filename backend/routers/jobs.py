"""
Jobs router — read-side endpoints over the shared state store.
"""
import time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend import state

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _items() -> list[dict]:
    return [_normalize_job(j) for j in state.get()["jobs"]["items"].values()]


def _looks_like_generated_url(job: dict) -> bool:
    source_id = job.get("source_id")
    jid = str(job.get("id") or "")
    url = job.get("url") or ""
    if source_id == "linkedin" and "linkedin.com/jobs/view/" in url and len(jid) < 10:
        return True
    # `simulated` is the legacy marker for jobs that should not claim verification.
    # `demo` jobs go through the in-app demo flow and are allowed to keep the
    # url_verified flag set by the engine.
    return bool(job.get("source_mode") == "simulated")


def _normalize_job(job: dict) -> dict:
    item = dict(job)
    item.setdefault("source", "LinkedIn")
    item.setdefault("source_id", "linkedin")
    item.setdefault("apply_type", "Easy Apply" if item.get("easy_apply") else "External Apply")
    item["url_verified"] = bool(item.get("url_verified")) and not _looks_like_generated_url(item)
    item["submission_verified"] = bool(item.get("submission_verified"))
    if _looks_like_generated_url(item):
        item["url_warning"] = "This is a locally generated placeholder URL, not a verified job posting."
    return item


def _by_status(status: str) -> list[dict]:
    return sorted(
        [j for j in _items() if j.get("status") == status],
        key=lambda j: (j.get("applied_at") or j.get("discovered_at") or 0, j.get("score", 0)),
        reverse=True,
    )


@router.get("/")
def list_jobs():
    items = _items()
    items.sort(key=lambda j: (j.get("discovered_at") or 0, j.get("score", 0)), reverse=True)
    return items


@router.get("/applied")
def applied():
    items = [j for j in _items() if j.get("status") in ("applied", "already_applied")]
    items.sort(
        key=lambda j: (j.get("applied_at") or j.get("discovered_at") or 0, j.get("score", 0)),
        reverse=True,
    )
    return items


@router.get("/applications")
def applications():
    return applied()


@router.get("/pending")
def pending():
    return _by_status("pending")


@router.get("/external")
def external():
    # external = non-easy-apply matches, ranked by score then recency
    items = [j for j in _items() if j.get("status") == "external"]
    items.sort(key=lambda j: (j.get("score", 0), -(j.get("posted_days_ago") or 99)), reverse=True)
    return items


@router.get("/skipped")
def skipped():
    return _by_status("skipped")


class AnswerIn(BaseModel):
    answer: str
    save_to_bank: bool = True


@router.post("/{job_id}/answer")
def answer_pending(job_id: str, body: AnswerIn):
    s = state.get()
    job = s["jobs"]["items"].get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("status") != "pending":
        raise HTTPException(400, "Job is not pending")
    if job.get("pending_kind") == "verify_source" or not _normalize_job(job).get("url_verified"):
        raise HTTPException(400, "This job does not have a verified live source URL yet, so it cannot be marked as applied.")
    question = job.get("pending_question") or ""

    def save_answer(st):
        if body.save_to_bank and question:
            existing = next((a for a in st["answers"] if a["question"].lower() == question.lower()), None)
            if existing:
                existing["answer"] = body.answer
            else:
                next_id = max((a.get("id") or 0 for a in st["answers"]), default=0) + 1
                st["answers"].append({
                    "id": next_id,
                    "question": question,
                    "answer": body.answer,
                    "created_at": time.time(),
                })
    state.update(save_answer)

    # Retry the real LinkedIn Easy Apply flow. Do not mark the job applied unless
    # LinkedIn submission is verified by the applier.
    try:
        from backend.routers.automation import _live_apply_easy, _is_infrastructure_apply_error
        result = _live_apply_easy(job)
    except Exception as exc:
        result = {"status": "error", "error": str(exc), "pending_question": None}

    status = result.get("status")
    if status == "submitted":
        def mark_applied(st):
            j = st["jobs"]["items"][job_id]
            j["status"] = "applied"
            j["applied_at"] = time.time()
            j["submission_verified"] = True
            j.pop("pending_question", None)
            j.pop("pending_kind", None)
            if job_id not in st["applied_ids"]:
                st["applied_ids"].append(job_id)
        state.update(mark_applied)
        state.push_log("success", f"✅ Answered & submitted application to '{job['title']}' at {job['company']}.")
        return {"success": True, "status": "submitted"}

    if status == "not_easy_apply":
        def mark_external(st):
            j = st["jobs"]["items"][job_id]
            j["easy_apply"] = False
            j["status"] = "external"
            j.pop("pending_question", None)
            j.pop("pending_kind", None)
        state.update(mark_external)
        state.push_log("external", f"🌐 '{job['title']}' at {job['company']} is not Easy Apply after retry — moved to External.")
        return {"success": False, "status": "external", "message": "Job is no longer Easy Apply."}

    err = result.get("error") or ""
    pending_question = result.get("pending_question") or err or "Easy Apply still needs review"
    if status == "pending" or not _is_infrastructure_apply_error(err):
        def keep_pending(st):
            j = st["jobs"]["items"][job_id]
            j["status"] = "pending"
            j["pending_question"] = pending_question
            j["pending_kind"] = "answer"
            j["error"] = None
        state.update(keep_pending)
        state.push_log("pending", f"⏸️ '{job['title']}' at {job['company']} still needs review: \"{pending_question}\".")
        return {"success": False, "status": "pending", "message": pending_question}

    def mark_failed(st):
        j = st["jobs"]["items"][job_id]
        j["status"] = "failed"
        j["error"] = err
    state.update(mark_failed)
    state.push_log("warn", f"⚠️ Retry failed for '{job['title']}' at {job['company']}: {err}")
    return {"success": False, "status": "failed", "message": err}


@router.delete("/{job_id}")
def dismiss_job(job_id: str):
    def m(st):
        st["jobs"]["items"].pop(job_id, None)
    state.update(m)
    return {"success": True}
