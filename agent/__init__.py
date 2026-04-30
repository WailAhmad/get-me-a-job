"""Jobs Land Autonomous Agent.

A standalone Playwright-driven LinkedIn Easy Apply agent. Reads the user's
profile from data.json (auto-synced from the FastAPI app's state.json),
scores jobs via a Groq-hosted LLM, and only submits Easy Apply forms when
the match score >= 85.

Runs out-of-process from the FastAPI app. The two share `data/history.db`
and `data/process.log` so the existing React dashboard can read live results.
"""
__version__ = "0.1.0"
