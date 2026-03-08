from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path
from shutil import which
from typing import Any, Callable


def get_tool_status() -> dict[str, dict[str, Any]]:
    yt_dlp_module = importlib.util.find_spec("yt_dlp")
    yt_dlp_command = which("yt-dlp")
    ffmpeg_path = which("ffmpeg")
    return {
        "ytDlp": {
            "available": bool(yt_dlp_module or yt_dlp_command),
            "mode": "python-module" if yt_dlp_module else ("command" if yt_dlp_command else None),
            "path": yt_dlp_command,
        },
        "ffmpeg": {
            "available": bool(ffmpeg_path),
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


def download_tracks(
    tracks: list[dict[str, Any]],
    output_dir: Path,
    extract_audio: bool,
    log: Callable[[str, str], None],
) -> Path:
    urls = [track.get("url") for track in tracks if isinstance(track.get("url"), str) and track["url"]]
    if not urls:
        raise RuntimeError("No downloadable YouTube URLs were found in the selected tracks.")

    if extract_audio and not which("ffmpeg"):
        raise RuntimeError("ffmpeg is required for audio extraction, but it was not found on PATH.")

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
        "--windows-filenames",
        "--no-warnings",
        "--paths",
        str(downloads_dir),
        "-o",
        "%(title)s [%(id)s].%(ext)s",
        "--batch-file",
        str(batch_file),
    ]

    if extract_audio:
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
