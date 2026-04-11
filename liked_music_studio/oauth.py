from __future__ import annotations

import json
import os
import secrets
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
OAUTH_CACHE_DIR = BASE_DIR / "runtime" / "oauth"
OAUTH_TOKEN_FILE = OAUTH_CACHE_DIR / "youtube_oauth_token.json"
STATE_CACHE_FILE = OAUTH_CACHE_DIR / "oauth_state.json"

# Get from environment variables (set on render.com)
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
OAUTH_REDIRECT_URI = os.environ.get("OAUTH_REDIRECT_URI", "http://localhost:4173/api/auth/callback")

# Google OAuth Scopes
SCOPES = [
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.readonly",
]

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _ensure_oauth_dir() -> None:
    OAUTH_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def is_configured() -> bool:
    """Check if Google OAuth credentials are configured."""
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def get_google_oauth_url() -> str | None:
    """
    Generate and return the Google OAuth authorization URL.
    Also generates and stores a state token.
    """
    if not is_configured():
        return None

    try:
        _ensure_oauth_dir()

        # Generate a random state token for CSRF protection
        state = secrets.token_urlsafe(32)
        
        # Store state with timestamp for validation (expires in 10 minutes)
        import time
        state_data = {
            "state": state,
            "timestamp": time.time(),
        }
        STATE_CACHE_FILE.write_text(json.dumps(state_data), encoding="utf-8")

        # Build OAuth URL
        params = {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "state": state,
            "prompt": "consent",
        }
        
        return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    except Exception:
        return None


def exchange_code_for_token(code: str, state: str) -> bool:
    """
    Exchange the OAuth authorization code for an access token.
    Validates the state token for security.
    """
    if not is_configured():
        return False

    try:
        # Validate state token
        if not STATE_CACHE_FILE.exists():
            return False

        state_data = json.loads(STATE_CACHE_FILE.read_text(encoding="utf-8"))
        stored_state = state_data.get("state")
        
        if not stored_state or stored_state != state:
            return False

        # Check if state token expired (10 minutes)
        import time
        if time.time() - state_data.get("timestamp", 0) > 600:
            return False

        # Exchange code for token
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
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=10) as response:
            response_data = json.loads(response.read().decode("utf-8"))

        # Store the token
        _ensure_oauth_dir()
        OAUTH_TOKEN_FILE.write_text(json.dumps(response_data), encoding="utf-8")
        STATE_CACHE_FILE.unlink(missing_ok=True)

        return True
    except Exception:
        return False


def load_oauth_token() -> dict[str, Any] | None:
    """
    Load stored OAuth token if available.
    """
    if not OAUTH_TOKEN_FILE.exists():
        return None

    try:
        return json.loads(OAUTH_TOKEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_authenticated() -> bool:
    """Check if user has valid OAuth credentials."""
    token = load_oauth_token()
    return token is not None and "access_token" in token


def get_youtube_auth_header() -> str | None:
    """
    Get the authorization header for YouTube API requests.
    Used with yt-dlp and direct HTTP calls.
    """
    token = load_oauth_token()
    if not token:
        return None

    access_token = token.get("access_token")
    if not access_token:
        return None

    return f"Bearer {access_token}"


def clear_oauth_token() -> None:
    """Clear stored OAuth token."""
    OAUTH_TOKEN_FILE.unlink(missing_ok=True)
    STATE_CACHE_FILE.unlink(missing_ok=True)
