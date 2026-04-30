from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass


AI_SKILLS = ["AI strategy", "GenAI", "LLM", "RAG", "agentic AI", "machine learning", "NLP", "responsible AI"]
DATA_SKILLS = ["data engineering", "analytics", "ETL", "data warehouse", "lakehouse", "BI", "streaming"]
ARCH_SKILLS = ["data architecture", "enterprise architecture", "solution architecture", "platform architecture"]
CLOUD = ["Azure", "AWS", "GCP", "Databricks", "Synapse", "Snowflake", "Microsoft Fabric"]
GOVERNANCE = ["Collibra", "Purview", "data governance", "catalog", "lineage", "MDM", "risk", "compliance"]
INDUSTRIES = ["government", "public sector", "telecom", "banking", "financial services", "insurance", "law enforcement", "technology"]


@dataclass
class ParsedCv:
    text: str
    profile: dict


def extract_text_from_upload(filename: str, content: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".docx"):
        from docx import Document

        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if lower.endswith(".pdf"):
        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    raise ValueError("Upload a .docx or .pdf CV")


def parse_cv_text(text: str, filename: str = "") -> ParsedCv:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    email = _first_match(r"[\w.+-]+@[\w.-]+\.\w+", text)
    linkedin = _first_match(r"https?://(?:www\.)?linkedin\.com/[^\s)]+", text)
    years = _years_experience(text)
    full_name = _guess_name(lines)
    current_title, current_company = _guess_current_role(lines)
    profile = {
        "cv_filename": filename,
        "full_name": full_name,
        "current_title": current_title,
        "current_company": current_company,
        "location": _guess_location(text),
        "email": email,
        "linkedin_url": linkedin,
        "nationality": _line_after_label(lines, ["nationality", "citizenship"]),
        "years_experience": years,
        "employers": _extract_employers(lines),
        "industries": _contains(INDUSTRIES, text),
        "ai_skills": _contains(AI_SKILLS, text),
        "data_engineering_skills": _contains(DATA_SKILLS, text),
        "data_architecture_skills": _contains(ARCH_SKILLS, text),
        "cloud_platforms": _contains(CLOUD, text),
        "governance_tools": _contains(GOVERNANCE, text),
        "leadership_experience": _leadership(lines, text),
        "education": _section_lines(lines, ["education", "academic"], ["certification", "experience", "employment"]),
        "certifications": _section_lines(lines, ["certification", "certifications"], ["education", "experience", "employment"]),
        "major_achievements": _achievements(lines),
        "cv_text_preview": text[:6000],
    }
    return ParsedCv(text=text, profile=profile)


def apply_parsed_profile(candidate, parsed: ParsedCv):
    profile = parsed.profile
    candidate.full_name = profile.get("full_name") or candidate.full_name
    candidate.current_title = profile.get("current_title") or candidate.current_title
    candidate.current_company = profile.get("current_company") or candidate.current_company
    candidate.location = profile.get("location") or candidate.location
    candidate.email = profile.get("email") or candidate.email
    candidate.linkedin_url = profile.get("linkedin_url") or candidate.linkedin_url
    candidate.nationality = profile.get("nationality") or candidate.nationality
    candidate.years_experience = profile.get("years_experience") or candidate.years_experience
    candidate.summary = _summary(parsed.text)
    candidate.core_skills_json = json.dumps(sorted(set(profile["ai_skills"] + profile["data_engineering_skills"] + profile["data_architecture_skills"] + profile["cloud_platforms"] + profile["governance_tools"])))
    candidate.ai_experience_json = json.dumps(profile["ai_skills"])
    candidate.data_experience_json = json.dumps(profile["data_engineering_skills"] + profile["data_architecture_skills"])
    candidate.cloud_platforms_json = json.dumps(profile["cloud_platforms"])
    candidate.governance_tools_json = json.dumps(profile["governance_tools"])
    candidate.industries_json = json.dumps(profile["industries"])
    candidate.employers_json = json.dumps(profile["employers"])
    candidate.education_json = json.dumps(profile["education"])
    candidate.certifications_json = json.dumps(profile["certifications"])
    candidate.major_achievements_json = json.dumps(profile["major_achievements"])
    candidate.profile_json = json.dumps(profile)
    return candidate


def _first_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.I)
    return match.group(0).strip(".,;") if match else ""


def _guess_name(lines: list[str]) -> str:
    for line in lines[:8]:
        if "@" in line or "linkedin" in line.lower() or len(line) > 80:
            continue
        if len(line.split()) in {2, 3, 4} and not any(ch.isdigit() for ch in line):
            return line
    return ""


def _guess_current_role(lines: list[str]) -> tuple[str, str]:
    for line in lines[:20]:
        lower = line.lower()
        if any(term in lower for term in ["head", "director", "architect", "lead", "manager", "consultant"]):
            parts = re.split(r"\s+(?:at|@|-|–|—)\s+", line, maxsplit=1)
            if len(parts) == 2:
                return parts[0].strip(), parts[1].strip()
            return line[:200], ""
    return "", ""


def _guess_location(text: str) -> str:
    for item in ["Bahrain", "Saudi Arabia", "UAE", "Qatar", "Kuwait", "Oman", "Ireland", "Dubai", "Abu Dhabi", "Riyadh", "Doha", "Manama"]:
        if re.search(rf"\b{re.escape(item)}\b", text, re.I):
            return item
    return ""


def _years_experience(text: str) -> int:
    matches = [int(v) for v in re.findall(r"(\d{1,2})\+?\s*(?:years|yrs)", text, flags=re.I)]
    return max(matches) if matches else 0


def _contains(terms: list[str], text: str) -> list[str]:
    return [term for term in terms if re.search(rf"\b{re.escape(term)}\b", text, re.I)]


def _line_after_label(lines: list[str], labels: list[str]) -> str:
    for line in lines:
        lower = line.lower()
        if any(label in lower for label in labels):
            return re.sub(r"^[^:]+:\s*", "", line).strip()
    return ""


def _section_lines(lines: list[str], starts: list[str], stops: list[str]) -> list[str]:
    capture = False
    out: list[str] = []
    for line in lines:
        lower = line.lower()
        if any(s in lower for s in starts):
            capture = True
            continue
        if capture and any(s in lower for s in stops):
            break
        if capture and len(out) < 8:
            out.append(line)
    return out


def _extract_employers(lines: list[str]) -> list[str]:
    employers: list[str] = []
    for line in lines:
        if re.search(r"\b(20\d{2}|19\d{2}|present|current)\b", line, re.I) and len(line) < 160:
            employers.append(line)
    return employers[:12]


def _leadership(lines: list[str], text: str) -> list[str]:
    items = [line for line in lines if re.search(r"\b(led|lead|managed|director|head|strategy|stakeholder|executive)\b", line, re.I)]
    if not items and re.search(r"\b(led|managed|leadership)\b", text, re.I):
        items = ["Leadership experience detected from CV text."]
    return items[:10]


def _achievements(lines: list[str]) -> list[str]:
    return [line for line in lines if re.search(r"\b(delivered|launched|built|reduced|increased|saved|improved|transformed|achieved)\b", line, re.I)][:10]


def _summary(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(sentences[:3])[:1200]

