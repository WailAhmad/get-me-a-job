"""
Real OAuth sign-in routes for Google and Apple.

These routes do not fake a successful login. If provider credentials are not
configured, they return a clear setup error.
"""
import base64
import json
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from backend import state
from backend.config import (
    APPLE_CLIENT_ID,
    APPLE_CLIENT_SECRET,
    APPLE_REDIRECT_URI,
    FRONTEND_URL,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _frontend_redirect(path: str = "/", **params):
    query = urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{FRONTEND_URL.rstrip('/')}{path}"
    if query:
        url += f"?{query}"
    return RedirectResponse(url)


def _save_oauth_state(provider: str, token: str):
    def m(s):
        s.setdefault("oauth", {})["state"] = token
        s.setdefault("oauth", {})["provider"] = provider

    state.update(m)


def _verify_oauth_state(token: str):
    saved = state.get().get("oauth", {}).get("state")
    if not token or token != saved:
        raise HTTPException(400, "OAuth state mismatch. Please try signing in again.")


def _save_profile(profile: dict):
    def m(s):
        s["profile"] = profile

    state.update(m)


def _decode_jwt_payload(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
    except Exception:
        return {}


@router.get("/providers")
def providers():
    return {
        "google": {
            "configured": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
            "missing": [k for k, v in {
                "GOOGLE_CLIENT_ID": GOOGLE_CLIENT_ID,
                "GOOGLE_CLIENT_SECRET": GOOGLE_CLIENT_SECRET,
            }.items() if not v],
        },
        "apple": {
            "configured": bool(APPLE_CLIENT_ID and APPLE_CLIENT_SECRET),
            "missing": [k for k, v in {
                "APPLE_CLIENT_ID": APPLE_CLIENT_ID,
                "APPLE_CLIENT_SECRET": APPLE_CLIENT_SECRET,
            }.items() if not v],
        },
    }


@router.get("/google/start")
def google_start():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            501,
            "Google OAuth is not configured. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env.",
        )

    token = secrets.token_urlsafe(24)
    _save_oauth_state("google", token)
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": token,
        "access_type": "offline",
        "prompt": "select_account",
    }
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}")


@router.get("/google/callback")
def google_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return _frontend_redirect("/", auth_error=error)
    _verify_oauth_state(state)

    with httpx.Client(timeout=20) as client:
        token_response = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
        userinfo = client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        userinfo.raise_for_status()
        user = userinfo.json()

    _save_profile({
        "name": user.get("name") or user.get("email") or "Google user",
        "title": user.get("email") or "Google account connected",
        "email": user.get("email"),
        "photo": user.get("picture"),
        "imported_at": __import__("time").time(),
        "connection_type": "google",
        "auth_provider": "google",
    })
    return _frontend_redirect("/", auth="success")


@router.get("/apple/start")
def apple_start():
    if not APPLE_CLIENT_ID or not APPLE_CLIENT_SECRET:
        raise HTTPException(
            501,
            "Apple Sign in is not configured. Add APPLE_CLIENT_ID and APPLE_CLIENT_SECRET to .env.",
        )

    token = secrets.token_urlsafe(24)
    _save_oauth_state("apple", token)
    params = {
        "client_id": APPLE_CLIENT_ID,
        "redirect_uri": APPLE_REDIRECT_URI,
        "response_type": "code id_token",
        "response_mode": "form_post",
        "scope": "name email",
        "state": token,
    }
    return RedirectResponse(f"https://appleid.apple.com/auth/authorize?{urlencode(params)}")


@router.post("/apple/callback")
async def apple_callback(
    request: Request,
    code: str = Form(""),
    id_token: str = Form(""),
    state: str = Form(""),
    error: str = Form(""),
):
    if error:
        return _frontend_redirect("/", auth_error=error)
    _verify_oauth_state(state)

    with httpx.Client(timeout=20) as client:
        token_response = client.post(
            "https://appleid.apple.com/auth/token",
            data={
                "client_id": APPLE_CLIENT_ID,
                "client_secret": APPLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": APPLE_REDIRECT_URI,
            },
        )
        token_response.raise_for_status()
        tokens = token_response.json()

    payload = _decode_jwt_payload(tokens.get("id_token") or id_token)
    email = payload.get("email")
    _save_profile({
        "name": email or "Apple user",
        "title": email or "Apple account connected",
        "email": email,
        "photo": None,
        "imported_at": __import__("time").time(),
        "connection_type": "apple",
        "auth_provider": "apple",
    })
    return _frontend_redirect("/", auth="success")
