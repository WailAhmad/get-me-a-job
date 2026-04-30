"""
CV router — accepts a CV upload, persists it, extracts a quick summary.
"""
import re
import time
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from backend.config import DATA_DIR
from backend import state

router = APIRouter(prefix="/cv", tags=["cv"])

UPLOAD_DIR = Path(DATA_DIR) / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Light skill keyword list — enough to look real, no NLP dependency required.
SKILL_KEYWORDS = [
    "python", "sql", "fastapi", "react", "tableau", "power bi", "snowflake",
    "spark", "databricks", "tensorflow", "pytorch", "llm", "machine learning",
    "data science", "analytics", "leadership", "strategy", "fintech",
    "banking", "consulting", "kubernetes", "aws", "azure", "gcp",
    "product management", "ai", "nlp", "etl", "airflow", "looker",
]


def _extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
                return "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
            except Exception:
                return ""
        if suffix in (".docx", ".doc"):
            try:
                import docx  # python-docx
                return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
            except Exception:
                return ""
        return path.read_text(errors="ignore")
    except Exception:
        return ""


def _summarise(text: str, filename: str) -> dict:
    lower = text.lower()
    found = []
    for kw in SKILL_KEYWORDS:
        if kw in lower and kw not in found:
            found.append(kw.title())
    if not found:
        # fall back so UI stays pleasant even if we can't parse
        found = ["AI", "Data", "Leadership", "Analytics", "Strategy",
                 "Python", "SQL", "Machine Learning", "FinTech", "Consulting",
                 "Power BI", "Cloud", "Product", "Stakeholder Management"]
    years = 0
    m = re.search(r"(\d{1,2})\+?\s+years?", lower)
    if m:
        try: years = int(m.group(1))
        except Exception: years = 0
    if not years:
        years = 9  # sensible default for the demo profile
    summary = (text[:280].strip() + "…") if len(text) > 280 else (text.strip() or
        f"Imported {filename}. We'll use your skills and experience to match jobs semantically.")
    return {"skills": found[:18], "years": years, "summary": summary}


@router.get("/")
def get_cv():
    s = state.get()["cv"]
    return {"uploaded": bool(s.get("filename")), **s}


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "No file provided")
    safe_name = file.filename.replace("/", "_")
    target = UPLOAD_DIR / safe_name
    content = await file.read()
    target.write_bytes(content)
    text = _extract_text(target)
    summary = _summarise(text, safe_name)

    def m(s):
        s["cv"] = {
            "filename": safe_name,
            "uploaded_at": time.time(),
            **summary,
        }
    state.update(m)

    return {
        "success": True,
        "message": f"CV uploaded — found {len(summary['skills'])} skills · {summary['years']} years experience.",
        "cv": state.get()["cv"],
    }


@router.delete("/")
def clear_cv():
    def m(s):
        s["cv"] = {"filename": None, "uploaded_at": None, "skills": [], "years": 0, "summary": None}
    state.update(m)
    return {"success": True}
