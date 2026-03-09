from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
RELEASE_DIR = DIST_DIR / "release"
APP_SLUG = "Music-Studio"


def _load_app_metadata() -> dict[str, str]:
    namespace: dict[str, object] = {}
    init_path = ROOT / "liked_music_studio" / "__init__.py"
    exec(init_path.read_text(encoding="utf-8"), namespace)
    return {
        "version": str(namespace["APP_VERSION"]),
        "owner": str(namespace["APP_UPDATE_OWNER"]),
        "repo": str(namespace["APP_UPDATE_REPO"]),
    }


def _load_version() -> str:
    return _load_app_metadata()["version"]


def _normalize_arch(machine: str) -> str:
    value = machine.lower()
    if value in {"amd64", "x86_64", "x64"}:
        return "x64"
    if value in {"arm64", "aarch64"}:
        return "arm64"
    return value.replace(" ", "-")


def _default_platform_id() -> str:
    arch = _normalize_arch(platform.machine())
    if os.name == "nt":
        return f"windows-{arch}"
    if sys.platform == "darwin":
        return f"macos-{arch}"
    return f"linux-{arch}"


def _data_separator() -> str:
    return ";" if os.name == "nt" else ":"


def _archive_extension(archive_format: str) -> str:
    return ".zip" if archive_format == "zip" else ".tar.gz"


def _stable_archive_name(platform_id: str, archive_format: str) -> str:
    return f"{APP_SLUG}-latest-{platform_id}{_archive_extension(archive_format)}"


def _stable_version_name(platform_id: str) -> str:
    return f"{APP_SLUG}-latest-{platform_id}.txt"


def _run(command: list[str], cwd: Path | None = None) -> None:
    print("Running:", " ".join(str(part) for part in command))
    subprocess.run(command, cwd=cwd or ROOT, check=True)


def _build_pyinstaller() -> Path:
    app_dir = DIST_DIR / APP_SLUG
    if app_dir.exists():
        shutil.rmtree(app_dir)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        APP_SLUG,
        "--hidden-import",
        "websocket",
        "--collect-submodules",
        "yt_dlp",
        "--collect-data",
        "imageio_ffmpeg",
        "--collect-binaries",
        "imageio_ffmpeg",
        "--add-data",
        f"{ROOT / 'public'}{_data_separator()}public",
        str(ROOT / "main.py"),
    ]
    _run(command)
    return app_dir


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def _windows_launcher_content(platform_id: str, version: str, owner: str, repo: str, archive_format: str) -> str:
    version_asset = _stable_version_name(platform_id)
    archive_asset = _stable_archive_name(platform_id, archive_format)
    return f"""@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "CURRENT_VERSION={version}"
set "PLATFORM_ID={platform_id}"
set "OWNER={owner}"
set "REPO={repo}"
set "REMOTE_VERSION_URL=https://github.com/%OWNER%/%REPO%/releases/latest/download/{version_asset}"
set "REMOTE_ARCHIVE_URL=https://github.com/%OWNER%/%REPO%/releases/latest/download/{archive_asset}"
set "CACHE_BASE=%LOCALAPPDATA%\\Music-Studio\\packaged-builds"
if not defined LOCALAPPDATA set "CACHE_BASE=%USERPROFILE%\\AppData\\Local\\Music-Studio\\packaged-builds"

set "REMOTE_VERSION="
where powershell >nul 2>nul
if not errorlevel 1 (
  for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try {{ (Invoke-WebRequest -UseBasicParsing '%REMOTE_VERSION_URL%').Content.Trim() }} catch {{ '' }}"`) do (
    set "REMOTE_VERSION=%%I"
  )
)

set "LAUNCH_DIR=%~dp0"
if defined REMOTE_VERSION if /I not "!REMOTE_VERSION!"=="%CURRENT_VERSION%" (
  set "CACHED_DIR=!CACHE_BASE!\\Music-Studio-!REMOTE_VERSION!-%PLATFORM_ID%"
  set "CACHED_EXE=!CACHED_DIR!\\Music-Studio.exe"
  if not exist "!CACHED_EXE!" (
    echo Downloading Music-Studio !REMOTE_VERSION!...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; $archiveUrl='%REMOTE_ARCHIVE_URL%'; $cacheRoot='%CACHE_BASE%'; $targetDir=Join-Path $cacheRoot 'Music-Studio-!REMOTE_VERSION!-%PLATFORM_ID%'; $tempRoot=Join-Path ([System.IO.Path]::GetTempPath()) ('music-studio-' + [guid]::NewGuid().ToString('N')); New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null; $archivePath=Join-Path $tempRoot 'release.zip'; $extractPath=Join-Path $tempRoot 'extract'; Invoke-WebRequest -UseBasicParsing $archiveUrl -OutFile $archivePath; Expand-Archive -Path $archivePath -DestinationPath $extractPath -Force; $sourceDir=Get-ChildItem -Path $extractPath -Directory | Select-Object -First 1; if (-not $sourceDir) {{ throw 'Update archive was empty.' }}; New-Item -ItemType Directory -Force -Path $cacheRoot | Out-Null; if (Test-Path $targetDir) {{ Remove-Item -Recurse -Force $targetDir }}; Copy-Item -Recurse -Force $sourceDir.FullName $targetDir; Remove-Item -Recurse -Force $tempRoot"
    if errorlevel 1 echo GitHub release download failed. Launching the local packaged build instead.
  )
  if exist "!CACHED_EXE!" set "LAUNCH_DIR=!CACHED_DIR!"
)

start "" "%LAUNCH_DIR%\\Music-Studio.exe"
"""


def _unix_launcher_content(platform_id: str, version: str, owner: str, repo: str, archive_format: str) -> str:
    version_asset = _stable_version_name(platform_id)
    archive_asset = _stable_archive_name(platform_id, archive_format)
    if archive_format == "zip":
        extract_block = 'if unzip -oq "$archive_path" -d "$extract_dir"; then'
    else:
        extract_block = 'if tar -xzf "$archive_path" -C "$extract_dir"; then'

    return f"""#!/bin/bash
set -uo pipefail

cd "$(dirname "$0")"

CURRENT_VERSION="{version}"
PLATFORM_ID="{platform_id}"
OWNER="{owner}"
REPO="{repo}"
REMOTE_VERSION_URL="https://github.com/${{OWNER}}/${{REPO}}/releases/latest/download/{version_asset}"
REMOTE_ARCHIVE_URL="https://github.com/${{OWNER}}/${{REPO}}/releases/latest/download/{archive_asset}"

if [[ "${{OSTYPE:-}}" == darwin* ]]; then
  CACHE_BASE="${{HOME}}/Library/Application Support/Music-Studio/packaged-builds"
else
  CACHE_BASE="${{XDG_DATA_HOME:-$HOME/.local/share}}/Music-Studio/packaged-builds"
fi

fetch_url() {{
  if command -v curl >/dev/null 2>&1; then
    curl -fsL "$1"
    return $?
  fi
  if command -v wget >/dev/null 2>&1; then
    wget -qO- "$1"
    return $?
  fi
  return 1
}}

remote_version="$(fetch_url "$REMOTE_VERSION_URL" 2>/dev/null | tr -d '\\r' | head -n 1 || true)"
launch_dir="$PWD"

if [[ -n "$remote_version" && "$remote_version" != "$CURRENT_VERSION" ]]; then
  cached_dir="$CACHE_BASE/Music-Studio-$remote_version-$PLATFORM_ID"
  cached_bin="$cached_dir/Music-Studio"
  if [[ ! -x "$cached_bin" ]]; then
    echo "Downloading Music-Studio $remote_version..."
    tmp_root="$(mktemp -d 2>/dev/null || mktemp -d -t music-studio)"
    if [[ -n "$tmp_root" ]]; then
      archive_path="$tmp_root/release{_archive_extension(archive_format)}"
      extract_dir="$tmp_root/extract"
      mkdir -p "$extract_dir" "$CACHE_BASE"
      if fetch_url "$REMOTE_ARCHIVE_URL" > "$archive_path"; then
        {extract_block}
          source_dir="$(find "$extract_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
          if [[ -n "$source_dir" ]]; then
            rm -rf "$cached_dir"
            mv "$source_dir" "$cached_dir"
          fi
        else
          echo "GitHub release download failed. Launching the local packaged build instead."
        fi
      else
        echo "GitHub release download failed. Launching the local packaged build instead."
      fi
      rm -rf "$tmp_root"
    fi
  fi
  if [[ -x "$cached_bin" ]]; then
    launch_dir="$cached_dir"
  fi
fi

exec "$launch_dir/Music-Studio"
"""


def _packaged_notes(version: str, platform_id: str, archive_format: str) -> str:
    archive_name = _stable_archive_name(platform_id, archive_format)
    return f"""Music-Studio packaged build {version}

1. Keep this folder together after extracting it.
2. Use the packaged launcher instead of the raw binary if you want automatic GitHub release updates.
3. Windows: double-click run-liked-music-studio.bat.
4. macOS: run chmod +x run-liked-music-studio.command once, then open it.
5. Linux: run chmod +x run-liked-music-studio.sh once, then run it.
6. The packaged launcher checks GitHub for the latest release and caches newer builds under your user data folder.
7. The stable release asset used by this build is {archive_name}.
8. The app opens a local browser UI and stores runtime/output data in a user data folder.
"""


def _add_launchers(
    package_dir: Path,
    platform_id: str,
    version: str,
    owner: str,
    repo: str,
    archive_format: str,
) -> None:
    _write_text(
        package_dir / "run-liked-music-studio.bat",
        _windows_launcher_content(platform_id, version, owner, repo, archive_format),
    )
    _write_text(
        package_dir / "run-liked-music-studio.command",
        _unix_launcher_content(platform_id, version, owner, repo, archive_format),
    )
    _write_text(
        package_dir / "run-liked-music-studio.sh",
        _unix_launcher_content(platform_id, version, owner, repo, archive_format),
    )
    _write_text(package_dir / "version.txt", f"{version}\n")
    _write_text(package_dir / "README-packaged.txt", _packaged_notes(version, platform_id, archive_format))

    if os.name != "nt":
        for name in ("run-liked-music-studio.command", "run-liked-music-studio.sh"):
            path = package_dir / name
            path.chmod(path.stat().st_mode | 0o111)


def _stage_package(app_dir: Path, platform_id: str, archive_format: str) -> Path:
    metadata = _load_app_metadata()
    version = metadata["version"]
    package_dir = RELEASE_DIR / f"{APP_SLUG}-{version}-{platform_id}"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(app_dir, package_dir)
    shutil.copy2(ROOT / "LICENSE", package_dir / "LICENSE")
    _add_launchers(package_dir, platform_id, version, metadata["owner"], metadata["repo"], archive_format)
    return package_dir


def _make_zip(package_dir: Path) -> Path:
    archive_path = Path(f"{package_dir}.zip")
    if archive_path.exists():
        archive_path.unlink()
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for path in sorted(package_dir.rglob("*")):
            handle.write(path, path.relative_to(package_dir.parent))
    return archive_path


def _make_tar_gz(package_dir: Path) -> Path:
    archive_path = Path(f"{package_dir}.tar.gz")
    if archive_path.exists():
        archive_path.unlink()
    with tarfile.open(archive_path, "w:gz") as handle:
        handle.add(package_dir, arcname=package_dir.name)
    return archive_path


def _write_release_aliases(platform_id: str, archive_format: str, archive_path: Path) -> None:
    version = _load_version()
    latest_archive_path = RELEASE_DIR / _stable_archive_name(platform_id, archive_format)
    latest_version_path = RELEASE_DIR / _stable_version_name(platform_id)
    if latest_archive_path.exists():
        latest_archive_path.unlink()
    shutil.copy2(archive_path, latest_archive_path)
    _write_text(latest_version_path, f"{version}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a packaged Music-Studio release artifact.")
    parser.add_argument("--platform-id", default=_default_platform_id())
    parser.add_argument("--archive-format", choices=["zip", "tar.gz"], default=None)
    args = parser.parse_args(argv)

    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    archive_format = args.archive_format or ("zip" if os.name == "nt" else "tar.gz")
    app_dir = _build_pyinstaller()
    package_dir = _stage_package(app_dir, args.platform_id, archive_format)
    archive_path = _make_zip(package_dir) if archive_format == "zip" else _make_tar_gz(package_dir)
    _write_release_aliases(args.platform_id, archive_format, archive_path)
    print(archive_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
