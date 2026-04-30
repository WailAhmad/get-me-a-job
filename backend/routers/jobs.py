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
    return _by_status("applied")


@router.get("/applications")
def applications():
    return _by_status("applied")


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

    def m(st):
        # save the answer to the Q&A bank for re-use
        if body.save_to_bank and question:
            existing = next((a for a in st["answers"] if a["question"].lower() == question.lower()), None)
            if existing:
                existing["answer"] = body.answer
            else:
                st["answers"].append({
                    "id": len(st["answers"]) + 1,
                    "question": question,
                    "answer": body.answer,
                    "created_at": time.time(),
                })
        # apply the job
        j = st["jobs"]["items"][job_id]
        j["status"] = "applied"
        j["applied_at"] = time.time()
        j.pop("pending_question", None)
        if job_id not in st["applied_ids"]:
            st["applied_ids"].append(job_id)
    state.update(m)
    state.push_log("success", f"✅ Answered & applied to '{job['title']}' at {job['company']}.")
    return {"success": True}


@router.delete("/{job_id}")
def dismiss_job(job_id: str):
    def m(st):
        st["jobs"]["items"].pop(job_id, None)
    state.update(m)
    return {"success": True}
