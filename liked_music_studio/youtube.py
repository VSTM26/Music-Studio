from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from . import oauth


ProgressCallback = Callable[[dict[str, Any]], None]
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


def _emit_progress(
    callback: ProgressCallback | None,
    *,
    label: str,
    detail: str,
    percent: float | None = None,
) -> None:
    if not callback:
        return
    callback({"label": label, "detail": detail, "percent": percent})


def _authorized_get(session_root: Path, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    auth_header = oauth.get_authorization_header(session_root)
    if not auth_header:
        raise RuntimeError("Sign in with Google first.")

    url = f"{YOUTUBE_API_BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": auth_header,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def list_liked_videos(
    session_root: Path,
    progress: ProgressCallback | None = None,
) -> list[dict[str, str]]:
    next_page_token = ""
    collected: list[dict[str, str]] = []
    total_results: int | None = None

    while True:
        params: dict[str, Any] = {
            "part": "snippet,contentDetails",
            "myRating": "like",
            "maxResults": 50,
        }
        if next_page_token:
            params["pageToken"] = next_page_token

        payload = _authorized_get(session_root, "videos", params)
        page_info = payload.get("pageInfo") if isinstance(payload.get("pageInfo"), dict) else {}
        if isinstance(page_info.get("totalResults"), int):
            total_results = int(page_info["totalResults"])

        for item in payload.get("items", []):
            if not isinstance(item, dict):
                continue
            video_id = str(item.get("id") or "").strip()
            snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
            title = str(snippet.get("title") or "").strip() or "Untitled video"
            if not video_id:
                continue
            collected.append(
                {
                    "videoId": video_id,
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                }
            )

        percent = None
        detail = f"Found {len(collected)} liked video(s) so far."
        if total_results and total_results > 0:
            percent = min(100.0, round((len(collected) / total_results) * 100.0, 1))
            detail = f"Found {len(collected)} of about {total_results} liked video(s)."
        _emit_progress(
            progress,
            label="Reading your YouTube likes",
            detail=detail,
            percent=percent,
        )

        next_page_token = str(payload.get("nextPageToken") or "").strip()
        if not next_page_token:
            break

    return collected
