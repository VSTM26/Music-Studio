from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from websocket import WebSocketBadStatusException, WebSocketTimeoutException, create_connection


YTMUSIC_PLAYLIST_URL = "https://music.youtube.com/playlist?list=LM"
SPOTIFY_COLLECTION_URL = "https://open.spotify.com/collection/tracks"
SOURCE_URLS = {
    "ytmusic": YTMUSIC_PLAYLIST_URL,
    "spotify": SPOTIFY_COLLECTION_URL,
}
SOURCE_LABELS = {
    "ytmusic": "YouTube Music",
    "spotify": "Spotify",
}


class ChromeDebugError(RuntimeError):
    """Raised when the Chrome DevTools session is unavailable or invalid."""


@dataclass
class ScrapeResult:
    source_platform: str
    source_label: str
    playlist_title: str
    reported_count: int | None
    songs: list[dict[str, Any]]
    download_supported: bool


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
        ytmusic_target = next(
            (
                target
                for target in targets
                if isinstance(target, dict)
                and isinstance(target.get("url"), str)
                and target["url"].startswith("https://music.youtube.com")
            ),
            None,
        )
        spotify_target = next(
            (
                target
                for target in targets
                if isinstance(target, dict)
                and isinstance(target.get("url"), str)
                and target["url"].startswith("https://open.spotify.com")
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
            "ytmusicTabOpen": bool(ytmusic_target),
            "ytmusicTabTitle": ytmusic_target.get("title") if ytmusic_target else None,
            "spotifyTabOpen": bool(spotify_target),
            "spotifyTabTitle": spotify_target.get("title") if spotify_target else None,
            "pageCount": page_count,
        }
    except ChromeDebugError as error:
        return {
            "connected": False,
            "browser": None,
            "ytmusicTabOpen": False,
            "ytmusicTabTitle": None,
            "spotifyTabOpen": False,
            "spotifyTabTitle": None,
            "pageCount": 0,
            "message": str(error),
        }


class DevToolsConnection:
    def __init__(self, host: str, port: int, timeout: float = 15.0) -> None:
        version = _get_json(f"http://{host}:{port}/json/version", timeout=timeout)
        ws_url = version.get("webSocketDebuggerUrl")
        if not isinstance(ws_url, str) or not ws_url:
            raise ChromeDebugError("Chrome did not provide a browser WebSocket URL.")
        try:
            self._socket = create_connection(
                ws_url,
                timeout=timeout,
                origin=f"http://{host}:{port}",
            )
        except WebSocketBadStatusException as error:
            if error.status_code == 403:
                raise ChromeDebugError(
                    "Chrome rejected the DevTools WebSocket handshake with HTTP 403. "
                    "Close Guided Chrome and reopen it from this app so it starts with the required remote debugging flags."
                ) from error
            raise ChromeDebugError(
                f"Chrome rejected the DevTools WebSocket handshake with HTTP {error.status_code}."
            ) from error
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


def _wait_for_snapshot(
    connection: DevToolsConnection,
    session_id: str,
    expression: str,
    error_message: str,
    timeout_seconds: float = 45.0,
) -> dict[str, Any]:
    started_at = time.monotonic()
    while time.monotonic() - started_at < timeout_seconds:
        snapshot = connection.evaluate(session_id, expression)
        if isinstance(snapshot, dict) and int(snapshot.get("domCount") or 0) > 0:
            return snapshot
        time.sleep(0.6)
    raise ChromeDebugError(error_message)


def _open_source_target(
    connection: DevToolsConnection,
    source: str,
    log: Callable[[str, str], None],
) -> tuple[str, str]:
    url = SOURCE_URLS[source]
    label = SOURCE_LABELS[source]
    target_id = connection.create_target(url)
    session_id = connection.attach_to_target(target_id)
    connection.send("Page.enable", session_id=session_id)
    connection.send("Runtime.enable", session_id=session_id)
    log(f"Opened a fresh {label} tab inside the guided Chrome session.", "info")
    return target_id, session_id


def _build_ytmusic_snapshot_expression() -> str:
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


def _collect_ytmusic_songs(
    connection: DevToolsConnection,
    session_id: str,
    log: Callable[[str, str], None],
) -> ScrapeResult:
    songs: dict[str, dict[str, Any]] = {}
    reported_count: int | None = None
    playlist_title = "Liked Music"
    stable_at_bottom = 0
    last_count = 0
    expression = _build_ytmusic_snapshot_expression()

    for iteration in range(1, 401):
        snapshot = connection.evaluate(session_id, expression)
        if not isinstance(snapshot, dict):
            raise ChromeDebugError("Chrome returned an empty YouTube Music playlist snapshot.")

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
            log(f"YouTube Music scan is at {current_count} discovered tracks.", "info")

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
        source_platform="ytmusic",
        source_label=SOURCE_LABELS["ytmusic"],
        playlist_title=playlist_title,
        reported_count=reported_count,
        songs=list(songs.values()),
        download_supported=True,
    )


def scrape_youtube_liked_music(
    host: str,
    port: int,
    log: Callable[[str, str], None],
) -> ScrapeResult:
    connection = DevToolsConnection(host, port)
    target_id: str | None = None

    try:
        target_id, session_id = _open_source_target(connection, "ytmusic", log)
        _wait_for_snapshot(
            connection,
            session_id,
            _build_ytmusic_snapshot_expression(),
            "Timed out waiting for the YouTube Music Liked Music page. Sign in first.",
        )
        return _collect_ytmusic_songs(connection, session_id, log)
    finally:
        if target_id:
            connection.close_target(target_id)
        connection.close()


def _build_spotify_snapshot_expression() -> str:
    return r"""
(() => {
  const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const rows = Array.from(document.querySelectorAll('[data-testid="tracklist-row"]'));
  const firstRow = rows[0] || null;

  const findScroller = (start) => {
    let node = start;
    while (node) {
      if (node.scrollHeight > node.clientHeight + 100) {
        return node;
      }
      node = node.parentElement;
    }
    return document.scrollingElement || document.documentElement;
  };

  const scroller = findScroller(firstRow);

  const getIdFromHref = (href, segment) => {
    try {
      const url = new URL(href, window.location.origin);
      const parts = url.pathname.split('/').filter(Boolean);
      const index = parts.indexOf(segment);
      return index >= 0 ? (parts[index + 1] || '') : '';
    } catch (error) {
      return '';
    }
  };

  const items = rows.map((row) => {
    const trackLink = row.querySelector('a[href*="/track/"]');
    const artistLinks = Array.from(row.querySelectorAll('a[href*="/artist/"]'));
    const albumLink = row.querySelector('a[href*="/album/"]');
    const cellTexts = Array.from(row.querySelectorAll('[role="gridcell"], [aria-colindex]'))
      .map((cell) => clean(cell.textContent))
      .filter(Boolean);

    const title = clean(trackLink?.textContent);
    const artists = artistLinks.map((link) => clean(link.textContent)).filter(Boolean).join(', ');
    const album = clean(albumLink?.textContent);
    const duration =
      cellTexts.find((value) => /^\d{1,2}:\d{2}(?::\d{2})?$/.test(value)) || '';
    const addedAt =
      cellTexts.find(
        (value) =>
          value &&
          value !== title &&
          value !== artists &&
          value !== album &&
          value !== duration,
      ) || '';

    return {
      title,
      artists,
      album,
      meta: [album, addedAt].filter(Boolean).join(' | '),
      duration,
      trackId: getIdFromHref(trackLink?.href || '', 'track'),
      trackType: 'Spotify Saved Track',
      url: trackLink?.href || '',
      addedAt,
    };
  }).filter((item) => item.title);

  const pageText = document.body?.innerText || '';
  const countMatch =
    pageText.match(/([0-9,]+)\s+saved songs\b/i) ||
    pageText.match(/([0-9,]+)\s+liked songs\b/i) ||
    pageText.match(/([0-9,]+)\s+songs\b/i);

  return {
    reportedCount: countMatch ? Number(countMatch[1].replace(/,/g, '')) : null,
    playlistTitle: clean(document.querySelector('main h1')?.textContent) || 'Liked Songs',
    scrollTop: scroller ? scroller.scrollTop : 0,
    scrollHeight: scroller ? scroller.scrollHeight : 0,
    clientHeight: scroller ? scroller.clientHeight : 0,
    domCount: items.length,
    items,
  };
})()
""".strip()


def _collect_spotify_songs(
    connection: DevToolsConnection,
    session_id: str,
    log: Callable[[str, str], None],
) -> ScrapeResult:
    songs: dict[str, dict[str, Any]] = {}
    reported_count: int | None = None
    playlist_title = "Liked Songs"
    stable_at_bottom = 0
    last_count = 0
    expression = _build_spotify_snapshot_expression()

    for iteration in range(1, 401):
        snapshot = connection.evaluate(session_id, expression)
        if not isinstance(snapshot, dict):
            raise ChromeDebugError("Chrome returned an empty Spotify liked songs snapshot.")

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
                str(item.get("trackId") or "").strip()
                or f"{title}|{item.get('artists', '')}|{item.get('duration', '')}"
            )
            songs.setdefault(key, item)

        current_count = len(songs)
        if iteration == 1 or current_count != last_count:
            log(f"Spotify scan is at {current_count} discovered tracks.", "info")

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

        if stable_at_bottom >= 10:
            break

        last_count = current_count
        connection.wheel_down(session_id)
        time.sleep(0.7)

    return ScrapeResult(
        source_platform="spotify",
        source_label=SOURCE_LABELS["spotify"],
        playlist_title=playlist_title,
        reported_count=reported_count,
        songs=list(songs.values()),
        download_supported=False,
    )


def scrape_spotify_liked_songs(
    host: str,
    port: int,
    log: Callable[[str, str], None],
) -> ScrapeResult:
    connection = DevToolsConnection(host, port)
    target_id: str | None = None

    try:
        target_id, session_id = _open_source_target(connection, "spotify", log)
        _wait_for_snapshot(
            connection,
            session_id,
            _build_spotify_snapshot_expression(),
            "Timed out waiting for the Spotify Liked Songs page. Sign in first.",
        )
        return _collect_spotify_songs(connection, session_id, log)
    finally:
        if target_id:
            connection.close_target(target_id)
        connection.close()


def scrape_source(
    source: str,
    host: str,
    port: int,
    log: Callable[[str, str], None],
) -> ScrapeResult:
    if source == "spotify":
        return scrape_spotify_liked_songs(host, port, log)
    return scrape_youtube_liked_music(host, port, log)
