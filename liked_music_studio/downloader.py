from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path
from shutil import which
from typing import Any, Callable


BASE_DIR = Path(__file__).resolve().parents[1]
GUIDED_CHROME_PROFILE_DIR = BASE_DIR / "runtime" / "chrome-profile"


def _resolve_ffmpeg_path(require_binary: bool = False) -> tuple[str | None, str | None]:
    system_path = which("ffmpeg")
    if system_path:
        return system_path, "system"

    if importlib.util.find_spec("imageio_ffmpeg"):
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


def get_tool_status() -> dict[str, dict[str, Any]]:
    yt_dlp_module = importlib.util.find_spec("yt_dlp")
    yt_dlp_command = which("yt-dlp")
    ffmpeg_path, ffmpeg_mode = _resolve_ffmpeg_path()
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
    }


def _resolve_yt_dlp_command() -> list[str]:
    if importlib.util.find_spec("yt_dlp"):
        return [sys.executable, "-m", "yt_dlp"]
    command = which("yt-dlp")
    if command:
        return [command]
    raise RuntimeError("yt-dlp is not installed yet. Run `pip install -r requirements.txt` first.")


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


def download_tracks(
    tracks: list[dict[str, Any]],
    output_dir: Path,
    extract_audio: bool,
    log: Callable[[str, str], None],
) -> Path:
    if any(track.get("sourcePlatform") != "ytmusic" for track in tracks):
        raise RuntimeError(
            "Downloads are only supported for YouTube Music exports. Spotify exports stay metadata-only."
        )

    urls = [track.get("url") for track in tracks if isinstance(track.get("url"), str) and track["url"]]
    if not urls:
        raise RuntimeError("No downloadable YouTube URLs were found in the selected tracks.")

    ffmpeg_path, _ = _resolve_ffmpeg_path(require_binary=extract_audio)
    if extract_audio and not ffmpeg_path:
        raise RuntimeError(
            "ffmpeg is required for audio extraction, but it was not available from PATH or imageio-ffmpeg."
        )

    downloads_dir = output_dir / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        suffix=".txt",
        prefix="ytmusic-batch-",
        delete=False,
        dir=downloads_dir,
    ) as handle:
        batch_file = Path(handle.name)
        handle.write("\n".join(urls) + "\n")

    command = _resolve_yt_dlp_command() + [
        "--newline",
        "--ignore-errors",
        "--no-warnings",
        "--paths",
        str(downloads_dir),
        "-o",
        "%(title)s [%(id)s].%(ext)s",
        "--batch-file",
        str(batch_file),
    ]
    command.extend(_build_cookie_arguments(log))

    if extract_audio:
        command.extend(["--ffmpeg-location", str(Path(ffmpeg_path).parent)])
        command.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])

    log(f"Starting yt-dlp for {len(urls)} track(s).", "info")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    try:
        assert process.stdout is not None
        for line in process.stdout:
            message = line.strip()
            if not message:
                continue
            upper = message.upper()
            if "ERROR" in upper:
                kind = "error"
            elif "100%" in upper or "FINISHED" in upper:
                kind = "success"
            else:
                kind = "info"
            log(message, kind)
            if "SIGN IN TO CONFIRM YOUR AGE" in upper or "USE --COOKIES-FROM-BROWSER" in upper:
                log(
                    "YouTube still wants an authenticated browser session. Reopen Guided Chrome from the app, "
                    "make sure you are signed in with the account that can view the track, and then retry the download.",
                    "error",
                )
        return_code = process.wait()
    finally:
        try:
            batch_file.unlink(missing_ok=True)
        except Exception:
            pass

    if return_code != 0:
        raise RuntimeError(f"yt-dlp exited with code {return_code}.")

    log(f"Downloads saved in {downloads_dir}", "success")
    return downloads_dir
