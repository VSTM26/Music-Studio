from __future__ import annotations

import json
import os
import secrets
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
OAUTH_REDIRECT_URI = os.environ.get(
    "OAUTH_REDIRECT_URI",
    "http://localhost:4173/api/auth/callback",
)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
]

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _oauth_dir(session_root: Path) -> Path:
    return session_root / "oauth"


def _token_file(session_root: Path) -> Path:
    return _oauth_dir(session_root) / "youtube_oauth_token.json"


def _state_file(session_root: Path) -> Path:
    return _oauth_dir(session_root) / "oauth_state.json"


def _ensure_oauth_dir(session_root: Path) -> None:
    _oauth_dir(session_root).mkdir(parents=True, exist_ok=True)


def is_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and OAUTH_REDIRECT_URI)


def _write_token(session_root: Path, token_data: dict[str, Any]) -> dict[str, Any]:
    payload = dict(token_data)
    expires_in = payload.get("expires_in")
    if isinstance(expires_in, (int, float)):
        payload["expires_at"] = int(time.time() + float(expires_in))
    _ensure_oauth_dir(session_root)
    _token_file(session_root).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def get_google_oauth_url(session_root: Path, session_id: str) -> str | None:
    if not is_configured():
        return None

    _ensure_oauth_dir(session_root)
    state = f"{session_id}:{secrets.token_urlsafe(32)}"
    _state_file(session_root).write_text(
        json.dumps({"state": state, "timestamp": time.time()}, indent=2),
        encoding="utf-8",
    )
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent select_account",
    }
    params["state"] = state
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_token(session_root: Path, code: str, state: str) -> bool:
    if not is_configured():
        return False

    state_path = _state_file(session_root)
    if not state_path.exists():
        return False

    try:
        state_data = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return False

    stored_state = str(state_data.get("state") or "")
    timestamp = float(state_data.get("timestamp") or 0)
    if not stored_state or stored_state != state:
        return False
    if time.time() - timestamp > 600:
        return False

    token_data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    request = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=urllib.parse.urlencode(token_data).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return False

    _write_token(session_root, response_data)
    state_path.unlink(missing_ok=True)
    return True


def load_oauth_token(session_root: Path) -> dict[str, Any] | None:
    token_path = _token_file(session_root)
    if not token_path.exists():
        return None
    try:
        return json.loads(token_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _refresh_access_token(session_root: Path, refresh_token: str) -> dict[str, Any] | None:
    token_data = {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    request = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=urllib.parse.urlencode(token_data).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            refreshed = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    existing = load_oauth_token(session_root) or {}
    merged = dict(existing)
    merged.update(refreshed)
    merged.setdefault("refresh_token", refresh_token)
    return _write_token(session_root, merged)


def get_access_token(session_root: Path) -> str | None:
    token = load_oauth_token(session_root)
    if not token:
        return None

    access_token = str(token.get("access_token") or "").strip()
    refresh_token = str(token.get("refresh_token") or "").strip()
    expires_at = int(token.get("expires_at") or 0)
    now = int(time.time())

    if access_token and (not expires_at or expires_at - now > 90):
        return access_token

    if not refresh_token or not is_configured():
        return access_token or None

    refreshed = _refresh_access_token(session_root, refresh_token)
    if not refreshed:
        return access_token or None
    return str(refreshed.get("access_token") or "").strip() or None


def is_authenticated(session_root: Path) -> bool:
    return bool(get_access_token(session_root))


def get_authorization_header(session_root: Path) -> str | None:
    access_token = get_access_token(session_root)
    if not access_token:
        return None
    return f"Bearer {access_token}"


def clear_oauth_token(session_root: Path) -> None:
    _token_file(session_root).unlink(missing_ok=True)
    _state_file(session_root).unlink(missing_ok=True)


def resolve_session_id(state: str) -> str | None:
    raw_state = str(state or "").strip()
    if ":" not in raw_state:
        return None
    session_id, _ = raw_state.split(":", 1)
    return session_id.strip() or None
