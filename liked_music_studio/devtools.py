from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from websocket import WebSocketTimeoutException, create_connection


PLAYLIST_URL = "https://music.youtube.com/playlist?list=LM"


class ChromeDebugError(RuntimeError):
    """Raised when the Chrome DevTools session is unavailable or invalid."""


def _get_json(url: str, timeout: float = 5.0) -> dict[str, Any] | list[Any]:
    try:
        with urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise ChromeDebugError(f"Chrome debug endpoint returned HTTP {error.code}.") from error
    except URLError as error:
        raise ChromeDebugError(str(error.reason)) from error


def get_debug_status(host: str, port: int) -> dict[str, Any]:
    try:
        version = _get_json(f"http://{host}:{port}/json/version")
        targets = _get_json(f"http://{host}:{port}/json/list")
        music_target = next(
            (
                target
                for target in targets
                if isinstance(target, dict)
                and isinstance(target.get("url"), str)
                and target["url"].startswith("https://music.youtube.com")
            ),
            None,
        )
        page_count = sum(
            1
            for target in targets
            if isinstance(target, dict) and target.get("type") == "page"
        )
        return {
            "connected": True,
            "browser": version.get("Browser"),
            "musicTabOpen": bool(music_target),
            "musicTabTitle": music_target.get("title") if music_target else None,
            "pageCount": page_count,
        }
    except ChromeDebugError as error:
        return {
            "connected": False,
            "browser": None,
            "musicTabOpen": False,
            "musicTabTitle": None,
            "pageCount": 0,
            "message": str(error),
        }


@dataclass
class ScrapeResult:
    playlist_title: str
    reported_count: int | None
    songs: list[dict[str, Any]]


class DevToolsConnection:
    def __init__(self, host: str, port: int, timeout: float = 15.0) -> None:
        version = _get_json(f"http://{host}:{port}/json/version", timeout=timeout)
        ws_url = version.get("webSocketDebuggerUrl")
        if not isinstance(ws_url, str) or not ws_url:
            raise ChromeDebugError("Chrome did not provide a browser WebSocket URL.")
        self._socket = create_connection(ws_url, timeout=timeout)
        self._socket.settimeout(timeout)
        self._next_id = 1

    def close(self) -> None:
        try:
            self._socket.close()
        except Exception:
            pass

    def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        message_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {
            "id": message_id,
            "method": method,
            "params": params or {},
        }
        if session_id:
            payload["sessionId"] = session_id
        self._socket.send(json.dumps(payload))

        while True:
            try:
                raw = self._socket.recv()
            except WebSocketTimeoutException as error:
                raise ChromeDebugError("Timed out waiting for Chrome DevTools.") from error

            message = json.loads(raw)
            if message.get("id") != message_id:
                continue
            if "error" in message:
                raise ChromeDebugError(json.dumps(message["error"]))
            return message.get("result", {})

    def create_target(self, url: str) -> str:
        result = self.send("Target.createTarget", {"url": url})
        target_id = result.get("targetId")
        if not isinstance(target_id, str) or not target_id:
            raise ChromeDebugError("Chrome did not return a target id.")
        return target_id

    def attach_to_target(self, target_id: str) -> str:
        result = self.send("Target.attachToTarget", {"targetId": target_id, "flatten": True})
        session_id = result.get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            raise ChromeDebugError("Chrome did not return a session id.")
        return session_id

    def close_target(self, target_id: str) -> None:
        try:
            self.send("Target.closeTarget", {"targetId": target_id})
        except ChromeDebugError:
            pass

    def evaluate(self, session_id: str, expression: str) -> Any:
        result = self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
            session_id=session_id,
        )
        if result.get("exceptionDetails"):
            details = result["exceptionDetails"]
            raise ChromeDebugError(details.get("text") or "Runtime.evaluate failed.")
        return result.get("result", {}).get("value")

    def wheel_down(self, session_id: str, delta_y: int = 720) -> None:
        self.send(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseWheel",
                "x": 700,
                "y": 900,
                "deltaX": 0,
                "deltaY": delta_y,
                "pointerType": "mouse",
            },
            session_id=session_id,
        )


def _build_snapshot_expression() -> str:
    return r"""
(() => {
  const parseRuns = (runs) =>
    (runs || [])
      .map((run) => run.text || '')
      .join('')
      .replace(/\s+/g, ' ')
      .trim();

  const items = Array.from(
    document.querySelectorAll('ytmusic-responsive-list-item-renderer'),
  ).map((el) => {
    const data = el.data || {};
    const titleRuns =
      data.flexColumns?.[0]?.musicResponsiveListItemFlexColumnRenderer?.text?.runs || [];
    const artistRuns =
      data.flexColumns?.[1]?.musicResponsiveListItemFlexColumnRenderer?.text?.runs || [];
    const metaRuns =
      data.flexColumns?.[2]?.musicResponsiveListItemFlexColumnRenderer?.text?.runs || [];
    const durationRuns =
      data.fixedColumns?.[0]?.musicResponsiveListItemFixedColumnRenderer?.text?.runs || [];
    const playlistData = data.playlistItemData || {};
    const videoType =
      data.overlay?.musicItemThumbnailOverlayRenderer?.content?.musicPlayButtonRenderer
        ?.playNavigationEndpoint?.watchEndpointMusicSupportedConfigs
        ?.watchEndpointMusicConfig?.musicVideoType || null;

    return {
      title: parseRuns(titleRuns),
      artists: parseRuns(artistRuns),
      meta: parseRuns(metaRuns),
      duration: parseRuns(durationRuns),
      videoId: playlistData.videoId || '',
      setVideoId: playlistData.playlistSetVideoId || '',
      voteSortValue: playlistData.voteSortValue || null,
      videoType,
    };
  });

  const scroller = document.scrollingElement || document.documentElement;
  const pageText = document.body?.innerText || '';
  const countMatch = pageText.match(/([0-9,]+)\s+songs\b/i);
  const titleMatch = pageText.match(/^(Liked Music)\b/m);

  return {
    reportedCount: countMatch ? Number(countMatch[1].replace(/,/g, '')) : null,
    playlistTitle: titleMatch ? titleMatch[1] : 'Liked Music',
    scrollTop: scroller ? scroller.scrollTop : 0,
    scrollHeight: scroller ? scroller.scrollHeight : 0,
    clientHeight: scroller ? scroller.clientHeight : 0,
    domCount: items.length,
    items,
  };
})()
""".strip()


def _wait_for_playlist(
    connection: DevToolsConnection,
    session_id: str,
    timeout_seconds: float = 45.0,
) -> dict[str, Any]:
    started_at = time.monotonic()
    expression = _build_snapshot_expression()
    while time.monotonic() - started_at < timeout_seconds:
        snapshot = connection.evaluate(session_id, expression)
        if isinstance(snapshot, dict) and int(snapshot.get("domCount") or 0) > 0:
            return snapshot
        time.sleep(0.6)
    raise ChromeDebugError(
        "Timed out waiting for the Liked Music page. Sign in inside Guided Chrome first."
    )


def _collect_songs(
    connection: DevToolsConnection,
    session_id: str,
    log: Callable[[str, str], None],
) -> ScrapeResult:
    songs: dict[str, dict[str, Any]] = {}
    reported_count: int | None = None
    playlist_title = "Liked Music"
    stable_at_bottom = 0
    last_count = 0
    expression = _build_snapshot_expression()

    for iteration in range(1, 401):
        snapshot = connection.evaluate(session_id, expression)
        if not isinstance(snapshot, dict):
            raise ChromeDebugError("Chrome returned an empty playlist snapshot.")

        if isinstance(snapshot.get("reportedCount"), int):
            reported_count = snapshot["reportedCount"]
        if isinstance(snapshot.get("playlistTitle"), str) and snapshot["playlistTitle"]:
            playlist_title = snapshot["playlistTitle"]

        for item in snapshot.get("items", []):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            key = (
                str(item.get("setVideoId") or "").strip()
                or str(item.get("videoId") or "").strip()
                or f"{title}|{item.get('artists', '')}|{item.get('duration', '')}"
            )
            songs.setdefault(key, item)

        current_count = len(songs)
        if iteration == 1 or current_count != last_count:
            log(f"Playlist scan is at {current_count} discovered tracks.", "info")

        if reported_count and current_count >= reported_count:
            break

        scroll_top = int(snapshot.get("scrollTop") or 0)
        client_height = int(snapshot.get("clientHeight") or 0)
        scroll_height = int(snapshot.get("scrollHeight") or 0)
        near_bottom = scroll_top + client_height >= scroll_height - 96

        if near_bottom and current_count == last_count:
            stable_at_bottom += 1
        else:
            stable_at_bottom = 0

        if stable_at_bottom >= 8:
            break

        last_count = current_count
        connection.wheel_down(session_id)
        time.sleep(0.7)

    return ScrapeResult(
        playlist_title=playlist_title,
        reported_count=reported_count,
        songs=list(songs.values()),
    )


def scrape_liked_music(
    host: str,
    port: int,
    log: Callable[[str, str], None],
) -> ScrapeResult:
    connection = DevToolsConnection(host, port)
    target_id: str | None = None

    try:
        target_id = connection.create_target(PLAYLIST_URL)
        session_id = connection.attach_to_target(target_id)
        connection.send("Page.enable", session_id=session_id)
        connection.send("Runtime.enable", session_id=session_id)
        log("Opened a fresh Liked Music tab inside the guided Chrome session.", "info")
        _wait_for_playlist(connection, session_id)
        return _collect_songs(connection, session_id, log)
    finally:
        if target_id:
            connection.close_target(target_id)
        connection.close()
