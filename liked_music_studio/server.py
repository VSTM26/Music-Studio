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
from . import oauth
from .paths import PUBLIC_DIR, RUNTIME_DIR

SESSIONS_DIR = RUNTIME_DIR / "sessions"
APP_HOST = os.environ.get("APP_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("PORT", "4173"))
SESSION_COOKIE_NAME = "music_studio_session"
OPEN_BROWSER_ON_START = os.environ.get("OPEN_BROWSER", "").strip() == "1"

try:
    import browser_cookie3  # type: ignore
except Exception:
    browser_cookie3 = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _quote_path_segment(value: str) -> str:
    return urllib.parse.quote(value.replace("\\", "/"), safe="/-._~")


def _format_cookie_line(cookie: dict[str, Any]) -> str | None:
    domain = str(cookie.get("domain") or "").strip()
    name = str(cookie.get("name") or "").strip()
    value = str(cookie.get("value") or "")
    path = str(cookie.get("path") or "/").strip() or "/"
    if not domain or not name:
        return None

    secure = "TRUE" if bool(cookie.get("secure")) else "FALSE"
    include_subdomains = "FALSE"
    if domain.startswith("."):
        include_subdomains = "TRUE"
    elif not bool(cookie.get("hostOnly")):
        domain = f".{domain}"
        include_subdomains = "TRUE"

    expires = 0
    raw_expiration = cookie.get("expirationDate")
    if isinstance(raw_expiration, (int, float)) and raw_expiration > 0:
        expires = int(raw_expiration)

    return "\t".join([domain, include_subdomains, path, secure, str(expires), name, value])


YOUTUBE_COOKIE_HOST_MARKERS = (
    "youtube.com",
    "music.youtube.com",
    "google.com",
    "accounts.google.com",
)


def _cookie_matches_youtube_hosts(domain: str) -> bool:
    cleaned = domain.lstrip(".").lower()
    return any(cleaned == marker or cleaned.endswith(f".{marker}") for marker in YOUTUBE_COOKIE_HOST_MARKERS)


def _cookiejar_cookie_to_export(cookie: Any) -> dict[str, Any]:
    expires = getattr(cookie, "expires", None)
    return {
        "domain": getattr(cookie, "domain", ""),
        "hostOnly": not bool(getattr(cookie, "domain_initial_dot", False)),
        "name": getattr(cookie, "name", ""),
        "path": getattr(cookie, "path", "/"),
        "secure": bool(getattr(cookie, "secure", False)),
        "value": getattr(cookie, "value", ""),
        "expirationDate": float(expires) if isinstance(expires, (int, float)) else None,
    }


def _browser_cookie_loaders() -> dict[str, Any]:
    if browser_cookie3 is None:
        return {}

    names = {
        "auto": "load",
        "chrome": "chrome",
        "chromium": "chromium",
        "edge": "edge",
        "brave": "brave",
        "vivaldi": "vivaldi",
        "opera": "opera",
        "firefox": "firefox",
        "librewolf": "librewolf",
        "safari": "safari",
    }
    loaders: dict[str, Any] = {}
    for public_name, attr_name in names.items():
        loader = getattr(browser_cookie3, attr_name, None)
        if callable(loader):
            loaders[public_name] = loader
    return loaders


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

    def _browser_session_dir(self, session: SessionState) -> Path:
        return session.root_dir / "browser-session"

    def _browser_cookie_file(self, session: SessionState) -> Path:
        return self._browser_session_dir(session) / "youtube-cookies.txt"

    def _browser_session_metadata_file(self, session: SessionState) -> Path:
        return self._browser_session_dir(session) / "session.json"

    def _load_browser_session_metadata(self, session: SessionState) -> dict[str, Any]:
        metadata_path = self._browser_session_metadata_file(session)
        if not metadata_path.exists():
            return {}
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            return {}
        return {}

    def _build_browser_session_payload(self, session: SessionState) -> dict[str, Any]:
        metadata = self._load_browser_session_metadata(session)
        cookie_file = self._browser_cookie_file(session)
        cookie_count = metadata.get("cookieCount")
        return {
            "imported": cookie_file.exists(),
            "cookieCount": int(cookie_count) if isinstance(cookie_count, int) else 0,
            "updatedAt": str(metadata.get("updatedAt") or "") or None,
            "userAgent": str(metadata.get("userAgent") or "") or None,
            "source": str(metadata.get("source") or "") or None,
        }

    def import_browser_session(
        self,
        session_id: str,
        *,
        cookies: list[dict[str, Any]],
        user_agent: str | None = None,
        accept_language: str | None = None,
        source: str = "chrome-extension",
    ) -> dict[str, Any]:
        session = self.get_session(session_id)
        if not cookies:
            raise RuntimeError("No browser cookies were provided.")

        cookie_lines = ["# Netscape HTTP Cookie File", "# This file is generated by Music Studio."]
        seen_keys: set[tuple[str, str, str]] = set()
        kept_count = 0
        for cookie in cookies:
            if not isinstance(cookie, dict):
                continue
            domain = str(cookie.get("domain") or "").strip()
            name = str(cookie.get("name") or "").strip()
            path = str(cookie.get("path") or "/").strip() or "/"
            if not domain or not name:
                continue
            dedupe_key = (domain, path, name)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            cookie_line = _format_cookie_line(cookie)
            if not cookie_line:
                continue
            cookie_lines.append(cookie_line)
            kept_count += 1

        if kept_count <= 0:
            raise RuntimeError("Music Studio could not build a valid cookie jar from the browser session.")

        session_dir = self._browser_session_dir(session)
        session_dir.mkdir(parents=True, exist_ok=True)
        cookie_file = self._browser_cookie_file(session)
        cookie_file.write_text("\n".join(cookie_lines) + "\n", encoding="utf-8")

        metadata = {
            "updatedAt": _utc_now(),
            "cookieCount": kept_count,
            "userAgent": str(user_agent or "").strip() or None,
            "acceptLanguage": str(accept_language or "").strip() or None,
            "source": source,
        }
        self._browser_session_metadata_file(session).write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8",
        )
        self.add_log(session_id, f"Imported {kept_count} browser cookie(s) from the local browser.", "success")
        return self._build_browser_session_payload(session)

    def import_browser_session_from_browser(
        self,
        session_id: str,
        *,
        browser_name: str,
    ) -> dict[str, Any]:
        loaders = _browser_cookie_loaders()
        if not loaders:
            raise RuntimeError(
                "Browser cookie import is unavailable because browser-cookie3 is not installed."
            )

        normalized_name = str(browser_name or "auto").strip().lower() or "auto"
        loader = loaders.get(normalized_name)
        if not loader:
            supported = ", ".join(sorted(loaders))
            raise RuntimeError(f"Unsupported browser `{browser_name}`. Supported options: {supported}.")

        try:
            cookie_jar = loader()
        except Exception as error:
            raise RuntimeError(f"Could not read cookies from {normalized_name}: {error}") from error

        cookies: list[dict[str, Any]] = []
        for cookie in cookie_jar:
            domain = str(getattr(cookie, "domain", "") or "").strip()
            if not _cookie_matches_youtube_hosts(domain):
                continue
            cookies.append(_cookiejar_cookie_to_export(cookie))

        if not cookies:
            raise RuntimeError(
                f"No YouTube or Google cookies were found in the {normalized_name} browser profile."
            )

        source_name = f"browser-cookie3:{normalized_name}"
        return self.import_browser_session(
            session_id,
            cookies=cookies,
            source=source_name,
        )

    def clear_browser_session(self, session_id: str) -> None:
        session = self.get_session(session_id)
        shutil.rmtree(self._browser_session_dir(session), ignore_errors=True)
        self.add_log(session_id, "Cleared the imported browser session.", "info")

    def _save_downloads_to_folder(self, session_id: str, downloads_dir: Path, folder_path: str) -> dict[str, Any]:
        target_root = Path(folder_path).expanduser()
        if not target_root.is_absolute():
            target_root = target_root.resolve()
        target_root.mkdir(parents=True, exist_ok=True)

        saved_count = 0
        for source_path in sorted(downloads_dir.rglob("*")):
            if not source_path.is_file():
                continue
            relative_path = source_path.relative_to(downloads_dir)
            destination = target_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination)
            saved_count += 1

        metadata = {
            "folderPath": str(target_root),
            "savedAt": _utc_now(),
            "savedFileCount": saved_count,
        }
        self.add_log(session_id, f"Saved {saved_count} file(s) into {target_root}.", "success")
        return metadata

    def save_latest_download_to_folder(self, session_id: str, folder_path: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        manifest = self._load_latest_download_manifest(session)
        if not manifest:
            raise RuntimeError("No completed download is available yet.")

        run_id = str(manifest.get("runId") or "").strip()
        if not run_id:
            raise RuntimeError("The latest download manifest is missing a run id.")

        downloads_dir = self._job_root(session, run_id) / "downloads"
        if not downloads_dir.exists():
            raise RuntimeError("The latest download files are no longer available locally.")

        manifest["localSave"] = self._save_downloads_to_folder(session_id, downloads_dir, folder_path)
        manifest_path = session.root_dir / "latest-download.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    def _resolve_browser_download_context(
        self,
        session: SessionState,
    ) -> tuple[Path | None, dict[str, str] | None]:
        metadata = self._load_browser_session_metadata(session)
        headers: dict[str, str] = {}

        user_agent = str(metadata.get("userAgent") or "").strip()
        if user_agent:
            headers["User-Agent"] = user_agent

        accept_language = str(metadata.get("acceptLanguage") or "").strip()
        if accept_language:
            headers["Accept-Language"] = accept_language

        cookie_file = self._browser_cookie_file(session)
        return (cookie_file if cookie_file.exists() else None, headers or None)

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
            "detail": "Paste links or import your browser session to start a download.",
            "percent": None,
        }

    def build_status_payload(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        with self.lock:
            download_state = JobState(**session.download.__dict__)
            logs = list(session.logs)

        latest_download = self._load_latest_download_manifest(session)
        browser_session = self._build_browser_session_payload(session)
        return {
            "sessionId": session_id,
            "app": {
                "name": APP_NAME,
                "version": APP_VERSION,
            },
            "auth": {
                "configured": oauth.is_configured(),
                "authenticated": oauth.is_authenticated(session.root_dir),
            },
            "browserSession": browser_session,
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

    def start_direct_download(
        self,
        session_id: str,
        urls: list[str],
        extract_audio: bool,
        save_folder_path: str | None = None,
    ) -> None:
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
            args=(session_id, run_id, cleaned_urls, extract_audio, save_folder_path),
            daemon=True,
        ).start()

    def start_liked_videos_download(
        self,
        session_id: str,
        extract_audio: bool,
        save_folder_path: str | None = None,
    ) -> None:
        session = self.get_session(session_id)
        cookie_file, _ = self._resolve_browser_download_context(session)
        if not cookie_file:
            raise RuntimeError(
                "Import your signed-in YouTube browser session first."
            )

        run_id = self._set_download_job_started(
            session_id,
            mode="liked-audio" if extract_audio else "liked-media",
            requested_count=1,
            progress_label="Preparing your YouTube likes",
            progress_detail="Using your imported browser session to read the likes playlist.",
        )
        threading.Thread(
            target=self._run_liked_videos_download_job,
            args=(session_id, run_id, extract_audio, save_folder_path),
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
        local_save: dict[str, Any] | None = None,
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
            "localSave": local_save,
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
        local_save: dict[str, Any] | None = None,
    ) -> None:
        manifest = self._write_latest_download_manifest(
            session_id,
            run_id,
            source_kind=source_kind,
            requested_count=requested_count,
            extract_audio=extract_audio,
            downloads_dir=downloads_dir,
            local_save=local_save,
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
        save_folder_path: str | None,
    ) -> None:
        session = self.get_session(session_id)
        self.add_log(session_id, f"Starting a link download for {len(urls)} URL(s).", "info")
        try:
            job_root = self._job_root(session, run_id)
            cookie_file, http_headers = self._resolve_browser_download_context(session)
            if cookie_file:
                self.add_log(session_id, "Using the imported browser session for this download.", "info")
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
                http_headers=http_headers,
                cookie_file=cookie_file,
            )
            local_save = (
                self._save_downloads_to_folder(session_id, downloads_dir, save_folder_path)
                if save_folder_path
                else None
            )
            self._finish_download_job_success(
                session_id,
                run_id=run_id,
                source_kind="links",
                requested_count=len(urls),
                extract_audio=extract_audio,
                downloads_dir=downloads_dir,
                local_save=local_save,
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
        save_folder_path: str | None,
    ) -> None:
        session = self.get_session(session_id)
        self.add_log(session_id, "Reading your YouTube liked videos from the signed-in browser session.", "info")
        try:
            job_root = self._job_root(session, run_id)
            cookie_file, http_headers = self._resolve_browser_download_context(session)
            if not cookie_file:
                raise RuntimeError("Import your YouTube browser session again and retry.")

            def download_progress(payload: dict[str, Any]) -> None:
                self._update_download_progress(
                    session_id,
                    label=str(payload.get("label") or "") or None,
                    detail=str(payload.get("detail") or "") or None,
                    percent=payload.get("percent") if isinstance(payload.get("percent"), (int, float)) else None,
                )

            downloads_dir = download_urls(
                ["https://www.youtube.com/playlist?list=LL"],
                job_root,
                extract_audio,
                lambda message, kind="info": self.add_log(session_id, message, kind),
                progress=download_progress,
                http_headers=http_headers,
                cookie_file=cookie_file,
            )
            local_save = (
                self._save_downloads_to_folder(session_id, downloads_dir, save_folder_path)
                if save_folder_path
                else None
            )
            self._finish_download_job_success(
                session_id,
                run_id=run_id,
                source_kind="youtube-liked-videos",
                requested_count=1,
                extract_audio=extract_audio,
                downloads_dir=downloads_dir,
                local_save=local_save,
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

    def do_OPTIONS(self) -> None:
        self._ensure_session()
        self.send_response(HTTPStatus.NO_CONTENT)
        self._apply_common_headers()
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Music-Studio-Session")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _ensure_session(self) -> str:
        if self.session_id:
            return self.session_id

        header_session_id = str(self.headers.get("X-Music-Studio-Session") or "").strip()
        if header_session_id:
            self.session_id = header_session_id
            self.state.get_session(header_session_id)
            return header_session_id

        query_session_id = str(
            (urllib.parse.parse_qs(urlparse(self.path).query).get("music_studio_session") or [""])[0]
        ).strip()
        if query_session_id:
            self.session_id = query_session_id
            self.state.get_session(query_session_id)
            return query_session_id

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
        if path == "/app":
            self._serve_static("/desktop.html")
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
            if path == "/api/browser-session":
                raw_cookies = body.get("cookies") if isinstance(body, dict) else None
                if not isinstance(raw_cookies, list):
                    raise RuntimeError("cookies must be provided as an array.")
                payload = self.state.import_browser_session(
                    session_id,
                    cookies=[item for item in raw_cookies if isinstance(item, dict)],
                    user_agent=str(body.get("userAgent") or "") if isinstance(body, dict) else None,
                    accept_language=str(body.get("acceptLanguage") or "") if isinstance(body, dict) else None,
                    source=str(body.get("source") or "chrome-extension") if isinstance(body, dict) else "chrome-extension",
                )
                self._send_json(
                    HTTPStatus.OK,
                    {"ok": True, "message": "Browser session imported.", "browserSession": payload},
                )
                return
            if path == "/api/browser-session/import":
                browser_name = str(body.get("browserName") or "auto") if isinstance(body, dict) else "auto"
                payload = self.state.import_browser_session_from_browser(
                    session_id,
                    browser_name=browser_name,
                )
                self._send_json(
                    HTTPStatus.OK,
                    {"ok": True, "message": "Browser session imported from the local browser.", "browserSession": payload},
                )
                return
            if path == "/api/browser-session/clear":
                self.state.clear_browser_session(session_id)
                self._send_json(HTTPStatus.OK, {"ok": True, "message": "Browser session cleared."})
                return
            if path == "/api/latest-download/save":
                folder_path = str(body.get("folderPath") or "").strip() if isinstance(body, dict) else ""
                if not folder_path:
                    raise RuntimeError("folderPath is required.")
                manifest = self.state.save_latest_download_to_folder(session_id, folder_path)
                self._send_json(
                    HTTPStatus.OK,
                    {"ok": True, "message": "Latest files saved into the chosen folder.", "latestDownload": manifest},
                )
                return
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
                save_folder_path = str(body.get("saveFolderPath") or "").strip() if isinstance(body, dict) else ""
                self.state.start_direct_download(
                    session_id,
                    urls,
                    extract_audio,
                    save_folder_path or None,
                )
                self._send_json(HTTPStatus.ACCEPTED, {"ok": True, "message": "Download job started."})
                return
            if path == "/api/youtube/download-liked":
                extract_audio = bool(body.get("extractAudio")) if isinstance(body, dict) else False
                save_folder_path = str(body.get("saveFolderPath") or "").strip() if isinstance(body, dict) else ""
                self.state.start_liked_videos_download(
                    session_id,
                    extract_audio,
                    save_folder_path or None,
                )
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
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Music-Studio-Session")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

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
    try:
        server = ThreadingHTTPServer((APP_HOST, DEFAULT_PORT), handler)
        return server, int(server.server_address[1])
    except OSError as error:
        raise OSError(
            f"Music Studio needs {APP_HOST}:{DEFAULT_PORT}. Close anything else using that port and try again."
        ) from error


def create_server_instance(state: StudioState | None = None) -> tuple[ThreadingHTTPServer, int, StudioState]:
    resolved_state = state or StudioState()
    handler = partial(StudioHandler, state=resolved_state)
    server, actual_port = _create_server(handler)
    return server, actual_port, resolved_state


def start_server_thread(server: ThreadingHTTPServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def main() -> None:
    server, actual_port, _ = create_server_instance()
    print(f"{APP_NAME} local helper is running at http://{APP_HOST}:{actual_port}")
    print("Run the desktop app to open the native Music Studio window.")
    print(f"Static app assets are loaded from: {PUBLIC_DIR}")
    if OPEN_BROWSER_ON_START and APP_HOST in {"127.0.0.1", "localhost"}:
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
