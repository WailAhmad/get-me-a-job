"""Spawn Google Chrome silently with a remote debugging port.

The agent launches a real Google Chrome process (not the bundled Chromium)
because LinkedIn fingerprints the binary. The window is positioned far
off-screen so it doesn't steal focus on macOS, and stdout/stderr are
redirected to /dev/null. Returns the WebSocket endpoint Playwright will
attach to via `connect_over_cdp(...)`.
"""
from __future__ import annotations
import os
import socket
import subprocess
import sys
import time
from typing import Optional

import httpx

from agent import config
from agent.logger import get_logger

log = get_logger("chrome")


def _is_port_open(host: str, port: int, timeout: float = 0.3) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


def _ws_endpoint(host: str, port: int, timeout: float = 5.0) -> Optional[str]:
    try:
        r = httpx.get(f"http://{host}:{port}/json/version", timeout=timeout)
        r.raise_for_status()
        return r.json().get("webSocketDebuggerUrl")
    except Exception as exc:
        log.debug("ws_endpoint probe failed: %s", exc)
        return None


def _hidden_subprocess_kwargs() -> dict:
    """Cross-platform flags to launch a process without stealing window focus."""
    kw: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin":  subprocess.DEVNULL,
        "start_new_session": True,
        "close_fds": True,
    }
    if sys.platform == "win32":
        CREATE_NO_WINDOW = 0x08000000
        DETACHED_PROCESS = 0x00000008
        kw["creationflags"] = CREATE_NO_WINDOW | DETACHED_PROCESS
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        kw["startupinfo"] = si
    return kw


def launch_chrome(visible: bool = False) -> str:
    """Start (or reuse) Chrome with remote debugging. Returns the ws_endpoint.

    visible=True positions the window on-screen at full size — used for the
    one-time `--login` flow. Default is False: window is far off-screen so it
    doesn't steal focus.
    """
    # Reuse if already up.
    if _is_port_open(config.CDP_HOST, config.CDP_PORT):
        ws = _ws_endpoint(config.CDP_HOST, config.CDP_PORT)
        if ws:
            log.info("Reusing existing Chrome on :%d", config.CDP_PORT)
            return ws
        # Port held by something else — bail loudly.
        raise RuntimeError(
            f"Port {config.CDP_PORT} is occupied but not by a Chrome CDP server. "
            "Close whatever is on it and retry."
        )

    config.PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    binary = config.chrome_binary()

    if visible:
        window_args = ["--window-position=120,80", "--window-size=1280,900"]
    else:
        window_args = ["--window-position=2400,2400", "--window-size=1280,900"]

    args = [
        binary,
        f"--remote-debugging-port={config.CDP_PORT}",
        f"--user-data-dir={config.PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-default-apps",
        "--disable-features=Translate,MediaRouter,OptimizationHints",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-sync",
        "--disable-extensions",
        "--metrics-recording-only",
        "--mute-audio",
        *window_args,
        "--lang=en-US",
        "about:blank",
    ]

    log.info("Launching Chrome → CDP :%d  (profile: %s, visible=%s)",
             config.CDP_PORT, config.PROFILE_DIR, visible)
    subprocess.Popen(args, **_hidden_subprocess_kwargs())

    # Wait up to 12s for the debugging port to come up.
    deadline = time.time() + 12.0
    while time.time() < deadline:
        if _is_port_open(config.CDP_HOST, config.CDP_PORT):
            ws = _ws_endpoint(config.CDP_HOST, config.CDP_PORT)
            if ws:
                log.info("Chrome ready  ws=%s…", ws[:60])
                return ws
        time.sleep(0.25)

    raise RuntimeError("Chrome did not open the debugging port in time.")


def shutdown_chrome() -> None:
    """Best-effort: ask Chrome to close via CDP. Leaves no zombies."""
    ws = _ws_endpoint(config.CDP_HOST, config.CDP_PORT, timeout=1.0)
    if not ws:
        return
    try:
        httpx.get(f"http://{config.CDP_HOST}:{config.CDP_PORT}/json/close", timeout=2.0)
    except Exception:
        pass
