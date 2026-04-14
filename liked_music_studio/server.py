from __future__ import annotations

import json
import mimetypes
import os
import secrets
import shutil
import threading
import urllib.parse
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import partial
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from . import APP_NAME, APP_VERSION
from .downloader import download_urls, get_tool_status
from . import oauth, youtube


BASE_DIR = Path(__file__).resolve().parents[1]
PUBLIC_DIR = BASE_DIR / "public"
RUNTIME_DIR = BASE_DIR / "runtime"
SESSIONS_DIR = RUNTIME_DIR / "sessions"
APP_HOST = os.environ.get("APP_HOST", "0.0.0.0")
DEFAULT_PORT = int(os.environ.get("PORT", "4173"))
SESSION_COOKIE_NAME = "music_studio_session"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _quote_path_segment(value: str) -> str:
    return urllib.parse.quote(value.replace("\\", "/"), safe="/-._~")


@dataclass
class JobState:
    running: bool = False
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_error: str | None = None
    last_exit_code: int | None = None
    requested_count: int | None = None
    mode: str | None = None
    progress_percent: float | None = None
    progress_label: str | None = None
    progress_detail: str | None = None
    active_run_id: str | None = None


@dataclass
class SessionState:
    session_id: str
    root_dir: Path
    logs: list[dict[str, str]] = field(default_factory=list)
    download: JobState = field(default_factory=JobState)


class StudioState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.sessions: dict[str, SessionState] = {}
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    def get_session(self, session_id: str) -> SessionState:
        with self.lock:
            session = self.sessions.get(session_id)
            if session:
                return session
            root_dir = SESSIONS_DIR / session_id
            root_dir.mkdir(parents=True, exist_ok=True)
            session = SessionState(session_id=session_id, root_dir=root_dir)
            self.sessions[session_id] = session
            return session

    def add_log(self, session_id: str, message: str, kind: str = "info") -> None:
        session = self.get_session(session_id)
        with self.lock:
            session.logs.append(
                {
                    "id": f"{session_id}-{len(session.logs) + 1}",
                    "kind": kind,
                    "message": message,
                    "timestamp": _utc_now(),
                }
            )
            if len(session.logs) > 220:
                session.logs = session.logs[-220:]

    def _load_latest_download_manifest(self, session: SessionState) -> dict[str, Any] | None:
        manifest_path = session.root_dir / "latest-download.json"
        if not manifest_path.exists():
            return None
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _build_live_progress(self, download_state: JobState) -> dict[str, Any]:
        if download_state.running:
            return {
                "kind": "download",
                "running": True,
                "label": download_state.progress_label or "Preparing download",
                "detail": download_state.progress_detail or "Waiting for yt-dlp to begin.",
                "percent": download_state.progress_percent,
            }
        if download_state.progress_label or download_state.progress_detail:
            return {
                "kind": "download",
                "running": False,
                "label": download_state.progress_label or "Last job complete",
                "detail": download_state.progress_detail or "The last job finished.",
                "percent": download_state.progress_percent,
            }
        return {
            "kind": None,
            "running": False,
            "label": "Ready",
            "detail": "Paste links or connect YouTube to start a download.",
            "percent": None,
        }

    def build_status_payload(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        with self.lock:
            download_state = JobState(**session.download.__dict__)
            logs = list(session.logs)

        latest_download = self._load_latest_download_manifest(session)
        return {
            "app": {
                "name": APP_NAME,
                "version": APP_VERSION,
            },
            "auth": {
                "configured": oauth.is_configured(),
                "authenticated": oauth.is_authenticated(session.root_dir),
            },
            "tools": get_tool_status(),
            "download": download_state.__dict__,
            "progress": self._build_live_progress(download_state),
            "latestDownload": latest_download,
            "logs": logs,
        }

    def _update_download_progress(
        self,
        session_id: str,
        *,
        label: str | None = None,
        detail: str | None = None,
        percent: float | None = None,
    ) -> None:
        session = self.get_session(session_id)
        with self.lock:
            if label is not None:
                session.download.progress_label = label
            if detail is not None:
                session.download.progress_detail = detail
            if percent is None:
                session.download.progress_percent = None
            else:
                session.download.progress_percent = max(0.0, min(100.0, round(float(percent), 1)))

    def _set_download_job_started(
        self,
        session_id: str,
        *,
        mode: str,
        requested_count: int | None,
        progress_label: str,
        progress_detail: str,
    ) -> str:
        session = self.get_session(session_id)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        with self.lock:
            if session.download.running:
                raise RuntimeError("A download job is already running for this browser session.")
            session.download.running = True
            session.download.last_started_at = _utc_now()
            session.download.last_finished_at = None
            session.download.last_error = None
            session.download.last_exit_code = None
            session.download.requested_count = requested_count
            session.download.mode = mode
            session.download.progress_percent = 0.0
            session.download.progress_label = progress_label
            session.download.progress_detail = progress_detail
            session.download.active_run_id = run_id
        return run_id

    def start_direct_download(self, session_id: str, urls: list[str], extract_audio: bool) -> None:
        cleaned_urls = [str(url).strip() for url in urls if str(url).strip()]
        if not cleaned_urls:
            raise RuntimeError("Paste at least one URL before starting a download.")

        run_id = self._set_download_job_started(
            session_id,
            mode="direct-audio" if extract_audio else "direct-media",
            requested_count=len(cleaned_urls),
            progress_label=f"Preparing {len(cleaned_urls)} link(s)",
            progress_detail="Setting up yt-dlp for your pasted links.",
        )
        threading.Thread(
            target=self._run_direct_download_job,
            args=(session_id, run_id, cleaned_urls, extract_audio),
            daemon=True,
        ).start()

    def start_liked_videos_download(self, session_id: str, extract_audio: bool) -> None:
        session = self.get_session(session_id)
        if not oauth.is_authenticated(session.root_dir):
            raise RuntimeError("Sign in with Google first so Music Studio can read your YouTube likes.")

        run_id = self._set_download_job_started(
            session_id,
            mode="liked-audio" if extract_audio else "liked-media",
            requested_count=None,
            progress_label="Connecting to your YouTube account",
            progress_detail="Reading your liked videos with Google OAuth.",
        )
        threading.Thread(
            target=self._run_liked_videos_download_job,
            args=(session_id, run_id, extract_audio),
            daemon=True,
        ).start()

    def _job_root(self, session: SessionState, run_id: str) -> Path:
        return session.root_dir / "jobs" / run_id

    def _prune_old_jobs(self, session: SessionState, keep: int = 5) -> None:
        jobs_root = session.root_dir / "jobs"
        if not jobs_root.exists():
            return
        job_dirs = sorted(
            [path for path in jobs_root.iterdir() if path.is_dir()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in job_dirs[keep:]:
            shutil.rmtree(path, ignore_errors=True)

    def _write_latest_download_manifest(
        self,
        session_id: str,
        run_id: str,
        *,
        source_kind: str,
        requested_count: int,
        extract_audio: bool,
        downloads_dir: Path,
    ) -> dict[str, Any]:
        session = self.get_session(session_id)
        files: list[dict[str, Any]] = []
        for path in sorted(downloads_dir.rglob("*")):
            if not path.is_file():
                continue
            relative_path = path.relative_to(downloads_dir).as_posix()
            files.append(
                {
                    "name": path.name,
                    "relativePath": relative_path,
                    "sizeBytes": path.stat().st_size,
                    "url": f"/downloads/{run_id}/{_quote_path_segment(relative_path)}",
                }
            )

        manifest = {
            "runId": run_id,
            "savedAt": _utc_now(),
            "sourceKind": source_kind,
            "requestedCount": requested_count,
            "extractAudio": extract_audio,
            "completedFileCount": len(files),
            "files": files,
        }
        manifest_path = session.root_dir / "latest-download.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self._prune_old_jobs(session)
        return manifest

    def _finish_download_job_success(
        self,
        session_id: str,
        *,
        run_id: str,
        source_kind: str,
        requested_count: int,
        extract_audio: bool,
        downloads_dir: Path,
    ) -> None:
        manifest = self._write_latest_download_manifest(
            session_id,
            run_id,
            source_kind=source_kind,
            requested_count=requested_count,
            extract_audio=extract_audio,
            downloads_dir=downloads_dir,
        )
        session = self.get_session(session_id)
        with self.lock:
            session.download.running = False
            session.download.last_finished_at = _utc_now()
            session.download.last_exit_code = 0
            session.download.progress_label = "Download complete"
            session.download.progress_detail = (
                f"Prepared {manifest['completedFileCount']} file(s) for local saving."
            )
            session.download.progress_percent = 100.0
            session.download.active_run_id = run_id

    def _finish_download_job_error(self, session_id: str, error: Exception) -> None:
        session = self.get_session(session_id)
        with self.lock:
            session.download.running = False
            session.download.last_finished_at = _utc_now()
            session.download.last_exit_code = 1
            session.download.last_error = str(error)
            session.download.progress_label = "Download failed"
            session.download.progress_detail = str(error)
            session.download.progress_percent = None

    def _run_direct_download_job(
        self,
        session_id: str,
        run_id: str,
        urls: list[str],
        extract_audio: bool,
    ) -> None:
        session = self.get_session(session_id)
        self.add_log(session_id, f"Starting a link download for {len(urls)} URL(s).", "info")
        try:
            job_root = self._job_root(session, run_id)
            downloads_dir = download_urls(
                urls,
                job_root,
                extract_audio,
                lambda message, kind="info": self.add_log(session_id, message, kind),
                progress=lambda payload: self._update_download_progress(
                    session_id,
                    label=str(payload.get("label") or "") or None,
                    detail=str(payload.get("detail") or "") or None,
                    percent=payload.get("percent") if isinstance(payload.get("percent"), (int, float)) else None,
                ),
            )
            self._finish_download_job_success(
                session_id,
                run_id=run_id,
                source_kind="links",
                requested_count=len(urls),
                extract_audio=extract_audio,
                downloads_dir=downloads_dir,
            )
            self.add_log(session_id, "Finished preparing files for local download.", "success")
        except Exception as error:
            self._finish_download_job_error(session_id, error)
            self.add_log(session_id, str(error), "error")

    def _run_liked_videos_download_job(
        self,
        session_id: str,
        run_id: str,
        extract_audio: bool,
    ) -> None:
        session = self.get_session(session_id)
        self.add_log(session_id, "Reading your YouTube liked videos.", "info")
        try:
            urls: list[str] = []

            def library_progress(payload: dict[str, Any]) -> None:
                percent = payload.get("percent")
                scaled_percent = None
                if isinstance(percent, (int, float)):
                    scaled_percent = round(min(40.0, float(percent) * 0.4), 1)
                self._update_download_progress(
                    session_id,
                    label=str(payload.get("label") or "") or None,
                    detail=str(payload.get("detail") or "") or None,
                    percent=scaled_percent,
                )

            liked_videos = youtube.list_liked_videos(session.root_dir, progress=library_progress)
            urls = [item["url"] for item in liked_videos if item.get("url")]
            if not urls:
                raise RuntimeError("No liked YouTube videos were available for this account.")

            self.add_log(session_id, f"Found {len(urls)} liked video(s) in your YouTube account.", "success")
            self._update_download_progress(
                session_id,
                label=f"Downloading {len(urls)} liked video(s)",
                detail="yt-dlp is now preparing media files from your account list.",
                percent=40.0,
            )

            job_root = self._job_root(session, run_id)

            def download_progress(payload: dict[str, Any]) -> None:
                percent = payload.get("percent")
                scaled_percent = None
                if isinstance(percent, (int, float)):
                    scaled_percent = round(40.0 + (float(percent) * 0.6), 1)
                self._update_download_progress(
                    session_id,
                    label=str(payload.get("label") or "") or None,
                    detail=str(payload.get("detail") or "") or None,
                    percent=scaled_percent,
                )

            downloads_dir = download_urls(
                urls,
                job_root,
                extract_audio,
                lambda message, kind="info": self.add_log(session_id, message, kind),
                progress=download_progress,
            )
            self._finish_download_job_success(
                session_id,
                run_id=run_id,
                source_kind="youtube-liked-videos",
                requested_count=len(urls),
                extract_audio=extract_audio,
                downloads_dir=downloads_dir,
            )
            self.add_log(session_id, "Finished preparing files from your YouTube likes.", "success")
        except Exception as error:
            self._finish_download_job_error(session_id, error)
            self.add_log(session_id, str(error), "error")

    def resolve_download(self, session_id: str, run_id: str, relative_path: str) -> Path | None:
        session = self.get_session(session_id)
        downloads_root = (session.root_dir / "jobs" / run_id / "downloads").resolve()
        candidate = (downloads_root / relative_path).resolve()
        if downloads_root not in candidate.parents and candidate != downloads_root:
            return None
        if not candidate.exists() or not candidate.is_file():
            return None
        return candidate


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "MusicStudio/1.0"

    def __init__(self, *args: Any, state: StudioState, **kwargs: Any) -> None:
        self.state = state
        self.session_id: str | None = None
        self._set_cookie = False
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _ensure_session(self) -> str:
        if self.session_id:
            return self.session_id

        cookie_header = self.headers.get("Cookie") or ""
        cookie = SimpleCookie()
        if cookie_header:
            try:
                cookie.load(cookie_header)
            except Exception:
                cookie = SimpleCookie()

        morsel = cookie.get(SESSION_COOKIE_NAME)
        session_id = morsel.value.strip() if morsel and morsel.value.strip() else ""
        if not session_id:
            session_id = secrets.token_urlsafe(24)
            self._set_cookie = True

        self.session_id = session_id
        self.state.get_session(session_id)
        return session_id

    def do_GET(self) -> None:
        session_id = self._ensure_session()
        path = urlparse(self.path).path
        query_params = urllib.parse.parse_qs(urlparse(self.path).query)

        if path == "/api/status":
            self._send_json(HTTPStatus.OK, self.state.build_status_payload(session_id))
            return
        if path == "/api/auth/status":
            session = self.state.get_session(session_id)
            self._send_json(
                HTTPStatus.OK,
                {
                    "authenticated": oauth.is_authenticated(session.root_dir),
                    "configured": oauth.is_configured(),
                },
            )
            return
        if path == "/api/auth/start":
            session = self.state.get_session(session_id)
            auth_url = oauth.get_google_oauth_url(session.root_dir, session_id)
            if not auth_url:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {
                        "message": "OAuth is not configured. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and OAUTH_REDIRECT_URI.",
                    },
                )
                return
            self._send_json(HTTPStatus.OK, {"auth_url": auth_url})
            return
        if path == "/api/auth/callback":
            code = (query_params.get("code") or [None])[0]
            state = (query_params.get("state") or [None])[0]
            if not code or not state:
                self._send_html(
                    HTTPStatus.BAD_REQUEST,
                    self._build_oauth_callback_html(False, "Missing code or state parameter."),
                )
                return
            resolved_session_id = oauth.resolve_session_id(state) or session_id
            if resolved_session_id != session_id:
                session_id = resolved_session_id
                self.session_id = resolved_session_id
                self._set_cookie = True
            session = self.state.get_session(session_id)
            success = oauth.exchange_code_for_token(session.root_dir, code, state)
            self._send_html(
                HTTPStatus.OK if success else HTTPStatus.UNAUTHORIZED,
                self._build_oauth_callback_html(
                    success,
                    "Google sign-in is complete. You can close this window."
                    if success
                    else "Google sign-in failed. Please close this window and try again.",
                ),
            )
            return
        if path.startswith("/downloads/"):
            raw_relative = unquote(path[len("/downloads/") :]).strip("/")
            if "/" not in raw_relative:
                self._send_text(HTTPStatus.NOT_FOUND, "Not found")
                return
            run_id, relative_path = raw_relative.split("/", 1)
            file_path = self.state.resolve_download(session_id, run_id, relative_path)
            if not file_path:
                self._send_text(HTTPStatus.NOT_FOUND, "Not found")
                return
            self._serve_file(file_path, download_name=file_path.name)
            return
        self._serve_static(path)

    def do_POST(self) -> None:
        session_id = self._ensure_session()
        path = urlparse(self.path).path
        body = self._read_json()
        try:
            if path == "/api/auth/logout":
                session = self.state.get_session(session_id)
                oauth.clear_oauth_token(session.root_dir)
                self._send_json(HTTPStatus.OK, {"ok": True, "message": "Logged out."})
                return
            if path == "/api/direct-download":
                raw_urls = body.get("urls") if isinstance(body, dict) else None
                if isinstance(raw_urls, str):
                    urls = raw_urls.split()
                elif isinstance(raw_urls, list):
                    urls = [str(item) for item in raw_urls]
                else:
                    raise RuntimeError("urls must be provided as a string or an array.")
                extract_audio = bool(body.get("extractAudio")) if isinstance(body, dict) else False
                self.state.start_direct_download(session_id, urls, extract_audio)
                self._send_json(HTTPStatus.ACCEPTED, {"ok": True, "message": "Download job started."})
                return
            if path == "/api/youtube/download-liked":
                extract_audio = bool(body.get("extractAudio")) if isinstance(body, dict) else False
                self.state.start_liked_videos_download(session_id, extract_audio)
                self._send_json(
                    HTTPStatus.ACCEPTED,
                    {"ok": True, "message": "YouTube liked videos download started."},
                )
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"message": "Not found"})
        except RuntimeError as error:
            self._send_json(HTTPStatus.CONFLICT, {"ok": False, "message": str(error)})
        except Exception as error:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "message": str(error)})

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        if not raw.strip():
            return {}
        return json.loads(raw)

    def _apply_common_headers(self) -> None:
        if self._set_cookie and self.session_id:
            secure = self.headers.get("X-Forwarded-Proto", "").lower() == "https"
            cookie_value = f"{SESSION_COOKIE_NAME}={self.session_id}; Path=/; HttpOnly; SameSite=Lax"
            if secure:
                cookie_value += "; Secure"
            self.send_header("Set-Cookie", cookie_value)
            self._set_cookie = False

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self._apply_common_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self._write_body(body)

    def _send_text(self, status: HTTPStatus, payload: str) -> None:
        body = payload.encode("utf-8")
        self.send_response(status)
        self._apply_common_headers()
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self._write_body(body)

    def _send_html(self, status: HTTPStatus, payload: str) -> None:
        body = payload.encode("utf-8")
        self.send_response(status)
        self._apply_common_headers()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self._write_body(body)

    def _serve_static(self, path: str) -> None:
        relative = "index.html" if path in {"", "/"} else path.lstrip("/")
        public_root = PUBLIC_DIR.resolve()
        file_path = (public_root / relative).resolve()
        if public_root not in file_path.parents and file_path != public_root:
            self._send_text(HTTPStatus.FORBIDDEN, "Forbidden")
            return
        if not file_path.exists() or not file_path.is_file():
            self._send_text(HTTPStatus.NOT_FOUND, "Not found")
            return
        self._serve_file(file_path)

    def _serve_file(self, file_path: Path, download_name: str | None = None) -> None:
        mime_type, _ = mimetypes.guess_type(file_path.name)
        self.send_response(HTTPStatus.OK)
        self._apply_common_headers()
        self.send_header("Content-Type", f"{mime_type or 'application/octet-stream'}")
        self.send_header("Cache-Control", "no-store")
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Content-Length", str(file_path.stat().st_size))
        self.end_headers()
        try:
            with file_path.open("rb") as handle:
                shutil.copyfileobj(handle, self.wfile)
        except OSError:
            return

    def _write_body(self, payload: bytes) -> None:
        try:
            self.wfile.write(payload)
        except OSError:
            return

    def _build_oauth_callback_html(self, success: bool, message: str) -> str:
        payload = "true" if success else "false"
        safe_message = json.dumps(message)
        return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Music Studio Sign-In</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: #f5efe3;
        color: #102127;
        font: 16px/1.5 Georgia, serif;
      }}
      main {{
        max-width: 32rem;
        padding: 2rem;
        border-radius: 24px;
        background: rgba(255, 255, 255, 0.88);
        box-shadow: 0 20px 60px rgba(16, 33, 39, 0.12);
      }}
    </style>
  </head>
  <body>
    <main>
      <h1>{'Signed in' if success else 'Sign-in failed'}</h1>
      <p>{message}</p>
      <p>You can close this window if it does not close automatically.</p>
    </main>
    <script>
      const success = {payload};
      const message = {safe_message};
      if (window.opener) {{
        window.opener.postMessage({{ type: 'music-studio-auth', success, message }}, window.location.origin);
      }}
      setTimeout(() => window.close(), 150);
    </script>
  </body>
</html>"""


def _create_server(handler: Any) -> tuple[ThreadingHTTPServer, int]:
    port_candidates = [DEFAULT_PORT] if "PORT" in os.environ else [*range(DEFAULT_PORT, DEFAULT_PORT + 25), 0]
    last_error: OSError | None = None

    for port in port_candidates:
        try:
            server = ThreadingHTTPServer((APP_HOST, port), handler)
            return server, int(server.server_address[1])
        except OSError as error:
            last_error = error
            continue

    assert last_error is not None
    raise last_error


def main() -> None:
    state = StudioState()
    handler = partial(StudioHandler, state=state)
    server, actual_port = _create_server(handler)
    print(f"{APP_NAME} is running on port {actual_port}")
    if os.environ.get("NO_OPEN_BROWSER") != "1" and APP_HOST in {"127.0.0.1", "localhost"}:
        try:
            webbrowser.open(f"http://{APP_HOST}:{actual_port}")
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
