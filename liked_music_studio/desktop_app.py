from __future__ import annotations

import argparse
import os
import socket
import sys
import time
import webbrowser

from . import APP_NAME
from .paths import RESOURCE_ROOT
from .server import create_server_instance, main as helper_main, start_server_thread

try:
    import webview  # type: ignore
except Exception:
    webview = None


def _is_port_open(host: str, port: int, timeout_seconds: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def _folder_dialog_type() -> object:
    if webview is None:
        return 0
    file_dialog = getattr(webview, "FileDialog", None)
    if file_dialog is not None and hasattr(file_dialog, "FOLDER"):
        return file_dialog.FOLDER
    return getattr(webview, "FOLDER_DIALOG", 0)


class DesktopBridge:
    def __init__(self) -> None:
        self.window = None

    def attach_window(self, window: object) -> None:
        self.window = window

    def open_external(self, url: str) -> bool:
        return bool(webbrowser.open(str(url)))

    def choose_download_folder(self) -> str | None:
        if self.window is None or webview is None:
            return None

        result = self.window.create_file_dialog(_folder_dialog_type())
        if not result:
            return None
        if isinstance(result, (list, tuple)):
            return str(result[0]) if result else None
        return str(result)

    def get_app_paths(self) -> dict[str, str]:
        return {
            "resourceRoot": str(RESOURCE_ROOT),
        }


def run_desktop_app() -> int:
    if webview is None:
        print("pywebview is not installed. Falling back to helper-only mode.")
        helper_main()
        return 0

    server, actual_port, _ = create_server_instance()
    server_thread = start_server_thread(server)
    startup_url = f"http://127.0.0.1:{actual_port}/app"

    started_at = time.monotonic()
    while time.monotonic() - started_at < 8.0:
        if _is_port_open("127.0.0.1", actual_port, 0.5):
            break
        time.sleep(0.1)

    bridge = DesktopBridge()
    window = webview.create_window(
        APP_NAME,
        startup_url,
        js_api=bridge,
        width=1320,
        height=920,
        min_size=(1040, 760),
        text_select=True,
    )
    bridge.attach_window(window)

    try:
        webview.start(debug=False)
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2.0)

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Music Studio desktop app.")
    parser.add_argument(
        "--helper-only",
        action="store_true",
        help="Start only the local helper HTTP service instead of opening the desktop app.",
    )
    args = parser.parse_args(argv)

    if args.helper_only or os.environ.get("MUSIC_STUDIO_HELPER_ONLY") == "1":
        helper_main()
        return 0

    return run_desktop_app()


if __name__ == "__main__":
    sys.exit(main())
