from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"
RELEASE_DIR = ROOT / "release"
APP_NAME = "Music Studio"


def _asset_name() -> str:
    if sys.platform == "win32":
        return "Music-Studio-Windows.zip"
    if sys.platform == "darwin":
        return "Music-Studio-macOS.zip"
    return "Music-Studio-Linux.tar.gz"


def _bundle_name() -> str:
    if sys.platform == "darwin":
        return f"{APP_NAME}.app"
    return APP_NAME


def _bundle_path() -> Path:
    return DIST_DIR / _bundle_name()


def _quickstart_text() -> str:
    if sys.platform == "win32":
        open_step = f"Double-click `{APP_NAME}.exe` to launch the desktop app."
    elif sys.platform == "darwin":
        open_step = f"Open `{APP_NAME}.app` to launch the desktop app."
    else:
        open_step = f"Run `./{APP_NAME}` from the extracted folder to launch the desktop app."

    return "\n".join(
        [
            "Music Studio desktop app",
            "",
            open_step,
            "",
            "Inside the app:",
            "1. Open YouTube Sign-In",
            "2. Sign in with the user's own browser",
            "3. Import the current browser session",
            "4. Choose a local download folder",
            "5. Paste links or download the likes playlist",
        ]
    )


def _pyinstaller_command() -> list[str]:
    add_data = f"{ROOT / 'public'}{os.pathsep}public"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        "--add-data",
        add_data,
        "--collect-all",
        "webview",
        "--collect-all",
        "yt_dlp",
        "--collect-all",
        "browser_cookie3",
        "--collect-all",
        "imageio_ffmpeg",
    ]
    if importlib.util.find_spec("qtpy") is not None:
        command.extend(["--collect-all", "qtpy"])
    if importlib.util.find_spec("PySide6") is not None:
        command.extend(["--collect-all", "PySide6"])
    if sys.platform == "darwin":
        command.extend(["--osx-bundle-identifier", "com.vstm.musicstudio"])
    command.append(str(ROOT / "main.py"))
    return command


def _reset_build_dirs() -> None:
    for directory in (BUILD_DIR, DIST_DIR, RELEASE_DIR):
        shutil.rmtree(directory, ignore_errors=True)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)


def _prepare_staging_dir(bundle_path: Path) -> Path:
    staging_dir = RELEASE_DIR / "staging"
    shutil.rmtree(staging_dir, ignore_errors=True)
    staging_dir.mkdir(parents=True, exist_ok=True)

    target_bundle = staging_dir / bundle_path.name
    shutil.copytree(bundle_path, target_bundle)
    shutil.copy2(ROOT / "LICENSE", staging_dir / "LICENSE.txt")
    (staging_dir / "README-FIRST.txt").write_text(_quickstart_text(), encoding="utf-8")
    return staging_dir


def _create_zip(source_dir: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_dir():
                continue
            archive.write(path, path.relative_to(source_dir))


def _create_targz(source_dir: Path, destination: Path) -> None:
    with tarfile.open(destination, "w:gz") as archive:
        for path in sorted(source_dir.iterdir()):
            archive.add(path, arcname=path.name)


def build_release_bundle() -> Path:
    _reset_build_dirs()
    subprocess.check_call(_pyinstaller_command(), cwd=ROOT)

    bundle_path = _bundle_path()
    if not bundle_path.exists():
        raise FileNotFoundError(f"Expected packaged app at {bundle_path}")

    staging_dir = _prepare_staging_dir(bundle_path)
    archive_path = RELEASE_DIR / _asset_name()
    if archive_path.suffix == ".zip":
        _create_zip(staging_dir, archive_path)
    else:
        _create_targz(staging_dir, archive_path)
    return archive_path


def main() -> None:
    archive_path = build_release_bundle()
    print(archive_path)


if __name__ == "__main__":
    main()
