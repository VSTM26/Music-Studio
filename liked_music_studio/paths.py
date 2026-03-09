from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DATA_NAME = "Music-Studio"
SOURCE_ROOT = Path(__file__).resolve().parents[1]


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return SOURCE_ROOT


def install_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return SOURCE_ROOT


def user_data_root() -> Path:
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return base / APP_DATA_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DATA_NAME
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home) if data_home else Path.home() / ".local" / "share"
    return base / APP_DATA_NAME


def app_data_root() -> Path:
    return user_data_root() if is_frozen() else SOURCE_ROOT


def public_dir() -> Path:
    return resource_root() / "public"


def output_dir() -> Path:
    return app_data_root() / "output"


def runtime_dir() -> Path:
    return app_data_root() / "runtime"
