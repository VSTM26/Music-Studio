from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import (
    APP_NAME,
    APP_REPOSITORY_URL,
    APP_UPDATE_BRANCH,
    APP_UPDATE_OWNER,
    APP_UPDATE_REPO,
    APP_VERSION,
)


BASE_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = BASE_DIR / "runtime"
STATE_PATH = RUNTIME_DIR / "update-state.json"
REQUEST_TIMEOUT = 12.0
USER_AGENT = f"{APP_NAME.replace(' ', '-')}/{APP_VERSION}"
PRESERVED_TOP_LEVEL = {".git", ".venv", "output", "runtime"}
IGNORED_PARTS = {"__pycache__"}
IGNORED_FILE_NAMES = {".DS_Store"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


@dataclass
class UpdateState:
    version: str | None = None
    commit: str | None = None
    mode: str | None = None
    managed_files: list[str] = field(default_factory=list)
    last_checked_at: str | None = None
    last_updated_at: str | None = None

    @classmethod
    def load(cls) -> "UpdateState":
        try:
            payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except Exception:
            return cls()
        if not isinstance(payload, dict):
            return cls()
        managed_files = payload.get("managedFiles")
        return cls(
            version=_clean_optional_text(payload.get("version")),
            commit=_clean_optional_text(payload.get("commit")),
            mode=_clean_optional_text(payload.get("mode")),
            managed_files=managed_files if isinstance(managed_files, list) else [],
            last_checked_at=_clean_optional_text(payload.get("lastCheckedAt")),
            last_updated_at=_clean_optional_text(payload.get("lastUpdatedAt")),
        )

    def save(self) -> None:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.version,
            "commit": self.commit,
            "mode": self.mode,
            "managedFiles": self.managed_files,
            "lastCheckedAt": self.last_checked_at,
            "lastUpdatedAt": self.last_updated_at,
        }
        STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@dataclass
class RemoteVersion:
    version: str
    commit: str
    archive_url: str


@dataclass
class UpdateResult:
    status: str
    message: str
    updated: bool = False


def _clean_optional_text(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _request(url: str, accept: str) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": USER_AGENT,
        },
    )
    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return response.read()


def _request_json(url: str) -> dict[str, Any]:
    payload = json.loads(_request(url, "application/json").decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected a JSON object from {url}.")
    return payload


def _request_text(url: str) -> str:
    return _request(url, "text/plain").decode("utf-8")


def _parse_version_tuple(value: str) -> tuple[int, ...]:
    parts = [int(part) for part in re.findall(r"\d+", value)]
    return tuple(parts or [0])


def _compare_versions(left: str, right: str) -> int:
    left_parts = list(_parse_version_tuple(left))
    right_parts = list(_parse_version_tuple(right))
    max_length = max(len(left_parts), len(right_parts))
    left_parts.extend([0] * (max_length - len(left_parts)))
    right_parts.extend([0] * (max_length - len(right_parts)))
    if left_parts < right_parts:
        return -1
    if left_parts > right_parts:
        return 1
    return 0


def _parse_remote_version(init_text: str) -> str:
    match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', init_text)
    if not match:
        raise RuntimeError("GitHub update metadata did not include APP_VERSION.")
    return match.group(1).strip()


def _read_local_version() -> str:
    init_path = BASE_DIR / "liked_music_studio" / "__init__.py"
    try:
        return _parse_remote_version(init_path.read_text(encoding="utf-8"))
    except Exception:
        return APP_VERSION


def _is_ignored_path(path: Path, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts
    if not rel_parts:
        return True
    if rel_parts[0] in PRESERVED_TOP_LEVEL:
        return True
    if any(part in IGNORED_PARTS for part in rel_parts):
        return True
    if path.name in IGNORED_FILE_NAMES:
        return True
    if path.suffix in IGNORED_SUFFIXES:
        return True
    return False


def _list_archive_files(root: Path) -> list[str]:
    managed_files: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if _is_ignored_path(path, root):
            continue
        managed_files.append(path.relative_to(root).as_posix())
    return managed_files


def _remove_deleted_files(previous: list[str], current: list[str]) -> None:
    stale_paths = sorted(set(previous) - set(current), reverse=True)
    for rel_path in stale_paths:
        candidate = (BASE_DIR / rel_path).resolve()
        try:
            candidate.relative_to(BASE_DIR.resolve())
        except ValueError:
            continue
        if candidate.is_file():
            candidate.unlink(missing_ok=True)
        parent = candidate.parent
        while parent != BASE_DIR and parent.exists():
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent


def _ensure_command_executable(path: Path) -> None:
    if os.name == "nt" or path.suffix not in {".command", ".sh"}:
        return
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _apply_archive_update(remote: RemoteVersion, state: UpdateState) -> UpdateResult:
    with tempfile.TemporaryDirectory(prefix="music-studio-update-") as temp_dir:
        temp_root = Path(temp_dir)
        archive_path = temp_root / "update.zip"
        archive_path.write_bytes(_request(remote.archive_url, "application/octet-stream"))

        extract_dir = temp_root / "extract"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path) as bundle:
            bundle.extractall(extract_dir)

        extracted_roots = [path for path in extract_dir.iterdir() if path.is_dir()]
        if not extracted_roots:
            raise RuntimeError("Downloaded update archive was empty.")
        source_root = extracted_roots[0]
        managed_files = _list_archive_files(source_root)

        for rel_path in managed_files:
            source = source_root / rel_path
            destination = BASE_DIR / rel_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            _ensure_command_executable(destination)

        if state.managed_files:
            _remove_deleted_files(state.managed_files, managed_files)

        state.version = remote.version
        state.commit = remote.commit
        state.mode = "archive"
        state.managed_files = managed_files
        state.last_checked_at = _utc_now()
        state.last_updated_at = state.last_checked_at
        state.save()
        return UpdateResult(
            status="updated",
            updated=True,
            message=f"Updated {APP_NAME} to {remote.version} from GitHub.",
        )


def _fetch_remote_version() -> RemoteVersion:
    branch = os.environ.get("MUSIC_STUDIO_UPDATE_BRANCH", APP_UPDATE_BRANCH).strip() or APP_UPDATE_BRANCH
    owner = os.environ.get("MUSIC_STUDIO_UPDATE_OWNER", APP_UPDATE_OWNER).strip() or APP_UPDATE_OWNER
    repo = os.environ.get("MUSIC_STUDIO_UPDATE_REPO", APP_UPDATE_REPO).strip() or APP_UPDATE_REPO

    commit_payload = _request_json(f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}")
    commit = _clean_optional_text(commit_payload.get("sha"))
    if not commit:
        raise RuntimeError("GitHub did not return a commit SHA for the update check.")

    init_text = _request_text(
        f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/liked_music_studio/__init__.py"
    )
    version = _parse_remote_version(init_text)
    archive_url = f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{branch}"
    return RemoteVersion(version=version, commit=commit, archive_url=archive_url)


def _git_available() -> bool:
    return shutil.which("git") is not None and (BASE_DIR / ".git").exists()


def _run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=BASE_DIR,
        text=True,
        capture_output=True,
        check=False,
    )


def _git_is_ancestor(ancestor: str, descendant: str) -> bool:
    result = _run_git("merge-base", "--is-ancestor", ancestor, descendant)
    return result.returncode == 0


def _maybe_update_from_git(state: UpdateState) -> UpdateResult:
    remote_name = os.environ.get("MUSIC_STUDIO_GIT_REMOTE", "origin").strip() or "origin"
    branch = os.environ.get("MUSIC_STUDIO_UPDATE_BRANCH", APP_UPDATE_BRANCH).strip() or APP_UPDATE_BRANCH

    dirty = _run_git("status", "--porcelain")
    if dirty.returncode != 0:
        raise RuntimeError(dirty.stderr.strip() or "Git status failed during auto-update.")
    if dirty.stdout.strip():
        return UpdateResult(
            status="skipped",
            message="Skipped auto-update because this Git checkout has local changes.",
        )

    fetch = _run_git("fetch", "--quiet", remote_name, branch)
    if fetch.returncode != 0:
        raise RuntimeError(fetch.stderr.strip() or "Git fetch failed during auto-update.")

    local_head = _run_git("rev-parse", "HEAD")
    remote_head = _run_git("rev-parse", f"{remote_name}/{branch}")
    if local_head.returncode != 0 or remote_head.returncode != 0:
        raise RuntimeError("Git could not resolve the local or remote revision.")

    local_commit = local_head.stdout.strip()
    incoming_commit = remote_head.stdout.strip()
    current_version = _read_local_version()

    if local_commit == incoming_commit:
        state.version = current_version
        state.commit = local_commit
        state.mode = "git"
        state.managed_files = []
        state.last_checked_at = _utc_now()
        state.save()
        return UpdateResult(status="current", message=f"{APP_NAME} is already up to date.")

    if _git_is_ancestor(local_commit, incoming_commit):
        pull = _run_git("pull", "--ff-only", remote_name, branch)
        if pull.returncode != 0:
            raise RuntimeError(pull.stderr.strip() or "Git pull failed during auto-update.")

        refreshed_commit = _run_git("rev-parse", "HEAD")
        if refreshed_commit.returncode != 0:
            raise RuntimeError("Git updated, but the new revision could not be read.")

        state.version = _read_local_version()
        state.commit = refreshed_commit.stdout.strip()
        state.mode = "git"
        state.managed_files = []
        state.last_checked_at = _utc_now()
        state.last_updated_at = state.last_checked_at
        state.save()
        return UpdateResult(
            status="updated",
            updated=True,
            message=f"Pulled the latest {APP_NAME} files from GitHub.",
        )

    if _git_is_ancestor(incoming_commit, local_commit):
        state.version = current_version
        state.commit = local_commit
        state.mode = "git"
        state.managed_files = []
        state.last_checked_at = _utc_now()
        state.save()
        return UpdateResult(
            status="current",
            message="Skipped auto-update because this Git checkout is already ahead of origin.",
        )

    return UpdateResult(
        status="skipped",
        message="Skipped auto-update because this Git checkout has diverged from origin.",
    )


def check_for_updates() -> UpdateResult:
    if os.environ.get("MUSIC_STUDIO_SKIP_UPDATE") == "1":
        return UpdateResult(status="skipped", message="Skipped auto-update because MUSIC_STUDIO_SKIP_UPDATE=1.")

    state = UpdateState.load()

    if _git_available():
        try:
            return _maybe_update_from_git(state)
        except RuntimeError as error:
            return UpdateResult(
                status="skipped",
                message=f"Skipped Git auto-update: {error}",
            )

    try:
        remote = _fetch_remote_version()
    except (HTTPError, URLError, TimeoutError, OSError, RuntimeError) as error:
        return UpdateResult(
            status="skipped",
            message=f"Skipped auto-update because GitHub could not be reached: {error}",
        )

    local_version = _read_local_version()
    version_compare = _compare_versions(remote.version, local_version)

    if version_compare < 0:
        state.version = local_version
        state.commit = state.commit
        state.mode = "archive"
        state.last_checked_at = _utc_now()
        state.save()
        return UpdateResult(
            status="current",
            message=f"Installed build {local_version} is newer than the GitHub branch.",
        )

    if version_compare == 0 and not state.commit:
        state.version = local_version
        state.commit = remote.commit
        state.mode = "archive"
        state.last_checked_at = _utc_now()
        state.save()
        return UpdateResult(status="current", message=f"{APP_NAME} is already up to date.")

    if version_compare == 0 and state.commit == remote.commit:
        state.version = local_version
        state.mode = "archive"
        state.last_checked_at = _utc_now()
        state.save()
        return UpdateResult(status="current", message=f"{APP_NAME} is already up to date.")

    try:
        return _apply_archive_update(remote, state)
    except Exception as error:
        raise RuntimeError(f"Auto-update failed while applying files from {APP_REPOSITORY_URL}: {error}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check GitHub for Music-Studio updates.")
    parser.parse_args(argv)
    try:
        result = check_for_updates()
    except RuntimeError as error:
        print(str(error))
        return 1

    print(result.message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
