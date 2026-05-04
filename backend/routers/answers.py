"""
Answer Memory — Q&A bank used to auto-fill recurring application questions.
"""
import time
from fastapi import APIRouter
from pydantic import BaseModel
from backend import state

router = APIRouter(prefix="/answers", tags=["answers"])


class AnswerIn(BaseModel):
    question: str
    answer: str


@router.get("/")
def get_all():
    return state.get()["answers"]


@router.post("/")
def save(body: AnswerIn):
    def m(st):
        existing = next((a for a in st["answers"]
                         if a["question"].lower() == body.question.lower()), None)
        if existing:
            existing["answer"] = body.answer
        else:
            # Use max existing id + 1 to avoid ID collisions after deletes
            next_id = max((a.get("id") or 0 for a in st["answers"]), default=0) + 1
            st["answers"].append({
                "id": next_id,
                "question": body.question,
                "answer": body.answer,
                "created_at": time.time(),
            })
    state.update(m)
    return {"success": True}


@router.delete("/{answer_id}")
def delete(answer_id: int):
    def m(st):
        st["answers"] = [a for a in st["answers"] if a.get("id") != answer_id]
    state.update(m)
    return {"success": True}
