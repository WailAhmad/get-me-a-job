"""
Real OAuth sign-in routes for Google and Apple.

These routes do not fake a successful login. If provider credentials are not
configured, they return a clear setup error.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import smtplib
import time
from email.message import EmailMessage
from email.utils import formataddr
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
    SMTP_FROM_EMAIL,
    SMTP_FROM_NAME,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_PROVIDER,
    SMTP_USERNAME,
    SMTP2GO_API_BASE_URL,
    SMTP2GO_API_KEY,
)

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EMAIL_CODE_TTL_SECONDS = 10 * 60
PASSWORD_MIN_LENGTH = 8


def _smtp_configured() -> bool:
    if SMTP_PROVIDER == "smtp2go" and SMTP2GO_API_KEY and SMTP_FROM_EMAIL:
        return True
    return bool(SMTP_HOST and SMTP_PORT and SMTP_USERNAME and SMTP_PASSWORD and SMTP_FROM_EMAIL)


def _missing_smtp() -> list[str]:
    return [k for k, v in {
        "SMTP_FROM_EMAIL": SMTP_FROM_EMAIL,
        **(
            {"SMTP2GO_API_KEY": SMTP2GO_API_KEY}
            if SMTP_PROVIDER == "smtp2go"
            else {
                "SMTP_HOST": SMTP_HOST,
                "SMTP_PORT": SMTP_PORT,
                "SMTP_USERNAME": SMTP_USERNAME,
                "SMTP_PASSWORD": SMTP_PASSWORD,
            }
        ),
    }.items() if not v]


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


def _normalise_email(email: str) -> str:
    return (email or "").strip().lower()


def _display_name_from_email(email: str) -> str:
    return email.split("@", 1)[0].replace(".", " ").replace("_", " ").title()


def _hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260_000)
    return salt.hex(), digest.hex()


def _password_ok(password: str, salt_hex: str, digest_hex: str) -> bool:
    _, candidate = _hash_password(password, salt_hex)
    return hmac.compare_digest(candidate, digest_hex)


def _save_local_login_profile(email: str, name: str | None = None):
    _save_profile({
        "name": name or _display_name_from_email(email),
        "title": email,
        "email": email,
        "photo": None,
        "imported_at": time.time(),
        "connection_type": "password",
        "auth_provider": "local_password",
        "email_verified": False,
    })


def _validate_password(password: str):
    if len(password or "") < PASSWORD_MIN_LENGTH:
        raise HTTPException(400, f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")


def _hash_code(email: str, code: str) -> str:
    secret = SMTP_PASSWORD or GOOGLE_CLIENT_SECRET or APPLE_CLIENT_SECRET or "jobsland-local-secret"
    msg = f"{email.lower()}:{code}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


SMTP_DEV_MODE = not _smtp_configured()   # True = console-log fallback, no real email sent


def _send_email_code(email: str, code: str) -> None:
    """Send the verification code.

    If SMTP is not configured (dev / no-secrets environment) we print the code
    to stdout with a clear banner instead of raising an error — so the app is
    fully usable without any email service set up.
    """
    if SMTP_DEV_MODE:
        banner = "=" * 60
        print(f"\n{banner}")
        print("  JOBSLAND EMAIL VERIFICATION CODE (dev / no-SMTP mode)")
        print(f"  To:   {email}")
        print(f"  Code: {code}")
        print(f"{banner}\n", flush=True)
        return   # success — caller reads the code from the console

    subject = "Your JobsLand verification code"
    text_body = (
        "Your JobsLand verification code is:\n\n"
        f"{code}\n\n"
        "This code expires in 10 minutes. If you did not request it, you can ignore this email.\n"
    )

    if SMTP_PROVIDER == "smtp2go" and SMTP2GO_API_KEY:
        try:
            resp = httpx.post(
                f"{SMTP2GO_API_BASE_URL.rstrip('/')}/email/send",
                headers={
                    "Content-Type": "application/json",
                    "accept": "application/json",
                    "X-Smtp2go-Api-Key": SMTP2GO_API_KEY,
                },
                json={
                    "sender": SMTP_FROM_EMAIL,
                    "to": [email],
                    "subject": subject,
                    "text_body": text_body,
                },
                timeout=20,
            )
            payload = resp.json() if resp.content else {}
            if resp.status_code >= 400:
                detail = payload.get("data", {}).get("error") or payload.get("error") or resp.text
                raise HTTPException(502, f"SMTP2GO API send failed: {detail}")
            data = payload.get("data") or {}
            if int(data.get("failed") or 0) > 0:
                failures = data.get("failures") or []
                raise HTTPException(502, f"SMTP2GO API rejected the message: {failures}")
            if int(data.get("succeeded") or 0) < 1:
                raise HTTPException(502, f"SMTP2GO API did not confirm delivery: {payload}")
            return
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(502, f"SMTP2GO API send failed: {exc}")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((SMTP_FROM_NAME or "JobsLand", SMTP_FROM_EMAIL))
    msg["To"] = email
    msg.set_content(text_body)

    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
                smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(
            502,
            "SMTP2GO rejected the SMTP credentials. Use the username/password from Sending > SMTP Users, not the SMTP2GO dashboard login password.",
        )
    except smtplib.SMTPException as exc:
        raise HTTPException(502, f"SMTP2GO send failed: {exc}")
    except OSError as exc:
        raise HTTPException(502, f"Could not connect to SMTP2GO at {SMTP_HOST}:{SMTP_PORT}: {exc}")


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
        "email": {
            "configured": _smtp_configured(),
            "dev_mode": SMTP_DEV_MODE,
            "missing": _missing_smtp(),
            "provider": SMTP_PROVIDER,
            "host": SMTP_HOST,
            "port": SMTP_PORT,
            "api_configured": bool(SMTP2GO_API_KEY),
            "detail": (
                "No SMTP configured — verification codes are printed to the backend console."
                if SMTP_DEV_MODE else
                "SMTP2GO is selected by default. Add SMTP2GO_API_KEY plus a verified SMTP_FROM_EMAIL, or use SMTP username/password fallback."
            ),
        },
        "password": {
            "configured": True,
            "storage": "local_state",
            "detail": "Free local email/password accounts are stored in data/state.json using PBKDF2 password hashes. Email verification can be enabled later.",
        },
    }


@router.post("/password/register")
def password_register(body: dict):
    email = _normalise_email(body.get("email") or "")
    password = str(body.get("password") or "")
    name = (body.get("name") or "").strip() or None
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Enter a valid email address.")
    _validate_password(password)
    s = state.get()
    users = s.get("users") or {}
    if email in users:
        raise HTTPException(409, "An account already exists for this email. Sign in instead.")
    salt, digest = _hash_password(password)
    now = time.time()

    def m(st):
        st.setdefault("users", {})[email] = {
            "email": email,
            "name": name or _display_name_from_email(email),
            "password_salt": salt,
            "password_hash": digest,
            "created_at": now,
            "updated_at": now,
            "email_verified": False,
        }

    state.update(m)
    _save_local_login_profile(email, name)
    return {"success": True, "profile": state.get()["profile"]}


@router.post("/password/login")
def password_login(body: dict):
    email = _normalise_email(body.get("email") or "")
    password = str(body.get("password") or "")
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Enter a valid email address.")
    user = (state.get().get("users") or {}).get(email)
    if not user or not _password_ok(password, user.get("password_salt") or "", user.get("password_hash") or ""):
        raise HTTPException(401, "Invalid email or password.")
    _save_local_login_profile(email, user.get("name"))
    return {"success": True, "profile": state.get()["profile"]}


@router.post("/email/start")
def email_start(body: dict):
    email = (body.get("email") or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Enter a valid email address.")

    now = time.time()
    existing = state.get().get("email_auth", {})
    if existing.get("email") == email and now - float(existing.get("sent_at") or 0) < 45:
        raise HTTPException(429, "Please wait a moment before requesting another code.")

    code = f"{secrets.randbelow(1000000):06d}"
    _send_email_code(email, code)

    def m(s):
        s["email_auth"] = {
            "email": email,
            "code_hash": _hash_code(email, code),
            "sent_at": now,
            "expires_at": now + EMAIL_CODE_TTL_SECONDS,
            "attempts": 0,
        }

    state.update(m)
    return {
        "success": True,
        "dev_mode": SMTP_DEV_MODE,
        "message": (
            "Dev mode: check the Backend API console for your verification code (SMTP not configured)."
            if SMTP_DEV_MODE else
            "Verification code sent — check your email."
        ),
    }


@router.post("/email/verify")
def email_verify(body: dict):
    email = (body.get("email") or "").strip().lower()
    code = re.sub(r"\D", "", str(body.get("code") or ""))
    pending = state.get().get("email_auth") or {}

    if not email or not code:
        raise HTTPException(400, "Email and verification code are required.")
    if pending.get("email") != email:
        raise HTTPException(400, "No verification code is active for this email.")
    if time.time() > float(pending.get("expires_at") or 0):
        raise HTTPException(400, "Verification code expired. Request a new code.")
    if int(pending.get("attempts") or 0) >= 5:
        raise HTTPException(429, "Too many incorrect attempts. Request a new code.")

    if not hmac.compare_digest(pending.get("code_hash") or "", _hash_code(email, code)):
        def bump(s):
            s.setdefault("email_auth", {})["attempts"] = int(pending.get("attempts") or 0) + 1
        state.update(bump)
        raise HTTPException(400, "Incorrect verification code.")

    display_name = email.split("@", 1)[0].replace(".", " ").replace("_", " ").title()
    _save_profile({
        "name": display_name,
        "title": email,
        "email": email,
        "photo": None,
        "imported_at": time.time(),
        "connection_type": "email",
        "auth_provider": "email",
        "email_verified": True,
    })

    def clear(s):
        s.pop("email_auth", None)
    state.update(clear)
    return {"success": True, "profile": state.get()["profile"]}


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
