from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import urllib.request
from pathlib import Path
from shutil import which
from typing import Any, Callable

BASE_DIR = Path(__file__).resolve().parents[1]
GUIDED_CHROME_PROFILE_DIR = BASE_DIR / "runtime" / "chrome-profile"
FFMPEG_TOOL_DIR = BASE_DIR / "runtime" / "tools" / "ffmpeg"
GITHUB_API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "Music-Studio",
}


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
    portable_path = _portable_binary_path("ffprobe")
    if portable_path.exists():
        return str(portable_path), "portable"
    return None, None


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


def _build_cookie_arguments(log: Callable[[str, str], None]) -> list[str]:
    if not _has_guided_chrome_cookies(GUIDED_CHROME_PROFILE_DIR):
        log(
            "Guided Chrome cookies were not found yet. Public YouTube tracks may still download, "
            "but age-restricted or private videos need a signed-in Guided Chrome session.",
            "info",
        )
        return []

    log(
        "Using cookies from the Guided Chrome profile so yt-dlp can access signed-in YouTube playback.",
        "info",
    )
    return ["--cookies-from-browser", f"chrome:{GUIDED_CHROME_PROFILE_DIR}"]


def _build_cookie_settings(log: Callable[[str, str], None]) -> tuple[str, str, None, None] | None:
    cookie_args = _build_cookie_arguments(log)
    if not cookie_args:
        return None
    return ("chrome", str(GUIDED_CHROME_PROFILE_DIR), None, None)


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
                "YouTube still wants an authenticated browser session. Reopen Guided Chrome from the app, "
                "make sure you are signed in with the account that can view the track, and then retry the download.",
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


def download_tracks(
    tracks: list[dict[str, Any]],
    output_dir: Path,
    extract_audio: bool,
    log: Callable[[str, str], None],
) -> Path:
    try:
        from yt_dlp import YoutubeDL
    except Exception as error:
        raise RuntimeError(
            "yt-dlp is not available yet. Run the launcher again so dependencies can install."
        ) from error

    if any(track.get("sourcePlatform") != "ytmusic" for track in tracks):
        raise RuntimeError(
            "Downloads are only supported for YouTube Music exports. Spotify exports stay metadata-only."
        )

    urls = [track.get("url") for track in tracks if isinstance(track.get("url"), str) and track["url"]]
    if not urls:
        raise RuntimeError("No downloadable YouTube URLs were found in the selected tracks.")

    ffmpeg_path = _ensure_audio_toolchain(log) if extract_audio else None
    cookie_settings = _build_cookie_settings(log)

    downloads_dir = output_dir / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    logger = _YtDlpLogger(log)
    ydl_options: dict[str, Any] = {
        "ignoreerrors": True,
        "no_warnings": True,
        "paths": {"home": str(downloads_dir)},
        "outtmpl": {"default": "%(title)s [%(id)s].%(ext)s"},
        "logger": logger,
        "progress_hooks": [_build_progress_hook(log)],
    }
    if cookie_settings:
        ydl_options["cookiesfrombrowser"] = cookie_settings
    if extract_audio:
        ydl_options["ffmpeg_location"] = str(Path(ffmpeg_path).parent)
        ydl_options["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            }
        ]

    log(f"Starting yt-dlp for {len(urls)} track(s).", "info")
    with YoutubeDL(ydl_options) as downloader:
        return_code = downloader.download(urls)

    if return_code != 0 or logger.error_count:
        raise RuntimeError(f"yt-dlp exited with code {return_code}.")

    log(f"Downloads saved in {downloads_dir}", "success")
    return downloads_dir
