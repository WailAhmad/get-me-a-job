"""Abstract LLM provider interface.

Concrete impls live alongside (groq.py for now). Adding another provider
later is just a matter of subclassing `LLMProvider`.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class LLMProvider(ABC):
    """The tiny surface area the agent needs from any LLM."""

    name: str = "abstract"

    @abstractmethod
    def chat_json(self, system: str, user: str, *,
                  max_tokens: int = 600, temperature: float = 0.1) -> Dict[str, Any]:
        """Send a chat-completion request that MUST return valid JSON.

        Implementations are responsible for stripping markdown fences,
        retrying once on a parse failure, and raising on hard errors.
        """
        raise NotImplementedError


# ── Singleton ────────────────────────────────────────────────────────
_INSTANCE: Optional[LLMProvider] = None


def get_provider() -> LLMProvider:
    """Lazy-init the configured provider. Currently always Groq."""
    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE
    from agent.ai.groq import GroqProvider
    _INSTANCE = GroqProvider()
    return _INSTANCE
