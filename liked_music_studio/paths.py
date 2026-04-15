from __future__ import annotations

import os
import sys
from pathlib import Path

from . import APP_NAME


def get_resource_root() -> Path:
    if getattr(sys, "frozen", False):
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            return Path(bundle_root)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def get_user_data_root() -> Path:
    override = os.environ.get("MUSIC_STUDIO_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME

    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            return Path(local_app_data) / APP_NAME
        return Path.home() / "AppData" / "Local" / APP_NAME

    xdg_data_home = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg_data_home:
        return Path(xdg_data_home) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


RESOURCE_ROOT = get_resource_root()
USER_DATA_ROOT = get_user_data_root()
PUBLIC_DIR = RESOURCE_ROOT / "public"
RUNTIME_DIR = USER_DATA_ROOT / "runtime"
OUTPUT_DIR = USER_DATA_ROOT / "output"
