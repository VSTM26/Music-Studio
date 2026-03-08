from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MANIFEST_NAME = "latest-export.json"
BASE_NAME = "ytmusic-liked-songs"


def _format_run_id(now: datetime | None = None) -> str:
    stamp = now or datetime.now()
    return stamp.strftime("%Y%m%d-%H%M%S")


def _build_track_key(song: dict[str, Any]) -> str:
    source = (
        str(song.get("setVideoId") or "").strip()
        or str(song.get("videoId") or "").strip()
        or "|".join(
            [
                str(song.get("title") or ""),
                str(song.get("artists") or ""),
                str(song.get("duration") or ""),
            ]
        )
    )
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()
    return digest[:16]


def _map_track(song: dict[str, Any], index: int) -> dict[str, Any]:
    video_id = str(song.get("videoId") or "").strip()
    return {
        "index": index,
        "trackKey": _build_track_key(song),
        "title": str(song.get("title") or "").strip(),
        "artists": str(song.get("artists") or "").strip(),
        "meta": str(song.get("meta") or "").strip(),
        "duration": str(song.get("duration") or "").strip(),
        "videoId": video_id,
        "setVideoId": str(song.get("setVideoId") or "").strip(),
        "voteSortValue": song.get("voteSortValue"),
        "videoType": str(song.get("videoType") or "").strip(),
        "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
    }


def write_exports(
    output_dir: Path,
    playlist_title: str,
    reported_count: int | None,
    songs: list[dict[str, Any]],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = _format_run_id()
    rows = [_map_track(song, index + 1) for index, song in enumerate(songs)]

    txt_name = f"{BASE_NAME}-{run_id}.txt"
    csv_name = f"{BASE_NAME}-{run_id}.csv"
    json_name = f"{BASE_NAME}-{run_id}.json"

    txt_path = output_dir / txt_name
    csv_path = output_dir / csv_name
    json_path = output_dir / json_name
    manifest_path = output_dir / MANIFEST_NAME

    txt_lines = [
        f"{row['index']}. {row['title']}{f' - {row['artists']}' if row['artists'] else ''}".rstrip()
        for row in rows
    ]
    txt_body = "\n".join(txt_lines)
    txt_path.write_text(f"{txt_body}\n" if txt_body else "", encoding="utf-8")

    headers = [
        "index",
        "trackKey",
        "title",
        "artists",
        "meta",
        "duration",
        "videoId",
        "setVideoId",
        "voteSortValue",
        "videoType",
        "url",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    exported_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    json_payload = {
        "exportedAt": exported_at,
        "source": "YouTube Music Liked Music (browser playlist scrape)",
        "playlistId": "LM",
        "title": playlist_title,
        "reportedTrackCount": reported_count,
        "exportedCount": len(rows),
        "tracks": rows,
    }
    json_body = json.dumps(json_payload, indent=2, ensure_ascii=False)
    json_path.write_text(f"{json_body}\n", encoding="utf-8")

    manifest = {
        "runId": run_id,
        "exportedAt": exported_at,
        "title": playlist_title,
        "reportedTrackCount": reported_count,
        "exportedCount": len(rows),
        "mismatchCount": (reported_count - len(rows)) if isinstance(reported_count, int) else None,
        "jsonFileName": json_name,
        "files": [
            {"name": txt_name, "sizeBytes": txt_path.stat().st_size},
            {"name": csv_name, "sizeBytes": csv_path.stat().st_size},
            {"name": json_name, "sizeBytes": json_path.stat().st_size},
        ],
    }
    manifest_path.write_text(f"{json.dumps(manifest, indent=2)}\n", encoding="utf-8")
    return manifest


def load_manifest(output_dir: Path) -> dict[str, Any] | None:
    manifest_path = output_dir / MANIFEST_NAME
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def load_latest_results(output_dir: Path) -> dict[str, Any] | None:
    manifest = load_manifest(output_dir)
    if manifest and manifest.get("jsonFileName"):
        payload_path = output_dir / str(manifest["jsonFileName"])
        if payload_path.exists():
            return json.loads(payload_path.read_text(encoding="utf-8"))

    fallback = output_dir / f"{BASE_NAME}.json"
    if fallback.exists():
        return json.loads(fallback.read_text(encoding="utf-8"))
    return None
