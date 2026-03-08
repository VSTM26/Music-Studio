from __future__ import annotations

import json
import mimetypes
import os
import shutil
import subprocess
import threading
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from . import APP_NAME, APP_VERSION
from .devtools import (
    ChromeDebugError,
    SOURCE_LABELS,
    SOURCE_URLS,
    get_debug_status,
    scrape_source,
)
from .downloader import download_tracks, get_tool_status
from .exports import load_latest_results, load_manifest, write_exports


BASE_DIR = Path(__file__).resolve().parents[1]
PUBLIC_DIR = BASE_DIR / "public"
DEFAULT_OUTPUT_DIR = BASE_DIR / "output"
RUNTIME_DIR = BASE_DIR / "runtime"
CHROME_PROFILE_DIR = RUNTIME_DIR / "chrome-profile"
APP_HOST = os.environ.get("APP_HOST", "127.0.0.1")
DEBUG_HOST = os.environ.get("YTMUSIC_DEBUG_HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "4173"))
DEBUG_PORT = int(os.environ.get("YTMUSIC_DEBUG_PORT", "9224"))
APP_URL = f"http://{APP_HOST}:{PORT}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _build_remote_allow_origins(host: str, port: int) -> str:
    hosts = {host.strip(), "127.0.0.1", "localhost"}
    origins: list[str] = []
    for item in sorted(candidate for candidate in hosts if candidate):
        origins.append(f"http://{item}:{port}")
        origins.append(f"ws://{item}:{port}")
    return ",".join(origins)


@dataclass
class JobState:
    running: bool = False
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_error: str | None = None
    last_exit_code: int | None = None
    requested_count: int | None = None
    mode: str | None = None


class StudioState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.logs: list[dict[str, str]] = []
        self.export = JobState()
        self.download = JobState()
        self.output_dir = DEFAULT_OUTPUT_DIR
        self.active_source = "ytmusic"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    def add_log(self, message: str, kind: str = "info") -> None:
        with self.lock:
            self.logs.append(
                {
                    "id": f"{threading.get_ident()}-{len(self.logs) + 1}",
                    "kind": kind,
                    "message": message,
                    "timestamp": _utc_now(),
                }
            )
            if len(self.logs) > 220:
                self.logs = self.logs[-220:]

    def get_chrome_path(self) -> str | None:
        candidates = [
            os.environ.get("CHROME_PATH"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            str(
                Path(os.environ.get("LOCALAPPDATA", ""))
                / "Google"
                / "Chrome"
                / "Application"
                / "chrome.exe"
            ),
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            str(
                Path.home()
                / "Applications"
                / "Google Chrome.app"
                / "Contents"
                / "MacOS"
                / "Google Chrome"
            ),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return candidate
        return None

    def build_status_payload(self) -> dict[str, Any]:
        with self.lock:
            export_state = JobState(**self.export.__dict__)
            download_state = JobState(**self.download.__dict__)
            logs = list(self.logs)
            active_source = self.active_source

        chrome_path = self.get_chrome_path()
        return {
            "app": {
                "name": APP_NAME,
                "version": APP_VERSION,
                "port": PORT,
                "url": APP_URL,
            },
            "sources": {
                "active": active_source,
                "labels": SOURCE_LABELS,
            },
            "privacy": {
                "usesApiKeys": False,
                "browserSessionOnly": True,
            },
            "chrome": {
                "found": bool(chrome_path),
                "path": chrome_path,
                "profileDir": str(CHROME_PROFILE_DIR),
            },
            "debug": get_debug_status(DEBUG_HOST, DEBUG_PORT),
            "output": {
                "directory": str(self.output_dir),
                "downloadsDirectory": str(self.output_dir / "downloads"),
            },
            "tools": get_tool_status(),
            "export": export_state.__dict__,
            "download": download_state.__dict__,
            "latestExport": self.get_latest_export(),
            "logs": logs,
        }

    def get_latest_export(self) -> dict[str, Any] | None:
        manifest = load_manifest(self.output_dir)
        if not manifest:
            return None
        source_platform = str(manifest.get("sourcePlatform") or "").strip() or "ytmusic"
        source_label = str(manifest.get("sourceLabel") or "").strip() or SOURCE_LABELS[source_platform]
        files = []
        for file_info in manifest.get("files", []):
            if not isinstance(file_info, dict):
                continue
            name = str(file_info.get("name") or "")
            if not name:
                continue
            files.append(
                {
                    "name": name,
                    "sizeBytes": file_info.get("sizeBytes"),
                    "url": f"/downloads/{name}",
                }
            )
        return {
            "title": manifest.get("title"),
            "sourcePlatform": source_platform,
            "sourceLabel": source_label,
            "downloadSupported": bool(
                manifest.get("downloadSupported")
                if "downloadSupported" in manifest
                else source_platform == "ytmusic"
            ),
            "exportedAt": manifest.get("exportedAt"),
            "reportedTrackCount": manifest.get("reportedTrackCount"),
            "exportedCount": manifest.get("exportedCount"),
            "mismatchCount": manifest.get("mismatchCount"),
            "jsonFileName": manifest.get("jsonFileName"),
            "files": files,
        }

    def get_results(self) -> dict[str, Any] | None:
        return load_latest_results(self.output_dir)

    def set_source(self, source: str) -> None:
        if source not in SOURCE_LABELS:
            raise RuntimeError("Unsupported export source.")
        with self.lock:
            self.active_source = source
        self.add_log(f"Switched source to {SOURCE_LABELS[source]}.", "info")

    def launch_guided_chrome(self) -> str:
        chrome_path = self.get_chrome_path()
        if not chrome_path:
            raise RuntimeError("Chrome was not found. Install Chrome or set CHROME_PATH.")

        with self.lock:
            source = self.active_source
        source_label = SOURCE_LABELS[source]
        source_url = SOURCE_URLS[source]

        CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        args = [
            chrome_path,
            f"--remote-debugging-port={DEBUG_PORT}",
            "--remote-debugging-address=127.0.0.1",
            f"--remote-allow-origins={_build_remote_allow_origins(DEBUG_HOST, DEBUG_PORT)}",
            f"--user-data-dir={CHROME_PROFILE_DIR}",
            "--new-window",
            "--disable-first-run-ui",
            "--no-default-browser-check",
            source_url,
        ]
        popen_kwargs: dict[str, Any] = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if os.name == "nt":
            creationflags = (
                getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )
            popen_kwargs["creationflags"] = creationflags
        else:
            popen_kwargs["start_new_session"] = True
        subprocess.Popen(args, **popen_kwargs)
        self.add_log(f"Opened Guided Chrome on {source_label}.", "success")
        return chrome_path

    def reset_guided_session(self) -> None:
        if self.export.running:
            raise RuntimeError("Wait for the current export to finish before resetting the session.")
        debug = get_debug_status(DEBUG_HOST, DEBUG_PORT)
        if debug.get("connected"):
            raise RuntimeError(
                "Close the Guided Chrome window first, then reset the session to switch accounts."
            )
        shutil.rmtree(CHROME_PROFILE_DIR, ignore_errors=True)
        self.add_log("Cleared the dedicated Chrome profile for the next sign-in.", "info")

    def select_output_directory(self) -> str:
        try:
            import tkinter as tk
            from tkinter import filedialog
        except Exception as error:
            raise RuntimeError(f"Folder picker is unavailable: {error}") from error

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        selected = filedialog.askdirectory(
            title="Choose a save folder for exports and downloads",
            initialdir=str(self.output_dir),
            mustexist=True,
        )
        root.destroy()
        if selected:
            self.output_dir = Path(selected)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.add_log(f"Save folder changed to {self.output_dir}", "success")
        return str(self.output_dir)

    def start_export(self) -> None:
        with self.lock:
            if self.export.running:
                raise RuntimeError("An export is already running.")
            self.export.running = True
            self.export.last_started_at = _utc_now()
            self.export.last_finished_at = None
            self.export.last_error = None
            self.export.last_exit_code = None
            self.export.requested_count = None
            self.export.mode = self.active_source
        threading.Thread(target=self._run_export_job, daemon=True).start()

    def _run_export_job(self) -> None:
        with self.lock:
            source = self.active_source
        source_label = SOURCE_LABELS[source]
        self.add_log(f"Starting the browser scrape for {source_label}.", "info")
        try:
            scrape_result = scrape_source(source, DEBUG_HOST, DEBUG_PORT, self.add_log)
            manifest = write_exports(
                self.output_dir,
                scrape_result.source_platform,
                scrape_result.playlist_title,
                scrape_result.reported_count,
                scrape_result.songs,
                scrape_result.download_supported,
            )
            with self.lock:
                self.export.running = False
                self.export.last_finished_at = _utc_now()
                self.export.last_exit_code = 0
            self.add_log(
                f"{scrape_result.source_label} export finished with {manifest['exportedCount']} tracks in {self.output_dir}.",
                "success",
            )
        except Exception as error:
            with self.lock:
                self.export.running = False
                self.export.last_finished_at = _utc_now()
                self.export.last_exit_code = 1
                self.export.last_error = str(error)
            self.add_log(str(error), "error")

    def start_download(self, track_keys: list[str] | None, extract_audio: bool) -> None:
        results = self.get_results()
        if not results:
            raise RuntimeError("Run an export first so the app knows which tracks are available.")
        if not results.get("downloadSupported"):
            raise RuntimeError(
                "This export source is metadata-only here. Downloads are only available for YouTube Music exports."
            )

        tracks = list(results.get("tracks") or [])
        if track_keys:
            wanted = set(track_keys)
            tracks = [track for track in tracks if track.get("trackKey") in wanted]
        if not tracks:
            raise RuntimeError("No matching exported tracks were selected for download.")

        with self.lock:
            if self.download.running:
                raise RuntimeError("A download job is already running.")
            self.download.running = True
            self.download.last_started_at = _utc_now()
            self.download.last_finished_at = None
            self.download.last_error = None
            self.download.last_exit_code = None
            self.download.requested_count = len(tracks)
            self.download.mode = "audio" if extract_audio else "media"
        threading.Thread(
            target=self._run_download_job,
            args=(tracks, extract_audio),
            daemon=True,
        ).start()

    def _run_download_job(self, tracks: list[dict[str, Any]], extract_audio: bool) -> None:
        try:
            downloads_dir = download_tracks(tracks, self.output_dir, extract_audio, self.add_log)
            with self.lock:
                self.download.running = False
                self.download.last_finished_at = _utc_now()
                self.download.last_exit_code = 0
            label = "audio files" if extract_audio else "media files"
            self.add_log(f"Finished downloading {label} into {downloads_dir}.", "success")
        except Exception as error:
            with self.lock:
                self.download.running = False
                self.download.last_finished_at = _utc_now()
                self.download.last_exit_code = 1
                self.download.last_error = str(error)
            self.add_log(str(error), "error")

    def resolve_download(self, file_name: str) -> Path | None:
        safe_name = Path(file_name).name
        candidate = (self.output_dir / safe_name).resolve()
        output_root = self.output_dir.resolve()
        if candidate.parent != output_root or not candidate.exists() or not candidate.is_file():
            return None
        return candidate


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "LikedMusicStudio/0.3"

    def __init__(self, *args: Any, state: StudioState, **kwargs: Any) -> None:
        self.state = state
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/status":
            self._send_json(HTTPStatus.OK, self.state.build_status_payload())
            return
        if path == "/api/results":
            payload = self.state.get_results()
            if payload is None:
                self._send_json(HTTPStatus.NOT_FOUND, {"message": "No export found yet."})
                return
            self._send_json(HTTPStatus.OK, payload)
            return
        if path.startswith("/downloads/"):
            self._serve_download(unquote(path[len("/downloads/") :]))
            return
        self._serve_static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        body = self._read_json()
        try:
            if path == "/api/source":
                source = str(body.get("source") or "")
                self.state.set_source(source)
                self._send_json(
                    HTTPStatus.OK,
                    {"ok": True, "message": "Source updated.", "source": source},
                )
                return
            if path == "/api/launch-browser":
                chrome_path = self.state.launch_guided_chrome()
                self._send_json(
                    HTTPStatus.OK,
                    {"ok": True, "message": "Guided Chrome opened.", "chromePath": chrome_path},
                )
                return
            if path == "/api/export":
                self.state.start_export()
                self._send_json(HTTPStatus.ACCEPTED, {"ok": True, "message": "Export started."})
                return
            if path == "/api/reset-session":
                self.state.reset_guided_session()
                self._send_json(
                    HTTPStatus.OK, {"ok": True, "message": "Guided Chrome profile cleared."}
                )
                return
            if path == "/api/select-output-folder":
                directory = self.state.select_output_directory()
                self._send_json(
                    HTTPStatus.OK,
                    {"ok": True, "message": "Save folder updated.", "directory": directory},
                )
                return
            if path == "/api/download":
                track_keys = body.get("trackKeys") if isinstance(body, dict) else None
                if track_keys is not None and not isinstance(track_keys, list):
                    raise RuntimeError("trackKeys must be an array when provided.")
                extract_audio = bool(body.get("extractAudio")) if isinstance(body, dict) else False
                self.state.start_download(track_keys, extract_audio)
                self._send_json(
                    HTTPStatus.ACCEPTED,
                    {"ok": True, "message": "Download job started."},
                )
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"message": "Not found"})
        except RuntimeError as error:
            self._send_json(HTTPStatus.CONFLICT, {"ok": False, "message": str(error)})
        except ChromeDebugError as error:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "message": str(error)})
        except Exception as error:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "message": str(error)}
            )

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        if not raw.strip():
            return {}
        return json.loads(raw)

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
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
        mime_type, _ = mimetypes.guess_type(file_path.name)
        payload = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime_type or 'application/octet-stream'}; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self._write_body(payload)

    def _serve_download(self, file_name: str) -> None:
        file_path = self.state.resolve_download(file_name)
        if not file_path:
            self._send_text(HTTPStatus.NOT_FOUND, "Not found")
            return
        mime_type, _ = mimetypes.guess_type(file_path.name)
        payload = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header(
            "Content-Type", f"{mime_type or 'application/octet-stream'}; charset=utf-8"
        )
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition", f'attachment; filename="{file_path.name}"')
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self._write_body(payload)

    def _send_text(self, status: HTTPStatus, payload: str) -> None:
        body = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self._write_body(body)

    def _write_body(self, payload: bytes) -> None:
        try:
            self.wfile.write(payload)
        except OSError:
            return


def _open_app() -> None:
    if os.environ.get("NO_OPEN_BROWSER") == "1":
        return
    try:
        webbrowser.open(APP_URL)
    except Exception:
        pass


def main() -> None:
    state = StudioState()
    handler = partial(StudioHandler, state=state)
    server = ThreadingHTTPServer((APP_HOST, PORT), handler)
    state.add_log(f"{APP_NAME} is running at {APP_URL}", "success")
    state.add_log("Both YouTube Music and Spotify exports use the local browser session, not API keys.", "info")
    print(f"{APP_NAME} is running at {APP_URL}")
    _open_app()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
