# Music Studio

Music Studio is now a **desktop app** for Windows, macOS, and Linux.

The app opens a native window, lets the user sign into YouTube in their normal browser, imports that browser session locally, then uses `yt-dlp` and `ffmpeg` on the same machine to download pasted links or the user's `LL` likes playlist into a folder they choose.

## What changed

- the main product is now a desktop app, not a hosted Render flow
- the Python backend now runs as an embedded local service inside the app
- browser authentication now comes from installed local browsers instead of hosted Google login
- the repo still contains some legacy OAuth and extension artifacts, but they are no longer the primary path

## Current desktop architecture

- `main.py`
  - launches the desktop app by default
  - use `python main.py --helper-only` to run only the local HTTP service
- `liked_music_studio/desktop_app.py`
  - starts the local backend
  - opens the native app window with `pywebview`
  - exposes native actions like folder picking and opening external browser tabs
- `liked_music_studio/server.py`
  - manages browser-session import
  - runs download jobs
  - tracks logs, progress, and finished files
- `liked_music_studio/downloader.py`
  - runs `yt-dlp`
  - installs or finds `ffmpeg`
  - uses imported browser cookies when available
- `public/`
  - main desktop app UI

## Run locally

```powershell
cd C:\path\to\Music-Studio
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

If you only want the local backend service without opening the native app window:

```powershell
python main.py --helper-only
```

## Desktop app flow

1. Open Music Studio
2. Click `Open YouTube Sign-In`
3. Sign into YouTube in your normal browser
4. Pick the browser to import from
5. Click `Use Current Browser Session`
6. Click `Choose Local Folder`
7. Paste links or click `Download My Likes`

## Packaging notes

- this codebase is structured to be packaged as a desktop app
- tagged GitHub releases build real GUI bundles for Windows, macOS, and Linux
- the release assets contain the packaged app itself, not just the source tree
- local packaging is handled by `python scripts/build_desktop_release.py`

## Dependencies

- `yt-dlp`
- `imageio-ffmpeg`
- `browser-cookie3`
- `pywebview`
