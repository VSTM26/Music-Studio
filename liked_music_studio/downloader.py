from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from shutil import which
from typing import Any, Callable

from .paths import RUNTIME_DIR

FFMPEG_TOOL_DIR = RUNTIME_DIR / "tools" / "ffmpeg"
GITHUB_API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "Music-Studio",
}
ProgressCallback = Callable[[dict[str, Any]], None]


def _has_module(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


def _resolve_ffmpeg_path(require_binary: bool = False) -> tuple[str | None, str | None]:
    system_path = which("ffmpeg")
    if system_path:
        return system_path, "system"

    if os.name == "nt":
        winget_path = _find_winget_binary("ffmpeg")
        if winget_path:
            return str(winget_path), "winget"

    portable_path = _portable_binary_path("ffmpeg")
    if portable_path.exists():
        return str(portable_path), "portable"

    if _has_module("imageio_ffmpeg"):
        if not require_binary:
            return "imageio-ffmpeg", "bundled-package"
        try:
            from imageio_ffmpeg import get_ffmpeg_exe

            bundled_path = get_ffmpeg_exe()
            if bundled_path:
                return bundled_path, "bundled-package"
        except Exception:
            return None, None

    return None, None


def _resolve_ffprobe_path() -> tuple[str | None, str | None]:
    system_path = which("ffprobe")
    if system_path:
        return system_path, "system"

    if os.name == "nt":
        winget_path = _find_winget_binary("ffprobe")
        if winget_path:
            return str(winget_path), "winget"

    portable_path = _portable_binary_path("ffprobe")
    if portable_path.exists():
        return str(portable_path), "portable"
    return None, None


def _find_winget_binary(tool_name: str) -> Path | None:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    winget_root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
    if not winget_root.exists():
        return None

    suffix = ".exe" if os.name == "nt" else ""
    for package_dir in winget_root.glob("*FFmpeg*"):
        for bin_path in package_dir.rglob(f"bin/{tool_name}{suffix}"):
            if bin_path.exists():
                return bin_path
        for binary in package_dir.rglob(f"{tool_name}{suffix}"):
            if binary.exists():
                return binary
    return None


def _portable_binary_path(tool_name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return FFMPEG_TOOL_DIR / f"{tool_name}{suffix}"


def _portable_asset_names() -> tuple[str, str] | None:
    machine = platform.machine().lower()
    if os.name == "nt":
        if machine in {"amd64", "x86_64"}:
            suffix = "win32-x64"
        else:
            return None
    elif sys.platform == "darwin":
        if machine in {"arm64", "aarch64"}:
            suffix = "darwin-arm64"
        elif machine in {"x86_64", "amd64"}:
            suffix = "darwin-x64"
        else:
            return None
    else:
        if machine in {"x86_64", "amd64"}:
            suffix = "linux-x64"
        elif machine in {"arm64", "aarch64"}:
            suffix = "linux-arm64"
        elif machine.startswith("armv7") or machine == "arm":
            suffix = "linux-arm"
        else:
            return None
    return f"ffmpeg-{suffix}", f"ffprobe-{suffix}"


def _download_to_path(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_name(f"{destination.name}.tmp")
    request = urllib.request.Request(url, headers=GITHUB_API_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=120) as response, temp_path.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        if os.name != "nt":
            temp_path.chmod(0o755)
        temp_path.replace(destination)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _try_install_portable_ffmpeg(log: Callable[[str, str], None]) -> bool:
    asset_names = _portable_asset_names()
    if not asset_names:
        log(
            "Portable FFmpeg downloads are not available for this platform/architecture combination.",
            "info",
        )
        return False

    log("Trying a portable FFmpeg download into the app runtime folder.", "info")
    try:
        release_request = urllib.request.Request(
            "https://api.github.com/repos/eugeneware/ffmpeg-static/releases/latest",
            headers=GITHUB_API_HEADERS,
        )
        with urllib.request.urlopen(release_request, timeout=30) as response:
            release_data = json.load(response)

        assets = {
            asset.get("name"): asset.get("browser_download_url")
            for asset in release_data.get("assets", [])
        }
        for tool_name, asset_name in zip(("ffmpeg", "ffprobe"), asset_names):
            asset_url = assets.get(asset_name)
            if not asset_url:
                log(f"Portable asset `{asset_name}` was not found in the latest FFmpeg release.", "error")
                return False
            destination = _portable_binary_path(tool_name)
            _download_to_path(str(asset_url), destination)
            log(f"Installed portable {tool_name} at {destination}", "success")
        return True
    except Exception as error:
        log(f"Portable FFmpeg download failed: {error}", "error")
        return False


def _run_install_command(
    command: list[str],
    log: Callable[[str, str], None],
    timeout_seconds: int = 900,
) -> bool:
    log(f"Running: {' '.join(command)}", "info")
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
    )

    output_lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    for line in output_lines[-18:]:
        kind = "error" if "ERROR" in line.upper() else "info"
        log(line, kind)
    return completed.returncode == 0


def _try_auto_install_ffmpeg(log: Callable[[str, str], None]) -> bool:
    if os.name == "nt":
        winget = which("winget")
        if winget:
            package_ids = ["yt-dlp.FFmpeg", "Gyan.FFmpeg.Essentials"]
            for package_id in package_ids:
                log(f"Trying to install FFmpeg automatically with winget package `{package_id}`.", "info")
                command = [
                    winget,
                    "install",
                    "--id",
                    package_id,
                    "--exact",
                    "--silent",
                    "--disable-interactivity",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                    "--scope",
                    "user",
                    "--no-upgrade",
                ]
                if _run_install_command(command, log):
                    return True
        else:
            log("`winget` was not found, so the app will try a portable FFmpeg download instead.", "info")
        return _try_install_portable_ffmpeg(log)

    if sys.platform == "darwin":
        brew = which("brew")
        if brew:
            log("Trying to install FFmpeg automatically with Homebrew.", "info")
            if _run_install_command([brew, "install", "ffmpeg"], log):
                return True
        else:
            log("`brew` was not found, so the app will try a portable FFmpeg download instead.", "info")
        return _try_install_portable_ffmpeg(log)

    return _try_install_portable_ffmpeg(log)


def _ensure_audio_toolchain(log: Callable[[str, str], None]) -> str:
    ffmpeg_path, ffmpeg_mode = _resolve_ffmpeg_path(require_binary=True)
    ffprobe_path, _ = _resolve_ffprobe_path()
    if ffmpeg_path and ffprobe_path:
        return ffmpeg_path

    if ffmpeg_mode == "bundled-package" and not ffprobe_path:
        log(
            "A bundled ffmpeg binary is available, but MP3 extraction still needs ffprobe. "
            "Trying to install the full FFmpeg toolchain automatically.",
            "info",
        )
    else:
        log("MP3 extraction needs both ffmpeg and ffprobe. Trying to install them automatically.", "info")

    if _try_auto_install_ffmpeg(log):
        ffmpeg_path, _ = _resolve_ffmpeg_path(require_binary=True)
        ffprobe_path, _ = _resolve_ffprobe_path()
        if ffmpeg_path and ffprobe_path:
            log("FFmpeg and ffprobe are now available for audio extraction.", "success")
            return ffmpeg_path

    raise RuntimeError(
        "MP3 extraction needs both ffmpeg and ffprobe. Music Studio tried automatic installation but it did not finish successfully."
    )


def get_tool_status() -> dict[str, dict[str, Any]]:
    yt_dlp_module = _has_module("yt_dlp")
    yt_dlp_command = which("yt-dlp")
    ffmpeg_path, ffmpeg_mode = _resolve_ffmpeg_path()
    ffprobe_path, ffprobe_mode = _resolve_ffprobe_path()
    return {
        "ytDlp": {
            "available": bool(yt_dlp_module or yt_dlp_command),
            "mode": "python-module" if yt_dlp_module else ("command" if yt_dlp_command else None),
            "path": yt_dlp_command,
        },
        "ffmpeg": {
            "available": bool(ffmpeg_path),
            "mode": ffmpeg_mode,
            "path": ffmpeg_path,
        },
        "ffprobe": {
            "available": bool(ffprobe_path),
            "mode": ffprobe_mode,
            "path": ffprobe_path,
        },
        "audioExtraction": {
            "available": bool(ffmpeg_path and ffprobe_path),
            "mode": ffmpeg_mode if ffmpeg_mode == ffprobe_mode else ("mixed" if ffmpeg_path and ffprobe_path else None),
            "path": ffmpeg_path if ffmpeg_path and ffprobe_path else None,
        },
    }


class _YtDlpLogger:
    def __init__(self, log: Callable[[str, str], None]) -> None:
        self._log = log
        self.error_count = 0

    def debug(self, message: str) -> None:
        self._emit(message)

    def info(self, message: str) -> None:
        self._emit(message)

    def warning(self, message: str) -> None:
        self._emit(message, "info")

    def error(self, message: str) -> None:
        self.error_count += 1
        self._emit(message, "error")

    def _emit(self, message: str, kind: str = "info") -> None:
        text = str(message or "").strip()
        if not text:
            return
        self._log(text, kind)


def _parse_fraction(update: dict[str, Any]) -> float:
    downloaded = update.get("downloaded_bytes")
    total = update.get("total_bytes") or update.get("total_bytes_estimate")
    if isinstance(downloaded, (int, float)) and isinstance(total, (int, float)) and total > 0:
        return max(0.0, min(1.0, float(downloaded) / float(total)))

    percent_text = str(update.get("_percent_str") or "").strip()
    match = re.search(r"(\d+(?:\.\d+)?)", percent_text)
    if match:
        return max(0.0, min(1.0, float(match.group(1)) / 100.0))
    return 0.0


def _emit_progress(
    callback: ProgressCallback | None,
    *,
    label: str,
    detail: str,
    percent: float | None,
) -> None:
    if not callback:
        return
    callback({"label": label, "detail": detail, "percent": percent})


def _build_download_progress_hook(
    total_urls: int,
    log: Callable[[str, str], None],
    progress: ProgressCallback | None,
) -> Callable[[dict[str, Any]], None]:
    seen_messages: set[str] = set()
    finished_ids: set[str] = set()
    state = {"completed": 0}

    def hook(update: dict[str, Any]) -> None:
        status = str(update.get("status") or "")
        info = update.get("info_dict") if isinstance(update.get("info_dict"), dict) else {}
        title = str(info.get("title") or update.get("filename") or "track").strip()

        if status == "finished":
            marker = str(info.get("id") or update.get("filename") or title)
            if marker not in finished_ids:
                finished_ids.add(marker)
                state["completed"] += 1
            overall = min(100.0, (state["completed"] / max(total_urls, 1)) * 100.0)
            log(f"Finished downloading {Path(title).name}", "success")
            _emit_progress(
                progress,
                label=f"Downloaded {state['completed']} of {total_urls}",
                detail=f"Finished {Path(title).name}",
                percent=overall,
            )
            return

        if status != "downloading":
            return

        current_fraction = _parse_fraction(update)
        current_index = min(state["completed"] + 1, total_urls)
        overall = ((state["completed"] + current_fraction) / max(total_urls, 1)) * 100.0
        summary_parts = [
            str(update.get("_percent_str") or "").strip(),
            str(update.get("_speed_str") or "").strip(),
            str(update.get("_eta_str") or "").strip(),
        ]
        summary = " ".join(part for part in summary_parts if part)
        message = f"Downloading {Path(title).name} {summary}".strip()
        if message and message not in seen_messages:
            seen_messages.add(message)
            log(message, "info")
        detail = f"{Path(title).name}"
        if summary:
            detail = f"{detail} | {summary}"
        _emit_progress(
            progress,
            label=f"Downloading {current_index} of {total_urls}",
            detail=detail,
            percent=max(0.0, min(100.0, overall)),
        )

    return hook


def _normalize_urls(urls: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw_url in urls:
        if not isinstance(raw_url, str):
            continue
        url = raw_url.strip()
        if not url or url in seen:
            continue
        cleaned.append(url)
        seen.add(url)
    return cleaned


def _download_url_batch(
    urls: list[str],
    output_dir: Path,
    extract_audio: bool,
    log: Callable[[str, str], None],
    progress: ProgressCallback | None = None,
    http_headers: dict[str, str] | None = None,
    cookie_file: Path | None = None,
) -> Path:
    normalized_urls = _normalize_urls(urls)
    if not normalized_urls:
        raise RuntimeError("Add at least one valid URL before starting a download.")

    try:
        from yt_dlp import YoutubeDL
    except Exception as error:
        raise RuntimeError(
            "yt-dlp is not available yet. Restart the app so dependencies can install."
        ) from error

    ffmpeg_path = _ensure_audio_toolchain(log) if extract_audio else None
    downloads_dir = output_dir / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    logger = _YtDlpLogger(log)
    _emit_progress(
        progress,
        label=f"Preparing {len(normalized_urls)} URL(s)",
        detail="Setting up yt-dlp for this job.",
        percent=0.0,
    )
    ydl_options: dict[str, Any] = {
        "ignoreerrors": True,
        "no_warnings": True,
        "js_runtimes": {"node": {}, "deno": {}},
        "remote_components": ["ejs:github"],
        "paths": {"home": str(downloads_dir)},
        "outtmpl": {"default": "%(title)s [%(id)s].%(ext)s"},
        "logger": logger,
        "progress_hooks": [_build_download_progress_hook(len(normalized_urls), log, progress)],
    }
    if http_headers:
        ydl_options["http_headers"] = dict(http_headers)
    if cookie_file:
        ydl_options["cookiefile"] = str(cookie_file)
    if extract_audio:
        ydl_options["format"] = "bestaudio/best"
        ydl_options["ffmpeg_location"] = str(Path(ffmpeg_path).parent)
        ydl_options["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            }
        ]
    else:
        ydl_options["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"

    log(f"Starting yt-dlp for {len(normalized_urls)} item(s).", "info")
    with YoutubeDL(ydl_options) as downloader:
        return_code = downloader.download(normalized_urls)

    if return_code != 0 or logger.error_count:
        raise RuntimeError(f"yt-dlp exited with code {return_code}.")

    _emit_progress(
        progress,
        label=f"Finished {len(normalized_urls)} of {len(normalized_urls)}",
        detail=f"Downloads saved in {downloads_dir}",
        percent=100.0,
    )
    log(f"Downloads saved in {downloads_dir}", "success")
    return downloads_dir


def download_tracks(
    tracks: list[dict[str, Any]],
    output_dir: Path,
    extract_audio: bool,
    log: Callable[[str, str], None],
    progress: ProgressCallback | None = None,
    http_headers: dict[str, str] | None = None,
    cookie_file: Path | None = None,
) -> Path:
    urls = [track.get("url") for track in tracks if isinstance(track.get("url"), str) and track["url"]]
    if not urls:
        raise RuntimeError("No downloadable URLs were found in the selected tracks.")
    return _download_url_batch(urls, output_dir, extract_audio, log, progress, http_headers, cookie_file)


def download_urls(
    urls: list[str],
    output_dir: Path,
    extract_audio: bool,
    log: Callable[[str, str], None],
    progress: ProgressCallback | None = None,
    http_headers: dict[str, str] | None = None,
    cookie_file: Path | None = None,
) -> Path:
    return _download_url_batch(urls, output_dir, extract_audio, log, progress, http_headers, cookie_file)
