from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
REQUIRED_MODULES = {
    "yt-dlp": "yt_dlp",
    "imageio-ffmpeg": "imageio_ffmpeg",
}


def ensure_dependencies() -> None:
    missing = [
        package_name
        for package_name, module_name in REQUIRED_MODULES.items()
        if importlib.util.find_spec(module_name) is None
    ]
    if not missing:
        return

    requirements_path = BASE_DIR / "requirements.txt"
    print(f"Installing missing dependencies: {', '.join(missing)}")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", str(requirements_path)],
        cwd=BASE_DIR,
    )


ensure_dependencies()

from liked_music_studio.server import main


if __name__ == "__main__":
    main()
