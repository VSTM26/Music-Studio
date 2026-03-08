from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MANIFEST_NAME = "latest-export.json"
BASE_NAMES = {
    "ytmusic": "ytmusic-liked-songs",
    "spotify": "spotify-liked-songs",
}
SOURCE_LABELS = {
    "ytmusic": "YouTube Music",
    "spotify": "Spotify",
}
SOURCE_EXPORT_DESCRIPTIONS = {
    "ytmusic": "YouTube Music Liked Music (browser playlist scrape)",
    "spotify": "Spotify Liked Songs (browser playlist scrape)",
}


def _format_run_id(now: datetime | None = None) -> str:
    stamp = now or datetime.now()
    return stamp.strftime("%Y%m%d-%H%M%S")


def _build_track_key(source_platform: str, song: dict[str, Any]) -> str:
    source = (
        str(song.get("setVideoId") or "").strip()
        or str(song.get("videoId") or "").strip()
        or str(song.get("trackId") or "").strip()
        or "|".join(
            [
                str(song.get("title") or ""),
                str(song.get("artists") or ""),
                str(song.get("duration") or ""),
            ]
        )
    )
    digest = hashlib.sha1(f"{source_platform}:{source}".encode("utf-8")).hexdigest()
    return digest[:16]


def _map_track(source_platform: str, song: dict[str, Any], index: int) -> dict[str, Any]:
    source_label = SOURCE_LABELS[source_platform]
    if source_platform == "spotify":
        track_id = str(song.get("trackId") or "").strip()
        album = str(song.get("album") or "").strip()
        added_at = str(song.get("addedAt") or "").strip()
        return {
            "index": index,
            "trackKey": _build_track_key(source_platform, song),
            "sourcePlatform": source_platform,
            "sourceLabel": source_label,
            "title": str(song.get("title") or "").strip(),
            "artists": str(song.get("artists") or "").strip(),
            "album": album,
            "meta": str(song.get("meta") or "").strip() or " | ".join(
                value for value in [album, added_at] if value
            ),
            "duration": str(song.get("duration") or "").strip(),
            "externalId": track_id,
            "trackId": track_id,
            "videoId": "",
            "setVideoId": "",
            "addedAt": added_at,
            "videoType": "",
            "trackType": str(song.get("trackType") or "Spotify Saved Track").strip(),
            "url": str(song.get("url") or "").strip(),
        }

    video_id = str(song.get("videoId") or "").strip()
    return {
        "index": index,
        "trackKey": _build_track_key(source_platform, song),
        "sourcePlatform": source_platform,
        "sourceLabel": source_label,
        "title": str(song.get("title") or "").strip(),
        "artists": str(song.get("artists") or "").strip(),
        "album": "",
        "meta": str(song.get("meta") or "").strip(),
        "duration": str(song.get("duration") or "").strip(),
        "externalId": video_id,
        "trackId": "",
        "videoId": video_id,
        "setVideoId": str(song.get("setVideoId") or "").strip(),
        "addedAt": "",
        "videoType": str(song.get("videoType") or "").strip(),
        "trackType": "",
        "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
    }


def write_exports(
    output_dir: Path,
    source_platform: str,
    playlist_title: str,
    reported_count: int | None,
    songs: list[dict[str, Any]],
    download_supported: bool,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = _format_run_id()
    rows = [_map_track(source_platform, song, index + 1) for index, song in enumerate(songs)]
    base_name = BASE_NAMES[source_platform]

    txt_name = f"{base_name}-{run_id}.txt"
    csv_name = f"{base_name}-{run_id}.csv"
    json_name = f"{base_name}-{run_id}.json"

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
        "sourcePlatform",
        "sourceLabel",
        "title",
        "artists",
        "album",
        "meta",
        "duration",
        "externalId",
        "trackId",
        "videoId",
        "setVideoId",
        "addedAt",
        "videoType",
        "trackType",
        "url",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    exported_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    json_payload = {
        "exportedAt": exported_at,
        "source": SOURCE_EXPORT_DESCRIPTIONS[source_platform],
        "sourcePlatform": source_platform,
        "sourceLabel": SOURCE_LABELS[source_platform],
        "downloadSupported": download_supported,
        "playlistId": "LM" if source_platform == "ytmusic" else "spotify-liked-songs",
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
        "sourcePlatform": source_platform,
        "sourceLabel": SOURCE_LABELS[source_platform],
        "downloadSupported": download_supported,
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


def _infer_source_platform(payload: dict[str, Any], file_name: str | None = None) -> str:
    source_platform = str(payload.get("sourcePlatform") or "").strip()
    if source_platform in SOURCE_LABELS:
        return source_platform

    source_text = str(payload.get("source") or "").lower()
    playlist_id = str(payload.get("playlistId") or "").strip()
    candidate = (file_name or "").lower()
    if (
        "youtube music" in source_text
        or playlist_id == "LM"
        or "ytmusic" in candidate
        or "youtube" in candidate
    ):
        return "ytmusic"
    return "spotify"


def _normalize_results_payload(payload: dict[str, Any], file_name: str | None = None) -> dict[str, Any]:
    source_platform = _infer_source_platform(payload, file_name)
    source_label = SOURCE_LABELS[source_platform]
    normalized = dict(payload)
    normalized.setdefault("sourcePlatform", source_platform)
    normalized.setdefault("sourceLabel", source_label)
    normalized.setdefault("downloadSupported", source_platform == "ytmusic")

    tracks = []
    for index, track in enumerate(normalized.get("tracks") or [], start=1):
        if not isinstance(track, dict):
            continue
        updated = dict(track)
        updated.setdefault("index", index)
        updated.setdefault("sourcePlatform", source_platform)
        updated.setdefault("sourceLabel", source_label)
        updated.setdefault("trackKey", _build_track_key(source_platform, updated))
        updated.setdefault("trackType", "Spotify Saved Track" if source_platform == "spotify" else "")
        tracks.append(updated)
    normalized["tracks"] = tracks
    return normalized


def load_latest_results(output_dir: Path) -> dict[str, Any] | None:
    manifest = load_manifest(output_dir)
    if manifest and manifest.get("jsonFileName"):
        payload_path = output_dir / str(manifest["jsonFileName"])
        if payload_path.exists():
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            return _normalize_results_payload(payload, payload_path.name)

    for base_name in BASE_NAMES.values():
        fallback = output_dir / f"{base_name}.json"
        if fallback.exists():
            payload = json.loads(fallback.read_text(encoding="utf-8"))
            return _normalize_results_payload(payload, fallback.name)
    return None
