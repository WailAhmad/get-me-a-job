"""Groq chat-completions client (OpenAI-compatible).

Uses the existing `AI_API_KEY` / `AI_BASE_URL` / `AI_MODEL` env vars from the
FastAPI app so the user only configures their key once.

Default model: `llama-3.3-70b-versatile` — Groq's flagship reasoning model,
on the free tier as of 2026.
"""
from __future__ import annotations
import json
import re
from typing import Any, Dict

import httpx

from agent import config
from agent.ai.provider import LLMProvider
from agent.logger import get_logger

log = get_logger("ai.groq")


class GroqAPIError(RuntimeError):
    pass


def _strip_fences(text: str) -> str:
    """Strip markdown code fences if the model wrapped its JSON."""
    t = text.strip()
    if t.startswith("```"):
        # ```json\n…\n``` or ```\n…\n```
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _extract_json(text: str) -> Dict[str, Any]:
    """Tolerant JSON extractor: tries strict parse, then the first {...} block."""
    candidate = _strip_fences(text)
    try:
        return json.loads(candidate)
    except Exception:
        pass
    m = re.search(r"\{.*\}", candidate, flags=re.S)
    if not m:
        raise GroqAPIError(f"Model did not return JSON. First 200 chars: {candidate[:200]!r}")
    return json.loads(m.group(0))


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self,
                 api_key: str | None = None,
                 base_url: str | None = None,
                 model: str | None = None,
                 timeout: float | None = None):
        self.api_key  = api_key  or config.GROQ_API_KEY
        self.base_url = (base_url or config.GROQ_BASE_URL).rstrip("/")
        self.model    = model    or config.GROQ_MODEL
        self.timeout  = timeout  or config.GROQ_TIMEOUT
        if not self.api_key:
            log.warning("AI_API_KEY is not set — LLM calls will fail until you export your Groq key.")

    def chat_json(self, system: str, user: str, *,
                  max_tokens: int = 600, temperature: float = 0.1) -> Dict[str, Any]:
        if not self.api_key:
            raise GroqAPIError("AI_API_KEY is not configured. Export it before running the agent.")

        body = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
        }
        url = f"{self.base_url}/chat/completions"

        # One transparent retry on transient network blips / 5xx.
        last_exc: Exception | None = None
        for attempt in (1, 2):
            try:
                r = httpx.post(url, headers=headers, json=body, timeout=self.timeout)
                if r.status_code >= 500:
                    raise GroqAPIError(f"Groq HTTP {r.status_code}: {r.text[:200]}")
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"]
                return _extract_json(content)
            except (httpx.RequestError, GroqAPIError) as exc:
                last_exc = exc
                log.warning("Groq attempt %d failed: %s", attempt, exc)
                continue
        raise GroqAPIError(f"Groq request failed twice: {last_exc}")
