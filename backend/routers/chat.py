"""
Chat router — guided AI assistant for capturing search preferences.

Flow:
  greet → country → recency → roles → confirm → ready

When the conversation reaches `ready`, preferences are committed to state
and the UI surfaces a "Run Automation" call-to-action.
"""
import json
import re
import time
import logging
from typing import Optional, List, Tuple
from fastapi import APIRouter
from pydantic import BaseModel
from backend import state
from backend.config import AI_API_KEY, AI_BASE_URL, AI_MODEL, AI_PROVIDER

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


class ChatIn(BaseModel):
    message: Optional[str] = None
    reset: bool = False


GCC_COUNTRIES = ["UAE", "Saudi Arabia", "Qatar", "Kuwait", "Bahrain", "Oman"]
EUROPE_COUNTRIES = [
    "United Kingdom", "Ireland", "Germany", "Netherlands", "France", "Spain",
    "Italy", "Switzerland", "Sweden", "Denmark", "Belgium", "Poland",
]
COUNTRIES = [
    "GCC", "Europe", "UAE", "Saudi Arabia", "Qatar", "Kuwait", "Bahrain", "Oman",
    "Egypt", "Jordan", "United Kingdom", "Ireland", "United States", "Germany",
    "Netherlands", "France", "Spain", "Italy", "Switzerland", "Singapore", "Remote",
]


def _dedupe(seq: List[str]) -> List[str]:
    out = []
    seen = set()
    for item in seq:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _parse_country(text: str) -> Optional[str]:
    payload = _parse_country_payload(text)
    if payload:
        return payload["country"]
    return None


def _parse_country_payload(text: str) -> Optional[dict]:
    t = text.lower()
    groups: List[str] = []
    countries: List[str] = []

    if any(k in t for k in ("gcc", "gulf", "middle east", "mena")):
        groups.append("GCC")
        countries.extend(GCC_COUNTRIES)
    if any(k in t for k in ("europe", "european", "e.u.")) or re.search(r"\beu\b", t):
        groups.append("Europe")
        countries.extend(EUROPE_COUNTRIES)

    map_ = {
        "uae": "UAE", "emirates": "UAE", "dubai": "UAE", "abu dhabi": "UAE",
        "saudi": "Saudi Arabia", "ksa": "Saudi Arabia", "riyadh": "Saudi Arabia", "jeddah": "Saudi Arabia",
        "qatar": "Qatar", "doha": "Qatar",
        "kuwait": "Kuwait", "bahrain": "Bahrain", "oman": "Oman", "muscat": "Oman",
        "egypt": "Egypt", "cairo": "Egypt",
        "jordan": "Jordan", "amman": "Jordan",
        "uk": "United Kingdom", "england": "United Kingdom", "london": "United Kingdom",
        "ireland": "Ireland", "dublin": "Ireland",
        "us ": "United States", "usa": "United States", "america": "United States",
        "germany": "Germany", "berlin": "Germany",
        "netherlands": "Netherlands", "amsterdam": "Netherlands",
        "france": "France", "paris": "France",
        "spain": "Spain", "madrid": "Spain",
        "italy": "Italy", "milan": "Italy", "rome": "Italy",
        "switzerland": "Switzerland", "zurich": "Switzerland",
        "sweden": "Sweden", "stockholm": "Sweden",
        "singapore": "Singapore",
        "remote": "Remote", "anywhere": "Remote",
    }
    for k, v in map_.items():
        if re.search(rf"\b{re.escape(k)}\b", t):
            countries.append(v)

    countries = _dedupe(countries)
    if not countries:
        return None
    label = " + ".join(groups) if groups else countries[0]
    if groups and any(c not in GCC_COUNTRIES + EUROPE_COUNTRIES for c in countries):
        label = label + " + Other"
    return {"country": label, "countries": countries, "locations": countries}


def _country_payload(country: str) -> dict:
    if country == "GCC":
        return {"country": "GCC", "countries": GCC_COUNTRIES, "locations": GCC_COUNTRIES}
    if country == "Europe":
        return {"country": "Europe", "countries": EUROPE_COUNTRIES, "locations": EUROPE_COUNTRIES}
    if country in {"GCC + Europe", "Europe + GCC"}:
        countries = _dedupe(GCC_COUNTRIES + EUROPE_COUNTRIES)
        return {"country": "GCC + Europe", "countries": countries, "locations": countries}
    return {"country": country, "countries": [country], "locations": [country]}


def _parse_recency(text: str) -> Optional[int]:
    t = text.lower()
    if "today" in t or "24 hour" in t or "past day" in t or "1 day" in t:
        return 1
    if "week" in t or "7 day" in t:
        return 7
    if "two week" in t or "14 day" in t:
        return 14
    if "month" in t or "30 day" in t:
        return 30
    m = re.search(r"(\d{1,3})\s*(day|d)", t)
    if m: return min(60, max(1, int(m.group(1))))
    return None


def _recency_prompt(country: str | None = None, roles: List[str] | None = None) -> str:
    scope = f" in **{country}**" if country else ""
    role_note = f" for **{', '.join((roles or [])[:3])}**" if roles else ""
    return (
        f"I have the region{scope} and target roles{role_note}.\n\n"
        "**How far back should I search LinkedIn postings?**\n"
        "Choose one: **today**, **last week**, **last 14 days**, or **last 30 days**."
    )


def _roles_prompt(country: str | None = None, days: int | None = None) -> str:
    nice = {1: "today", 7: "last week", 14: "last 14 days", 30: "last 30 days"}.get(days, f"last {days} days" if days else "")
    bits = []
    if country:
        bits.append(f"region **{country}**")
    if nice:
        bits.append(f"recency **{nice}**")
    context = " and ".join(bits)
    prefix = f"I have {context}.\n\n" if context else ""
    return prefix + "**Which job titles should I target?** You can say **match my CV** or list titles like **Head of Data, AI Director**."


def _missing_preference_followup(prefs_update: dict, current_prefs: dict) -> tuple[str, str] | None:
    merged = {**(current_prefs or {}), **(prefs_update or {})}
    country = merged.get("country")
    days = merged.get("recency_days")
    roles = merged.get("roles") or []
    if country and roles and not days:
        return "recency", _recency_prompt(country, roles)
    if country and days and not roles:
        return "roles", _roles_prompt(country, days)
    if roles and days and not country:
        return "country", "I have the roles and timeframe. **Which region should I search?** Try **GCC**, **Europe**, **UAE**, **Saudi Arabia**, or **Remote**."
    return None


def _region_label(countries: List[str]) -> str:
    countries = _dedupe(countries or [])
    has_gcc = any(c in GCC_COUNTRIES for c in countries)
    has_europe = any(c in EUROPE_COUNTRIES for c in countries)
    extra = [c for c in countries if c not in GCC_COUNTRIES + EUROPE_COUNTRIES]
    if len(countries) == 1:
        return countries[0]
    if has_gcc and has_europe and not extra:
        return "GCC + Europe"
    if has_gcc and not has_europe and not extra and set(countries) == set(GCC_COUNTRIES):
        return "GCC"
    if has_europe and not has_gcc and not extra and set(countries) == set(EUROPE_COUNTRIES):
        return "Europe"
    labels = []
    if has_gcc:
        labels.append("GCC")
    if has_europe:
        labels.append("Europe")
    labels.extend(extra)
    return " + ".join(labels) if labels else "Custom"


def _merge_country_payload(existing: dict, incoming: dict, mode: str) -> dict:
    if mode == "add":
        countries = _dedupe((existing.get("countries") or []) + (incoming.get("countries") or []))
    else:
        countries = incoming.get("countries") or []
    label = _region_label(countries)
    return {"country": label, "countries": countries, "locations": countries}


def _message_mentions_roles(text: str) -> bool:
    t = (text or "").lower()
    role_terms = (
        "role", "roles", "title", "titles", "job", "jobs", "position", "positions",
        "billing", "invoice", "invoicing", "accounts receivable", "finance",
        "data", "ai", "artificial intelligence", "machine learning", "analyst",
        "manager", "director", "head", "chief", "specialist", "engineer",
        "architect", "product", "governance", "transformation"
    )
    return any(term in t for term in role_terms)


def _parse_search_keywords(text: str, cv: dict | None = None) -> List[str]:
    t = (text or "").lower()
    keywords: List[str] = []
    if any(phrase in t for phrase in ("ai & data", "data & ai", "ai and data", "data and ai")):
        keywords.append("AI & Data")
    elif "genai" in t or "generative ai" in t:
        keywords.append("Generative AI")
    elif "machine learning" in t:
        keywords.append("Machine Learning")
    elif "data science" in t:
        keywords.append("Data Science")
    elif "billing analyst" in t:
        keywords.append("Billing Analyst")
    elif "billing" in t and cv and any(term in " ".join(cv.get("skills") or []).lower() for term in ("billing", "invoice", "invoicing")):
        keywords.append("Billing")
    return _dedupe(keywords)


AI_DATA_ROLES = {
    "head of ai", "head of data", "ai director", "chief data officer",
    "ai product", "ai platform", "ai architect", "data governance",
    "digital transformation", "machine learning director",
}


def _cv_role_defaults(cv: dict) -> List[str]:
    blob = " ".join([
        cv.get("summary") or "",
        cv.get("seniority") or "",
        " ".join(cv.get("skills") or []),
    ]).lower()
    if any(term in blob for term in ("billing", "invoice", "invoicing", "accounts receivable", "collections")):
        return [
            "Billing Analyst",
            "Senior Billing Analyst",
            "Billing Specialist",
            "Accounts Receivable Analyst",
            "Invoicing Specialist",
            "Revenue Cycle Analyst",
            "Collections Analyst",
            "Finance Operations Analyst",
        ]
    if any(term in blob for term in ("accounting", "finance", "financial")):
        return ["Finance Analyst", "Accounting Analyst", "Accounts Receivable Analyst", "Billing Analyst"]
    if any(term in blob for term in ("ai", "machine learning", "data governance", "data science", "llm")):
        return [
            "Head of AI",
            "Head of Data",
            "AI Director",
            "Chief Data Officer",
            "AI Product",
            "Data Governance",
            "Digital Transformation",
            "AI Platform",
        ]
    return ["Analyst", "Senior Analyst", "Operations Analyst", "Business Analyst"]


def _cv_supports_ai_data(cv: dict) -> bool:
    skills = {str(s).lower() for s in (cv.get("skills") or [])}
    blob = " ".join([cv.get("summary") or "", " ".join(skills)]).lower()
    if skills & {"ai", "machine learning", "data science", "data governance", "llm", "scala", "databricks"}:
        return True
    return any(term in blob for term in (
        " ai ", "artificial intelligence", "machine learning", "data science",
        "data governance", "llm", "python", "scala", "databricks"
    ))


def _sanitize_roles(roles: List[str], cv: dict, user_msg: str = "") -> List[str]:
    explicit_ai = any(term in (user_msg or "").lower() for term in (
        " ai ", "artificial intelligence", "machine learning", "data science", "data governance"
    ))
    if _cv_supports_ai_data(cv) or explicit_ai:
        return roles[:8]
    cleaned = [r for r in roles if r.strip().lower() not in AI_DATA_ROLES and not r.strip().lower().startswith("ai ")]
    return cleaned[:8] or _cv_role_defaults(cv)


def _parse_roles(text: str, cv: dict | None = None) -> List[str]:
    t = text.lower()
    cv = cv or {}

    # Catch broad domain-level requests
    domain_phrases = [
        "all jobs", "any jobs", "based on my cv", "match my cv", "for me",
        "ai domain", "data domain", "ai & data", "data & ai",
        "ai field", "data field", "ai area", "data area",
        "ai and data", "data and ai", "machine learning",
        "ai roles", "data roles", "tech roles", "technology roles",
        "artificial intelligence", "data science",
    ]
    if any(phrase in t for phrase in domain_phrases):
        return _cv_role_defaults(cv)

    if "billing analyst" in t or "billing" in t:
        return _sanitize_roles(["Billing Analyst", "Senior Billing Analyst", "Billing Specialist", "Accounts Receivable Analyst"], cv, text)

    # Try to extract specific role titles (comma-separated)
    parts = re.split(r"[,;]| and |/| or |\n", text)
    out = []
    for p in parts:
        p = p.strip()
        # Filter out non-role fragments (search instructions, locations, etc.)
        skip_words = ["please", "search", "find", "jobs in", "last", "days", "week",
                      "month", "gcc", "uae", "dubai", "saudi", "qatar", "remote",
                      "looking for", "i want", "i need", "help me"]
        if any(sw in p.lower() for sw in skip_words):
            continue
        if 2 <= len(p) <= 60:
            out.append(p)

    # If after filtering we have nothing meaningful, use smart defaults
    if not out:
        return _cv_role_defaults(cv)

    return _sanitize_roles(out, cv, text)


def _extract_json(text: str) -> Optional[dict]:
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def _call_ai_preference_agent(user_msg: str, s: dict) -> Optional[Tuple[str, str, dict]]:
    if not AI_API_KEY or AI_PROVIDER.lower() not in {"groq", "openai", "openai-compatible"}:
        return None

    try:
        import httpx

        cv = s.get("cv", {})
        profile = s.get("profile", {})
        prefs = s.get("preferences", {})
        history = s.get("chat", {}).get("history", [])[-8:]

        system = {
            "role": "system",
            "content": (
                "You are the AI Assistant inside JobsLand. Convert the user's natural language into job-search preferences "
                "aligned only with the currently uploaded CV, not any previous candidate. Be concise and helpful.\n\n"
                "Return ONLY valid JSON with this schema:\n"
                "{\n"
                '  "reply": "short user-facing reply",\n'
                '  "step": "country|recency|roles|confirm|ready|greet",\n'
                '  "preferences": {\n'
                '    "ready": boolean|null,\n'
                '    "country": "GCC|Europe|GCC + Europe|UAE|Saudi Arabia|Qatar|Kuwait|Bahrain|Oman|Remote|..."|null,\n'
                '    "countries": ["..."],\n'
                '    "locations": ["..."],\n'
                '    "search_keywords": ["..."],\n'
                '    "recency_days": number|null,\n'
                '    "roles": ["..."]\n'
                "  }\n"
                "}\n\n"
                "Rules:\n"
                "- If the user says GCC/Gulf/MENA, set country to GCC and countries/locations to UAE, Saudi Arabia, Qatar, Kuwait, Bahrain, Oman.\n"
                "- If the user says Europe/EU, set country to Europe and countries/locations to United Kingdom, Ireland, Germany, Netherlands, France, Spain, Italy, Switzerland, Sweden, Denmark, Belgium, Poland.\n"
                "- If the user combines regions, for example Gulf and Europe, set country to GCC + Europe and include both region country lists.\n"
                "- If they say last week, set recency_days to 7. Today/past 24 hours is 1. Last month is 30.\n"
                "- If they say all jobs for me / based on my CV, choose concrete LinkedIn-searchable titles from the uploaded CV summary, title, and skills.\n"
                "- If they ask for a broad keyword search like data and AI, AI & Data, GenAI, machine learning, or billing analyst, set search_keywords to the literal LinkedIn query phrase and use roles for target/scoring intent.\n"
                "- Do not add AI, Data Science, Machine Learning, Scala, or Data Governance roles unless the current CV or user explicitly asks for them.\n"
                "- For billing/invoicing/accounts receivable CVs, good titles include Billing Analyst, Senior Billing Analyst, Billing Specialist, Accounts Receivable Analyst, Invoicing Specialist, Revenue Cycle Analyst, Collections Analyst, and Finance Operations Analyst.\n"
                "- Set ready true only when country/location, recency, and roles are known.\n"
                "- Ask one short follow-up if something essential is missing.\n"
            ),
        }
        context = {
            "role": "user",
            "content": json.dumps({
                "profile": profile,
                "cv": {
                    "filename": cv.get("filename"),
                    "skills": cv.get("skills", []),
                    "years": cv.get("years"),
                    "summary": cv.get("summary"),
                },
                "current_preferences": prefs,
                "recent_history": [{"role": h.get("role"), "content": h.get("content")} for h in history],
                "user_message": user_msg,
            }, ensure_ascii=False),
        }

        response = httpx.post(
            f"{AI_BASE_URL.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {AI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": AI_MODEL,
                "messages": [system, context],
                "temperature": 0.15,
                "response_format": {"type": "json_object"},
            },
            timeout=20,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = _extract_json(content)
        if not parsed:
            return None

        reply = (parsed.get("reply") or "").strip()
        next_step = parsed.get("step") or s["chat"].get("step") or "greet"
        prefs_update = parsed.get("preferences") or {}
        prefs_update = {k: v for k, v in prefs_update.items() if v not in (None, "", [])}

        direct_country_payload = _parse_country_payload(user_msg)
        if direct_country_payload:
            edit_words = ("add", "also", "include", "plus", "with", "and")
            replace_words = ("only", "instead", "replace", "switch", "change to", "set to")
            lower_msg = user_msg.lower()
            mode = "add" if any(w in lower_msg for w in edit_words) and not any(w in lower_msg for w in replace_words) else "replace"
            prefs_update.update(_merge_country_payload(prefs, direct_country_payload, mode))
        else:
            country = prefs_update.get("country")
            if country and not prefs_update.get("countries"):
                prefs_update.update(_country_payload(country))

        parsed_search_keywords = _parse_search_keywords(user_msg, cv)
        if parsed_search_keywords:
            prefs_update["search_keywords"] = parsed_search_keywords

        if not prefs_update.get("roles") and _message_mentions_roles(user_msg):
            parsed_roles = _parse_roles(user_msg, cv)
            if parsed_roles:
                prefs_update["roles"] = parsed_roles
        elif prefs_update.get("roles"):
            prefs_update["roles"] = _sanitize_roles(prefs_update.get("roles") or [], cv, user_msg)

        merged_for_ready = {**prefs, **prefs_update}
        if (
            merged_for_ready.get("country")
            and merged_for_ready.get("recency_days")
            and merged_for_ready.get("roles")
        ):
            prefs_update["ready"] = True
            next_step = "ready"
            if not reply or next_step == "ready":
                nice = {1: "today", 7: "last week", 14: "last 14 days", 30: "last 30 days"}.get(
                    merged_for_ready.get("recency_days"),
                    f"last {merged_for_ready.get('recency_days')} days"
                )
                reply = (
                    f"Updated. I’ll search **{merged_for_ready.get('country')}** for "
                    f"**{', '.join((merged_for_ready.get('roles') or [])[:4])}** from **{nice}**.\n\n"
                    + (f"LinkedIn keyword query: **{', '.join(merged_for_ready.get('search_keywords') or [])}**.\n\n" if merged_for_ready.get("search_keywords") else "")
                    + "You can keep editing filters here, or run the automation when ready."
                )

        followup = _missing_preference_followup(prefs_update, prefs)
        if followup and not prefs_update.get("ready"):
            next_step, reply = followup

        if not reply:
            reply = "Got it. I updated your search preferences."
        return next_step, reply, prefs_update
    except Exception as e:
        logger.warning("AI assistant Groq call failed, using deterministic fallback: %s", e)
        return None


def _greet(s) -> str:
    cv = s["cv"]
    name = (cv.get("name") or s["profile"].get("name") or "there").split(" ")[0]
    if not cv.get("filename"):
        return (f"Hi {name}! Before we set your preferences, I need your CV uploaded "
                f"so I can match jobs to your real skills. Head to **My CV** and upload it — "
                f"then come back here and say *hi* again.")
    return (f"Hi {name}! 👋 I see your CV — **{len(cv['skills'])} skills** and "
            f"**{cv['years']} years** of experience. Let's set up your search.\n\n"
            f"**Which country should I search in?** (e.g. UAE, Saudi Arabia, Qatar, Remote…)")


def _step_response(step: str, msg: str, s: dict) -> Tuple[str, str, dict]:
    """Returns (next_step, reply, partial_pref_update)."""
    ai_result = _call_ai_preference_agent(msg, s)
    if ai_result:
        return ai_result

    existing = s.get("preferences", {}) or {}
    country_update = _parse_country_payload(msg)
    lower_msg = msg.lower()
    edit_words = ("add", "also", "include", "plus", "with", "and")
    replace_words = ("only", "instead", "replace", "switch", "change to", "set to")
    if country_update:
        country_mode = "add" if any(w in lower_msg for w in edit_words) and not any(w in lower_msg for w in replace_words) else "replace"
        country_update = _merge_country_payload(existing, country_update, country_mode)
    country = country_update["country"] if country_update else existing.get("country")
    days = _parse_recency(msg)
    if not days:
        days = existing.get("recency_days")
    search_keywords = _parse_search_keywords(msg, s.get("cv", {})) or existing.get("search_keywords") or []
    roles = _parse_roles(msg, s.get("cv", {})) if _message_mentions_roles(msg) else (existing.get("roles") or [])
    if existing.get("roles") and not _message_mentions_roles(msg):
        roles = existing.get("roles") or roles
    existing_country_update = None
    if country and not country_update:
        existing_country_update = {
            "country": country,
            "countries": existing.get("countries") or _country_payload(country).get("countries", []),
            "locations": existing.get("locations") or _country_payload(country).get("locations", []),
        }
    country_payload = country_update or existing_country_update

    if country and days and roles:
        return "ready", (
            f"Got it. I saved a ready-to-run search for **{country}**, jobs from the **last {days} day(s)**, "
            "focused on roles aligned to the uploaded CV.\n\n"
            "The **Run Automation** button is ready below."
        ), {**(country_payload or _country_payload(country)), "recency_days": days, "roles": roles, "search_keywords": search_keywords, "ready": True}

    if country and roles and not days:
        return "recency", _recency_prompt(country, roles), {**(country_payload or _country_payload(country)), "roles": roles, "search_keywords": search_keywords, "ready": False}

    if country and days and not roles:
        return "roles", _roles_prompt(country, days), {**(country_payload or _country_payload(country)), "search_keywords": search_keywords, "recency_days": days, "ready": False}

    if roles and days and not country:
        return "country", "I have the roles and timeframe. **Which region should I search?** Try **GCC**, **Europe**, **UAE**, **Saudi Arabia**, or **Remote**.", {"roles": roles, "search_keywords": search_keywords, "recency_days": days, "ready": False}

    if step == "greet":
        if not s["cv"].get("filename"):
            return "greet", _greet(s), {}
        return "country", _greet(s), {}

    if step == "country":
        if not country:
            return "country", ("I didn't catch a country in there — try one of: "
                              + ", ".join(COUNTRIES[:8]) + "…"), {}
        return "recency", (f"Great — searching in **{country}**.\n\n"
                            f"**How recent should the jobs be?** Choose **today**, **last week**, **last 14 days**, or **last 30 days**."), country_update or _country_payload(country)

    if step == "recency":
        if not days:
            return "recency", "Try something like *last week*, *past 24 hours*, or *14 days*.", {}
        nice = {1: "past 24 hours", 7: "last week", 14: "last 14 days", 30: "last month"}.get(days, f"last {days} days")
        return "roles", (f"Got it — I'll only consider jobs posted in the **{nice}**.\n\n"
                         f"**Which roles or titles should I target?** "
                         f"(comma-separated, e.g. *AI Product Manager, Data Science Manager, Strategy Lead*)"),\
               {"recency_days": days}

    if step == "roles":
        if not roles:
            return "roles", "Give me at least one role title — e.g. *Data Manager, AI Lead*.", {}
        return "confirm", (
            f"Perfect. Here's what I have:\n\n"
            f"• **Country:** {s['preferences'].get('country')}\n"
            f"• **Recency:** last {s['preferences'].get('recency_days')} day(s)\n"
            f"• **Target roles:** {', '.join(roles)}\n\n"
            f"Say **yes** to lock this in and I'll get the *Run Automation* button ready, "
            f"or tell me what to change."
        ), {"roles": roles}

    if step == "confirm":
        t = msg.lower()
        if any(w in t for w in ("yes", "yep", "yeah", "go", "lock", "confirm", "ready", "ok", "okay", "lgtm")):
            return "ready", (
                "🎉 You're all set! I've saved your preferences.\n\n"
                "When you're ready, click **Run Automation** on the Dashboard. "
                "I'll start scanning LinkedIn and applying to matching Easy Apply jobs — "
                "and route anything that needs your input to **Pending Review**."
            ), {"ready": True}
        if "country" in t: return "country", "Sure — which country instead?", {}
        if "recen" in t or "day" in t or "week" in t:
            return "recency", "No problem — what timeframe should I use instead?", {}
        if "role" in t or "title" in t:
            return "roles", "Got it — what roles should I target instead?", {}
        return "confirm", "Reply **yes** to lock these in, or tell me which one to change (country / recency / roles).", {}

    if step == "ready":
        return "ready", ("You're already set! Hit **Run Automation** on the Dashboard whenever you're ready. "
                         "If you want to change anything, just say *reset preferences*."), {}

    return "greet", _greet(s), {}


@router.get("/")
def get_chat():
    s = state.get()
    return {
        "history": s["chat"]["history"],
        "step": s["chat"]["step"],
        "preferences": s["preferences"],
    }


@router.post("/")
def chat(body: ChatIn):
    s = state.get()

    if body.reset or (body.message and body.message.strip().lower() in
                      ("reset", "reset preferences", "start over", "restart")):
        def m(st):
            st["chat"] = {"step": "greet", "history": []}
            st["preferences"] = {"ready": False, "country": None, "city": None,
                                  "countries": [], "locations": [], "roles": [],
                                  "search_keywords": [], "recency_days": None, "industries": []}
        state.update(m)
        s = state.get()

    user_msg = (body.message or "").strip()
    step = s["chat"]["step"]

    if not user_msg and not s["chat"]["history"]:
        # opening message
        reply = _greet(s)
        next_step = "country" if s["cv"].get("filename") else "greet"
        def m(st):
            st["chat"]["step"] = next_step
            st["chat"]["history"] = [{"role": "assistant", "content": reply, "ts": time.time()}]
        state.update(m)
        return {"reply": reply, "step": next_step, "preferences": state.get()["preferences"]}

    next_step, reply, partial = _step_response(step, user_msg, s)

    def m(st):
        if user_msg:
            st["chat"]["history"].append({"role": "user", "content": user_msg, "ts": time.time()})
        st["chat"]["history"].append({"role": "assistant", "content": reply, "ts": time.time()})
        st["chat"]["step"] = next_step
        if partial:
            st["preferences"] = {**st["preferences"], **partial}
    state.update(m)

    return {"reply": reply, "step": next_step, "preferences": state.get()["preferences"]}
