"""Rotating file logger for the agent. Writes to data/process.log."""
from __future__ import annotations
import logging
import sys
from logging.handlers import RotatingFileHandler

from agent import config

_FMT = "%(asctime)s  %(levelname)-7s  %(name)-22s  %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _configure_root() -> None:
    global _configured
    if _configured:
        return
    root = logging.getLogger("agent")
    root.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
    root.propagate = False

    fh = RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUPS,
        encoding="utf-8",
    )
    fh.setFormatter(logging.Formatter(_FMT, _DATEFMT))
    root.addHandler(fh)

    # Mirror INFO+ to stderr so the user sees something when running in foreground.
    sh = logging.StreamHandler(stream=sys.stderr)
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter(_FMT, _DATEFMT))
    root.addHandler(sh)

    _configured = True


def get_logger(name: str = "agent") -> logging.Logger:
    _configure_root()
    if name == "agent":
        return logging.getLogger("agent")
    return logging.getLogger(f"agent.{name}")
