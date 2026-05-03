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

# Skill labels and strict regexes. Avoid raw substring checks: "ai" inside
# Bahrain or "scala" inside escalation must never become a detected skill.
SKILL_PATTERNS = [
    ("Python", r"\bpython\b"),
    ("SQL", r"\bsql\b"),
    ("FastAPI", r"\bfastapi\b"),
    ("React", r"\breact(?:\.js|js)?\b"),
    ("Tableau", r"\btableau\b"),
    ("Power BI", r"\bpower\s*bi\b"),
    ("Snowflake", r"\bsnowflake\b"),
    ("Spark", r"\bspark\b"),
    ("Databricks", r"\bdatabricks\b"),
    ("TensorFlow", r"\btensorflow\b"),
    ("PyTorch", r"\bpytorch\b"),
    ("LLM", r"\bllms?\b|\blarge language models?\b"),
    ("Machine Learning", r"\bmachine learning\b"),
    ("Data Science", r"\bdata science\b"),
    ("Analytics", r"\banalytics?\b|\banalyst\b|\banalysis\b"),
    ("Leadership", r"\bleadership\b"),
    ("Strategy", r"\bstrategy\b|\bstrategic\b"),
    ("FinTech", r"\bfintech\b"),
    ("Banking", r"\bbanking\b|\bbank\b"),
    ("Consulting", r"\bconsulting\b|\bconsultant\b"),
    ("Kubernetes", r"\bkubernetes\b|\bk8s\b"),
    ("AWS", r"\baws\b|amazon web services"),
    ("Azure", r"\bazure\b"),
    ("GCP", r"\bgcp\b|google cloud"),
    ("Product Management", r"\bproduct management\b"),
    ("AI", r"\bai\b|\bartificial intelligence\b"),
    ("NLP", r"\bnlp\b|\bnatural language processing\b"),
    ("ETL", r"\betl\b"),
    ("Airflow", r"\bairflow\b"),
    ("Looker", r"\blooker\b"),
    ("Deep Learning", r"\bdeep learning\b"),
    ("Computer Vision", r"\bcomputer vision\b"),
    ("Docker", r"\bdocker\b"),
    ("Java", r"\bjava\b"),
    ("JavaScript", r"\bjavascript\b|\bjs\b"),
    ("C++", r"\bc\+\+\b"),
    ("R", r"\br programming\b|\br language\b|\bcran\b|\brstudio\b"),
    ("Scala", r"\bscala\b"),
    ("Agile", r"\bagile\b"),
    ("Scrum", r"\bscrum\b"),
    ("Stakeholder Management", r"\bstakeholder management\b|\bstakeholder engagement\b"),
    ("Governance", r"\bgovernance\b"),
    ("Digital Transformation", r"\bdigital transformation\b"),
    ("Cloud", r"\bcloud\b"),
    ("DevOps", r"\bdevops\b|\bci/cd\b"),
    ("Billing", r"\bbilling\b|\binvoicing\b|\binvoice\b"),
    ("Accounts Receivable", r"\baccounts receivable\b|\bar\b"),
    ("Revenue Cycle", r"\brevenue cycle\b|\brevenue assurance\b"),
    ("Collections", r"\bcollections?\b|\bpayment follow[- ]?up\b"),
    ("ERP", r"\berp\b|\boracle\b|\bsap\b"),
    ("Excel", r"\bexcel\b|\bpivot tables?\b|\bvlookup\b"),
    ("Reconciliation", r"\breconciliation\b|\breconcile\b"),
    ("Customer Service", r"\bcustomer service\b|\bcustomer support\b"),
]

SENIORITY_PATTERNS = [
    (r"\b(chief|c-level|cto|cdo|cio|coo|ceo)\b", "C-Level Executive"),
    (r"\b(vice president|vp)\b", "Vice President"),
    (r"\b(director|head of|head,)\b", "Director / Head"),
    (r"\b(senior manager|sr\. manager)\b", "Senior Manager"),
    (r"\b(manager|lead|principal)\b", "Manager / Lead"),
    (r"\b(senior|sr\.)\b", "Senior"),
    (r"\b(architect)\b", "Architect"),
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


def _extract_contact(text: str) -> dict:
    """Extract email, phone, and location from CV text."""
    contact = {}

    # Email
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    if email_match:
        contact["email"] = email_match.group(0)

    # Phone (international and local formats)
    phone_match = re.search(r"(?:\+?\d{1,4}[\s-]?)?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}", text)
    if phone_match:
        raw = phone_match.group(0).strip()
        if len(re.sub(r"\D", "", raw)) >= 7:
            contact["phone"] = raw

    # Location — look for common patterns
    loc_match = re.search(
        r"(?:located?\s+(?:in|at)|address|city|based\s+in)[:\s]+([A-Z][a-zA-Z\s,]+)",
        text, re.IGNORECASE
    )
    if loc_match:
        contact["location"] = loc_match.group(1).strip()[:60]
    else:
        # Try to find city/country patterns near top of CV
        top_text = text[:600]
        for city in ["Manama", "Bahrain", "Dubai", "Abu Dhabi", "Riyadh", "Doha", "London", "Munich"]:
            if city in top_text:
                contact["location"] = city
                break

    return contact


def _extract_name(text: str) -> str:
    """Best-effort candidate name from the top of the CV."""
    for line in text.splitlines()[:12]:
        clean = re.sub(r"\s+", " ", line).strip()
        if not clean:
            continue
        lower = clean.lower()
        if "@" in clean or any(tok in lower for tok in ("cv", "resume", "phone", "email", "linkedin")):
            continue
        if len(clean) <= 60 and re.match(r"^[A-Za-z][A-Za-z .'-]+$", clean) and len(clean.split()) >= 2:
            return clean
    return ""


def _extract_linkedin(text: str) -> dict:
    """Extract LinkedIn URL when present, plus visible label/handle when only text exists."""
    # Full URL, allowing PDF extraction to insert spaces before punctuation.
    url_match = re.search(
        r"https?://(?:www\.)?linkedin\.com/(?:in|pub|company)/[A-Za-z0-9_.%-]+/?",
        text,
        re.IGNORECASE,
    )
    if url_match:
        url = re.sub(r"\s+", "", url_match.group(0)).rstrip("/.,;")
        return {"url": url, "label": url}

    # Label-only forms, e.g. "LinkedIn: Hend. Khaled".
    label_match = re.search(
        r"(?:linkedin|linked\s*in)\s*[:\-]\s*([^\n\r|•]+)",
        text,
        re.IGNORECASE,
    )
    if label_match:
        label = label_match.group(1).strip()
        label = re.split(r"\s{2,}|📍|location|email|phone|☎|✉", label, flags=re.IGNORECASE)[0].strip(" -–—|,;")
        if label and not re.search(r"^https?://", label, re.IGNORECASE):
            return {"url": "", "label": label}

    return {"url": "", "label": ""}


def _detect_seniority(text: str) -> str:
    """Detect seniority level from the CV header area (first 500 chars)."""
    # Only check the top of the CV (name/title/headline area)
    # to avoid matching 'chief' etc. from job descriptions deeper in the text
    header = text[:500].lower()
    for pattern, label in SENIORITY_PATTERNS:
        if re.search(pattern, header):
            return label
    # Fallback: check full text but skip C-level (too easy to false-positive)
    lower = text.lower()
    for pattern, label in SENIORITY_PATTERNS:
        if label == "C-Level Executive":
            continue  # skip C-level in full-text scan
        if re.search(pattern, lower):
            return label
    return "Professional"


def _extract_experience_items(text: str) -> list:
    """Extract key experience/role mentions from CV."""
    items = []
    # Look for role-like patterns: "Title at Company" or "Title, Company"
    role_patterns = [
        r"((?:Head|Director|VP|Chief|Manager|Lead|Senior|Architect|Consultant)[^\n]{5,60})(?:\s*(?:at|[-–]|,)\s*)([A-Z][^\n]{3,40})",
    ]
    for pat in role_patterns:
        for m in re.finditer(pat, text):
            title = m.group(1).strip()
            company = m.group(2).strip().rstrip(".,;")
            if len(title) < 80 and len(company) < 50:
                items.append({"title": title, "company": company})
            if len(items) >= 5:
                break
        if items:
            break
    return items


def _summarise(text: str, filename: str) -> dict:
    lower = text.lower()
    found = []
    for label, pattern in SKILL_PATTERNS:
        if re.search(pattern, lower, re.IGNORECASE) and label not in found:
            found.append(label)

    # ── Years of experience: multi-strategy ──
    years = 0

    # Strategy 1: Explicit "X+ years" / "X years" mentions — pick the LARGEST
    explicit_years = 0
    for m in re.finditer(r"(\d{1,2})\+?\s*years?", lower):
        try:
            y = int(m.group(1))
            explicit_years = max(explicit_years, y)
        except Exception:
            pass

    # Strategy 2: Calculate from date ranges (2005–Present = 21 years)
    # Only used as fallback when no explicit years mention found
    date_span = 0
    date_years = []
    for m in re.finditer(
            r"(20\d{2}|19\d{2})\s*[-–—]\s*(20\d{2}|19\d{2}|[Pp]resent|[Cc]urrent|[Tt]oday|[Nn]ow)",
            text):
        start_year = int(m.group(1))
        end_str = m.group(2).lower()
        end_year = 2026 if end_str in ("present", "current", "today", "now") else int(end_str)
        # Skip future dates
        if end_year > 2027:
            continue
        date_years.append((start_year, end_year))

    if date_years:
        earliest = min(d[0] for d in date_years)
        latest = min(2026, max(d[1] for d in date_years))
        date_span = latest - earliest

    # Prefer explicit mention; use date span only as fallback
    if explicit_years:
        years = explicit_years
    elif date_span:
        years = date_span
    else:
        years = 0

    # ── Education ──
    education = []
    edu_patterns = [
        (r"\b(ph\.?d|phd|doctor(?:ate)?)\b", "PhD"),
        (r"\b(m\.?sc|msc|master(?:'?s)?|m\.?a\b|mba)\b", "Master's"),
        (r"\b(b\.?sc|bsc|bachelor(?:'?s)?|b\.?a\b|b\.?eng)\b", "Bachelor's"),
    ]
    for pattern, label in edu_patterns:
        if re.search(pattern, lower):
            education.append(label)

    # ── LinkedIn ──
    linkedin = _extract_linkedin(text)
    linkedin_url = linkedin["url"]
    linkedin_label = linkedin["label"]

    # ── Summary text ──
    # Try to find "Summary" section, else use first 600 chars
    summary_match = re.search(
        r"(?:summary|profile|about|objective)[^\n]*\n(.{50,800}?)(?:\n\s*\n|\n[A-Z])",
        text, re.IGNORECASE | re.DOTALL)
    if summary_match:
        summary = summary_match.group(1).strip()
    else:
        summary = (text[:600].strip() + "…") if len(text) > 600 else (text.strip() or
            f"Imported {filename}. We'll use your skills and experience to match jobs semantically.")

    contact = _extract_contact(text)
    candidate_name = _extract_name(text)
    if linkedin_url:
        contact["linkedin"] = linkedin_url
    if linkedin_label:
        contact["linkedin_label"] = linkedin_label
    seniority = _detect_seniority(text)
    experience = _extract_experience_items(text)

    # ── ATS Score (estimated) ──
    # Based on: skills count, contact completeness, summary present, education, experience items
    ats_score = 30  # base
    ats_score += min(25, len(found) * 2)         # skills: up to 25
    ats_score += 10 if contact.get("email") else 0
    ats_score += 5 if contact.get("phone") else 0
    ats_score += 5 if contact.get("location") else 0
    ats_score += 5 if linkedin_url else 0
    ats_score += 10 if education else 0
    ats_score += 5 if experience else 0
    ats_score += 5 if years >= 10 else 0
    ats_score = min(98, ats_score)
    ats_hints = []
    if len(found) < 8:
        ats_hints.append("Add a dedicated Skills section with 8-12 role-specific tools and competencies.")
    if not linkedin_url:
        if linkedin_label:
            ats_hints.append("LinkedIn name detected, but add the full LinkedIn URL so recruiters and forms can open it.")
        else:
            ats_hints.append("Add a LinkedIn profile URL.")
    if not experience:
        ats_hints.append("Use clear role headings with company names and dates.")
    if not education:
        ats_hints.append("Add education/qualification details.")
    if years < 1:
        ats_hints.append("Add an explicit years-of-experience statement.")
    has_ai_data_focus = any(skill in found for skill in (
        "AI", "LLM", "Machine Learning", "Data Science", "Databricks",
        "Governance", "Digital Transformation", "Cloud", "AWS", "Azure"
    ))
    has_billing_focus = any(skill in found for skill in (
        "Billing", "Accounts Receivable", "Collections", "Revenue Cycle", "Reconciliation"
    ))
    has_metrics = re.search(
        r"\b(increased|reduced|improved|saved|processed|managed|reconciled|collected|delivered|led|launched|built|designed|implemented)\b.{0,120}\b\d+[%\d]?",
        lower,
    )
    if not has_metrics:
        if has_billing_focus:
            ats_hints.append("Add measurable achievements, for example invoice volume, collection rate, or error reduction.")
        elif has_ai_data_focus:
            ats_hints.append("Add measurable AI/data achievements, for example platform scale, revenue impact, cost reduction, adoption, latency, or governance coverage.")
        else:
            ats_hints.append("Add measurable achievements with numbers, impact, scope, or volume.")
    if not ats_hints:
        if has_billing_focus:
            ats_hints.append("Good baseline. Improve further by adding more quantified achievements and exact billing/ERP tools.")
        elif has_ai_data_focus:
            ats_hints.append("Good baseline. Improve further by adding more quantified AI/data outcomes and exact platform/tool names.")
        else:
            ats_hints.append("Good baseline. Improve further by adding more quantified outcomes and exact tools.")

    return {
        "name": candidate_name,
        "skills": found[:25],
        "years": years,
        "summary": summary,
        "seniority": seniority,
        "contact": contact,
        "experience": experience,
        "education": education,
        "linkedin": linkedin_url,
        "linkedin_label": linkedin_label,
        "ats_score": ats_score,
        "ats_hints": ats_hints,
        "full_text": text,  # store for AI RAG context
    }


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

    # Also save the text version for other services
    text_path = UPLOAD_DIR / "cv.txt"
    text_path.write_text(text, errors="ignore")

    def m(s):
        # Exclude full_text from state — it's already saved as cv.txt
        # and would bloat the JSON state file
        state_summary = {k: v for k, v in summary.items() if k != "full_text"}
        s["cv"] = {
            "filename": safe_name,
            "uploaded_at": time.time(),
            **state_summary,
        }
        # A new CV means a new candidate/search context. Clear stale roles,
        # jobs, and chat so Wael's previous AI/Data preferences do not bleed in.
        s["preferences"] = {"ready": False, "country": None, "city": None,
                            "countries": [], "locations": [], "roles": [],
                            "recency_days": None, "industries": []}
        s["chat"] = {"step": "greet", "history": []}
        s["jobs"]["items"] = {}
        s["applied_ids"] = []
        s["automation"]["today_count"] = 0
        s["automation"]["hour_count"] = 0
        s["automation"]["live_matched"] = 0
        s["automation"]["live_easy_apply"] = 0
        s["automation"]["live_found"] = 0
        s["automation"]["current_run_id"] = None
    state.update(m)

    cv_data = state.get()["cv"]
    return {
        "success": True,
        "message": f"CV uploaded — found {len(summary['skills'])} skills · {summary['years']} years experience.",
        "cv": {"uploaded": True, **cv_data},
    }


@router.delete("/")
def clear_cv():
    def m(s):
        s["cv"] = {"filename": None, "uploaded_at": None, "skills": [], "years": 0, "summary": None,
                    "seniority": None, "contact": {}, "experience": []}
    state.update(m)
    return {"success": True}
