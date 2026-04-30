from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from app.models.entities import PlatformConnection, SourceRun
from app.services.job_import import create_or_update_job, parse_job_text

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
LOCAL_DIR = Path(__file__).resolve().parents[2] / ".local"
CLIENT_SECRET_PATH = LOCAL_DIR / "google_client_secret.json"
TOKEN_PATH = LOCAL_DIR / "gmail_token.json"
REDIRECT_URI = "http://127.0.0.1:8000/api/sources/gmail/callback"
JOB_ALERT_QUERY = (
    '(from:linkedin.com OR from:bayt.com OR '
    'from:gulftalent.com OR from:irishjobs.ie OR from:workday.com OR from:greenhouse.io OR from:lever.co '
    'OR subject:(job OR jobs OR alert OR application)) newer_than:30d'
)


def gmail_connection(db: Session) -> PlatformConnection:
    item = db.query(PlatformConnection).filter(PlatformConnection.platform == "Gmail").first()
    if not item:
        item = PlatformConnection(platform="Gmail", status="credentials_required", auth_type="OAuth 2.0")
        db.add(item)
        db.flush()
    item.token_path = str(TOKEN_PATH) if TOKEN_PATH.exists() else item.token_path
    return item


def auth_url(db: Session) -> dict:
    LOCAL_DIR.mkdir(exist_ok=True)
    connection = gmail_connection(db)
    if not CLIENT_SECRET_PATH.exists():
        connection.status = "credentials_required"
        connection.last_error = f"Missing {CLIENT_SECRET_PATH}"
        db.commit()
        return {
            "status": "credentials_required",
            "message": "Place your Google OAuth desktop/web client JSON at backend/.local/google_client_secret.json",
            "client_secret_path": str(CLIENT_SECRET_PATH),
        }
    flow = Flow.from_client_secrets_file(str(CLIENT_SECRET_PATH), scopes=SCOPES, redirect_uri=REDIRECT_URI)
    url, state = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    connection.sync_status = "awaiting_oauth"
    connection.last_error = ""
    db.commit()
    return {"status": "authorization_required", "auth_url": url, "state": state}


def oauth_callback(db: Session, code: str, state: str = "") -> dict:
    if not CLIENT_SECRET_PATH.exists():
        raise RuntimeError(f"Missing {CLIENT_SECRET_PATH}")
    LOCAL_DIR.mkdir(exist_ok=True)
    flow = Flow.from_client_secrets_file(str(CLIENT_SECRET_PATH), scopes=SCOPES, redirect_uri=REDIRECT_URI)
    flow.fetch_token(code=code)
    TOKEN_PATH.write_text(flow.credentials.to_json())
    os.chmod(TOKEN_PATH, 0o600)
    connection = gmail_connection(db)
    connection.status = "connected"
    connection.sync_status = "idle"
    connection.token_path = str(TOKEN_PATH)
    connection.last_error = ""
    db.commit()
    return {"status": "connected"}


def disconnect(db: Session) -> dict:
    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()
    connection = gmail_connection(db)
    connection.status = "credentials_required"
    connection.sync_status = "disconnected"
    connection.token_path = ""
    db.commit()
    return {"status": "disconnected"}


def sync_gmail(db: Session, max_results: int = 25) -> dict:
    connection = gmail_connection(db)
    run = SourceRun(source_name="Gmail", status="running", metadata_json=json.dumps({"query": JOB_ALERT_QUERY}))
    db.add(run)
    db.flush()
    try:
        service = _service()
        response = service.users().messages().list(userId="me", q=JOB_ALERT_QUERY, maxResults=max_results).execute()
        messages = response.get("messages", [])
        imported = 0
        duplicates = 0
        for msg in messages:
            full = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
            parsed = _parse_message(full)
            if not parsed["text"]:
                continue
            data = parse_job_text(parsed["text"], parsed.get("url", ""), parsed.get("platform", "Gmail Alert"))
            job, duplicate = create_or_update_job(
                db,
                data,
                {
                    "source_policy": "gmail_alert",
                    "source_email_id": parsed["id"],
                    "source_email_subject": parsed["subject"],
                    "source_email_from": parsed["from"],
                },
            )
            imported += 0 if duplicate else 1
            duplicates += 1 if duplicate else 0
        run.status = "success"
        run.imported_count = imported
        run.duplicate_count = duplicates
        run.finished_at = datetime.utcnow()
        connection.status = "connected"
        connection.sync_status = "idle"
        connection.last_sync_at = datetime.utcnow()
        connection.last_error = ""
        db.commit()
        return {"status": "success", "imported": imported, "duplicates": duplicates, "scanned": len(messages)}
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)
        run.finished_at = datetime.utcnow()
        connection.sync_status = "failed"
        connection.last_error = str(exc)
        db.commit()
        return {"status": "failed", "error": str(exc)}


def get_recruiter_emails(max_results: int = 50) -> list[dict]:
    query = '(subject:interview OR subject:application OR subject:update OR subject:offer OR subject:"next steps" OR subject:rejection) newer_than:14d'
    try:
        service = _service()
        response = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
        messages = response.get("messages", [])
        results = []
        for msg in messages:
            full = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
            parsed = _parse_message(full)
            if parsed["text"]:
                results.append({
                    "id": parsed["id"],
                    "subject": parsed["subject"],
                    "from": parsed["from"],
                    "date": parsed["date"],
                    "snippet": parsed["text"][:200] + "..."
                })
        return results
    except Exception as exc:
        print(f"Error fetching recruiter emails: {exc}")
        return []


def _credentials() -> Credentials:
    if not TOKEN_PATH.exists():
        raise RuntimeError("Gmail is not connected. Use /api/sources/gmail/connect first.")
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
        os.chmod(TOKEN_PATH, 0o600)
    if not creds.valid:
        raise RuntimeError("Gmail token is invalid. Disconnect and reconnect Gmail.")
    return creds


def _service():
    return build("gmail", "v1", credentials=_credentials())


def _parse_message(message: dict) -> dict:
    headers = {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}
    text = _body_text(message.get("payload", {}))
    subject = headers.get("subject", "")
    sender = headers.get("from", "")
    date = headers.get("date", "")
    platform = _platform(sender, subject, text)
    url = _first_url(text)
    return {
        "id": message.get("id", ""),
        "subject": subject,
        "from": sender,
        "date": parsedate_to_datetime(date).isoformat() if date else "",
        "platform": platform,
        "url": url,
        "text": f"Subject: {subject}\nFrom: {sender}\n{text}",
    }


def _body_text(part: dict) -> str:
    chunks: list[str] = []
    data = part.get("body", {}).get("data")
    if data:
        chunks.append(_decode(data))
    for child in part.get("parts", []) or []:
        chunks.append(_body_text(child))
    return "\n".join(c for c in chunks if c)


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="ignore")


def _platform(sender: str, subject: str, text: str) -> str:
    blob = f"{sender} {subject} {text}".lower()
    for name in ["LinkedIn", "Bayt", "GulfTalent", "IrishJobs", "Workday", "Greenhouse", "Lever"]:
        if name.lower() in blob:
            return name
    return "Gmail Alert"


def _first_url(text: str) -> str:
    match = re.search(r"https?://[^\s<>\")]+", text)
    return match.group(0).rstrip(".,") if match else ""

