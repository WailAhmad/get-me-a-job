"""
Chat router — guided AI assistant for capturing search preferences.

Flow (scripted, deterministic so the demo always works):
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
COUNTRIES = ["GCC", "UAE", "Saudi Arabia", "Qatar", "Kuwait", "Bahrain", "Oman", "Egypt", "Jordan",
             "United Kingdom", "United States", "Germany", "Singapore", "Remote"]


def _parse_country(text: str) -> Optional[str]:
    t = text.lower()
    map_ = {
        "gcc": "GCC", "gulf": "GCC", "middle east": "GCC", "mena": "GCC",
        "uae": "UAE", "emirates": "UAE", "dubai": "UAE", "abu dhabi": "UAE",
        "saudi": "Saudi Arabia", "ksa": "Saudi Arabia", "riyadh": "Saudi Arabia", "jeddah": "Saudi Arabia",
        "qatar": "Qatar", "doha": "Qatar",
        "kuwait": "Kuwait", "bahrain": "Bahrain", "oman": "Oman", "muscat": "Oman",
        "egypt": "Egypt", "cairo": "Egypt",
        "jordan": "Jordan", "amman": "Jordan",
        "uk": "United Kingdom", "england": "United Kingdom", "london": "United Kingdom",
        "us ": "United States", "usa": "United States", "america": "United States",
        "germany": "Germany", "berlin": "Germany",
        "singapore": "Singapore",
        "remote": "Remote", "anywhere": "Remote",
    }
    for k, v in map_.items():
        if k in t:
            return v
    return None


def _country_payload(country: str) -> dict:
    if country == "GCC":
        return {"country": "GCC", "countries": GCC_COUNTRIES, "locations": GCC_COUNTRIES}
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


def _parse_roles(text: str) -> List[str]:
    t = text.lower()
    if any(phrase in t for phrase in ("all jobs", "any jobs", "based on my cv", "match my cv", "for me")):
        return [
            "AI & Data Leadership",
            "Data & AI Product",
            "AI Platform",
            "AI Solutions Architecture",
            "Data Governance",
            "Digital Transformation",
            "AI Automation",
            "Machine Learning Leadership",
        ]
    parts = re.split(r"[,;]| and |/| or |\n", text)
    out = [p.strip() for p in parts if p.strip()]
    return [r for r in out if 2 <= len(r) <= 60][:8]


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
                "You are the AI Assistant inside Jobs Land, an executive AI/data job automation app. "
                "Your job is to convert the user's natural language into job-search preferences aligned with Wael's CV "
                "and his previous application behavior. Be concise and helpful.\n\n"
                "Return ONLY valid JSON with this schema:\n"
                "{\n"
                '  "reply": "short user-facing reply",\n'
                '  "step": "country|recency|roles|confirm|ready|greet",\n'
                '  "preferences": {\n'
                '    "ready": boolean|null,\n'
                '    "country": "GCC|UAE|Saudi Arabia|Qatar|Kuwait|Bahrain|Oman|Remote|..."|null,\n'
                '    "countries": ["..."],\n'
                '    "locations": ["..."],\n'
                '    "recency_days": number|null,\n'
                '    "roles": ["..."]\n'
                "  }\n"
                "}\n\n"
                "Rules:\n"
                "- If the user says GCC/Gulf/MENA, set country to GCC and countries/locations to UAE, Saudi Arabia, Qatar, Kuwait, Bahrain, Oman.\n"
                "- If they say last week, set recency_days to 7. Today/past 24 hours is 1. Last month is 30.\n"
                "- If they say all jobs for me / based on my CV, choose semantic role families suitable for a senior AI & Data leader.\n"
                "- Good role families include AI & Data Leadership, Data & AI Product, AI Platform, AI Solutions Architecture, Data Governance, Digital Transformation, AI Automation, Machine Learning Leadership.\n"
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

        country = prefs_update.get("country")
        if country and not prefs_update.get("countries"):
            prefs_update.update(_country_payload(country))

        if not prefs_update.get("roles"):
            parsed_roles = _parse_roles(user_msg)
            if parsed_roles:
                prefs_update["roles"] = parsed_roles

        if (
            prefs_update.get("country")
            and prefs_update.get("recency_days")
            and prefs_update.get("roles")
        ):
            prefs_update["ready"] = True
            next_step = "ready"

        if not reply:
            reply = "Got it. I updated your search preferences."
        return next_step, reply, prefs_update
    except Exception as e:
        logger.warning("AI assistant Groq call failed, using deterministic fallback: %s", e)
        return None


def _greet(s) -> str:
    name = (s["profile"].get("name") or "there").split(" ")[0]
    cv = s["cv"]
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

    country = _parse_country(msg)
    days = _parse_recency(msg)
    roles = _parse_roles(msg)

    if country and days and roles:
        country_update = _country_payload(country)
        return "ready", (
            f"Got it. I saved a ready-to-run search for **{country}**, jobs from the **last {days} day(s)**, "
            "focused on AI/data leadership roles aligned to your CV and previous applications.\n\n"
            "Go to the Dashboard and click **Run Automation**."
        ), {**country_update, "recency_days": days, "roles": roles, "ready": True}

    if step == "greet":
        if not s["cv"].get("filename"):
            return "greet", _greet(s), {}
        return "country", _greet(s), {}

    if step == "country":
        if not country:
            return "country", ("I didn't catch a country in there — try one of: "
                              + ", ".join(COUNTRIES[:6]) + "…"), {}
        return "recency", (f"Great — searching in **{country}**.\n\n"
                            f"**How recent should the jobs be?** (e.g. *posted today*, "
                            f"*last week*, *last 14 days*, *last month*)"), _country_payload(country)

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
            st["preferences"] = {**st["preferences"], "ready": False}
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
