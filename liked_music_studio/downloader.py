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
from urllib.parse import urlparse

from .devtools import ChromeDebugError, export_source_cookies

BASE_DIR = Path(__file__).resolve().parents[1]
GUIDED_CHROME_PROFILE_DIR = BASE_DIR / "runtime" / "chrome-profile"
FFMPEG_TOOL_DIR = BASE_DIR / "runtime" / "tools" / "ffmpeg"
COOKIE_EXPORT_DIR = BASE_DIR / "runtime" / "cookies"
YTDLP_COOKIE_FILE = COOKIE_EXPORT_DIR / "ytmusic-cookies.txt"
DEBUG_HOST = os.environ.get("YTMUSIC_DEBUG_HOST", "127.0.0.1")
DEBUG_PORT = int(os.environ.get("YTMUSIC_DEBUG_PORT", "9224"))
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

    # Fallback to common winget installation paths on Windows
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

    # Fallback to common winget installation paths on Windows
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

    # Search for yt-dlp.FFmpeg or Gyan.FFmpeg folders
    suffix = ".exe" if os.name == "nt" else ""
    for package_dir in winget_root.glob("*FFmpeg*"):
        for bin_path in package_dir.rglob(f"bin/{tool_name}{suffix}"):
            if bin_path.exists():
                return bin_path
        # Some packages might have it directly or in other subfolders
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

    log(
        "Trying a portable FFmpeg download into the app runtime folder so MP3 extraction can work without a separate install.",
        "info",
    )
    try:
        release_request = urllib.request.Request(
            "https://api.github.com/repos/eugeneware/ffmpeg-static/releases/latest",
            headers=GITHUB_API_HEADERS,
        )
        with urllib.request.urlopen(release_request, timeout=30) as response:
            release_data = json.load(response)

        assets = {asset.get("name"): asset.get("browser_download_url") for asset in release_data.get("assets", [])}
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
        log(
            "MP3 extraction needs both ffmpeg and ffprobe. Trying to install them automatically.",
            "info",
        )

    if _try_auto_install_ffmpeg(log):
        ffmpeg_path, ffmpeg_mode = _resolve_ffmpeg_path(require_binary=True)
        ffprobe_path, _ = _resolve_ffprobe_path()
        if ffmpeg_path and ffprobe_path:
            log("FFmpeg and ffprobe are now available for audio extraction.", "success")
            return ffmpeg_path

    raise RuntimeError(
        "MP3 extraction needs both ffmpeg and ffprobe. Music Studio tried automatic system install and a portable download, "
        "but neither finished successfully. On Windows, install FFmpeg with `winget install --id yt-dlp.FFmpeg --exact`. "
        "On macOS, install it with `brew install ffmpeg`."
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

def _has_guided_chrome_cookies(profile_dir: Path) -> bool:
    if not profile_dir.exists():
        return False
    if (profile_dir / "Local State").exists():
        return True
    cookie_candidates = (
        profile_dir / "Default" / "Cookies",
        profile_dir / "Default" / "Network" / "Cookies",
        profile_dir / "Profile 1" / "Cookies",
        profile_dir / "Profile 1" / "Network" / "Cookies",
    )
    return any(candidate.exists() for candidate in cookie_candidates)


def _netscape_cookie_domain(cookie: dict[str, Any]) -> str:
    domain = str(cookie.get("domain") or "").strip()
    if not domain:
        return domain
    if bool(cookie.get("httpOnly")) and not domain.startswith("#HttpOnly_"):
        return f"#HttpOnly_{domain}"
    return domain


def _cookie_domain_for_scope(domain: str) -> str:
    return domain[len("#HttpOnly_") :] if domain.startswith("#HttpOnly_") else domain


def _write_netscape_cookie_file(cookies: list[dict[str, Any]], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Netscape HTTP Cookie File",
        "# Exported by Music Studio from the Guided Chrome session.",
    ]
    for cookie in cookies:
        name = str(cookie.get("name") or "").replace("\t", " ").replace("\r", " ").replace("\n", " ")
        value = str(cookie.get("value") or "").replace("\t", " ").replace("\r", " ").replace("\n", " ")
        domain = _netscape_cookie_domain(cookie)
        if not name or not domain:
            continue
        include_subdomains = "TRUE" if _cookie_domain_for_scope(domain).startswith(".") else "FALSE"
        path = str(cookie.get("path") or "/").replace("\t", " ").replace("\r", " ").replace("\n", " ")
        secure = "TRUE" if bool(cookie.get("secure")) else "FALSE"
        expires_raw = cookie.get("expires")
        expires = str(max(int(float(expires_raw or 0)), 0))
        lines.append(
            "\t".join([domain, include_subdomains, path, secure, expires, name, value])
        )
    destination.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return destination


def _export_guided_cookie_file(log: Callable[[str, str], None]) -> Path | None:
    try:
        cookies = export_source_cookies("ytmusic", DEBUG_HOST, DEBUG_PORT)
    except ChromeDebugError as error:
        log(
            f"Guided Chrome cookie export was unavailable, so yt-dlp will fall back to direct browser cookies. {error}",
            "info",
        )
        return None
    except Exception as error:
        log(
            f"Guided Chrome cookie export failed unexpectedly, so yt-dlp will fall back to direct browser cookies. {error}",
            "info",
        )
        return None

    if not cookies:
        log(
            "Guided Chrome is connected, but no YouTube cookies were available yet. Sign in there first if a track needs authentication.",
            "info",
        )
        return None

    cookie_file = _write_netscape_cookie_file(cookies, YTDLP_COOKIE_FILE)
    log(
        "Exported cookies from the Guided Chrome session for yt-dlp, which avoids Chrome cookie database copy errors.",
        "info",
    )
    return cookie_file


def _is_youtube_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    return any(
        host == candidate or host.endswith(f".{candidate}")
        for candidate in ("youtube.com", "youtu.be", "music.youtube.com")
    )


def _build_cookie_options(log: Callable[[str, str], None], urls: list[str]) -> dict[str, Any]:
    if not any(_is_youtube_url(url) for url in urls):
        return {}

    cookie_file = _export_guided_cookie_file(log)
    if cookie_file:
        return {"cookiefile": str(cookie_file)}

    log(
        "Direct downloads will proceed without cookies because Guided Chrome is closed or unavailable. "
        "If your download fails because it requires Sign In, reopen Guided Chrome and stay signed in.",
        "info",
    )
    return {}


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
        upper = text.upper()
        self._log(text, kind)
        if "SIGN IN TO CONFIRM YOUR AGE" in upper or "USE --COOKIES-FROM-BROWSER" in upper:
            self._log(
                "YouTube wants an authenticated browser session. Make sure you're signed into YouTube in your Chrome browser, then retry the download.",
                "error",
            )
        if "COULD NOT COPY CHROME COOKIE DATABASE" in upper or "FAILED TO LOAD COOKIES" in upper:
            self._log(
                "yt-dlp could not read Chrome's cookie database. Check that Chrome is closed, then retry the download.",
                "error",
            )


def _build_progress_hook(log: Callable[[str, str], None]) -> Callable[[dict[str, Any]], None]:
    seen_messages: set[str] = set()

    def hook(update: dict[str, Any]) -> None:
        status = str(update.get("status") or "")
        if status == "finished":
            filename = str(update.get("filename") or "").strip()
            if filename:
                log(f"Finished downloading {Path(filename).name}", "success")
            return

        if status != "downloading":
            return

        percent = str(update.get("_percent_str") or "").strip()
        speed = str(update.get("_speed_str") or "").strip()
        eta = str(update.get("_eta_str") or "").strip()
        filename = str(update.get("filename") or update.get("info_dict", {}).get("title") or "").strip()
        parts = [part for part in [percent, speed, eta] if part]
        summary = " ".join(parts)
        message = f"Downloading {Path(filename).name if filename else 'track'} {summary}".strip()
        if message and message not in seen_messages:
            seen_messages.add(message)
            log(message, "info")

    return hook


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
    callback(
        {
            "label": label,
            "detail": detail,
            "percent": percent,
        }
    )


def _build_download_progress_hook(
    total_urls: int,
    log: Callable[[str, str], None],
    progress: ProgressCallback | None,
) -> Callable[[dict[str, Any]], None]:
    base_hook = _build_progress_hook(log)
    finished_ids: set[str] = set()
    state = {"completed": 0}

    def hook(update: dict[str, Any]) -> None:
        base_hook(update)
        status = str(update.get("status") or "")
        info = update.get("info_dict") if isinstance(update.get("info_dict"), dict) else {}
        title = str(info.get("title") or update.get("filename") or "track").strip()

        if status == "finished":
            marker = str(info.get("id") or update.get("filename") or title)
            if marker not in finished_ids:
                finished_ids.add(marker)
                state["completed"] += 1
            overall = min(100.0, (state["completed"] / max(total_urls, 1)) * 100.0)
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
) -> Path:
    normalized_urls = _normalize_urls(urls)
    if not normalized_urls:
        raise RuntimeError("Add at least one valid URL before starting a download.")

    try:
        from yt_dlp import YoutubeDL
    except Exception as error:
        raise RuntimeError(
            "yt-dlp is not available yet. Run the launcher again so dependencies can install."
        ) from error

    ffmpeg_path = _ensure_audio_toolchain(log) if extract_audio else None
    cookie_options = _build_cookie_options(log, normalized_urls)

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
    ydl_options.update(cookie_options)
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
) -> Path:
    if any(track.get("sourcePlatform") != "ytmusic" for track in tracks):
        raise RuntimeError(
            "Downloads are only supported for YouTube Music exports. Spotify exports stay metadata-only."
        )

    urls = [track.get("url") for track in tracks if isinstance(track.get("url"), str) and track["url"]]
    if not urls:
        raise RuntimeError("No downloadable YouTube URLs were found in the selected tracks.")

    return _download_url_batch(urls, output_dir, extract_audio, log, progress)


def download_urls(
    urls: list[str],
    output_dir: Path,
    extract_audio: bool,
    log: Callable[[str, str], None],
    progress: ProgressCallback | None = None,
) -> Path:
    return _download_url_batch(urls, output_dir, extract_audio, log, progress)
