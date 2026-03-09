# Music-Studio

Music-Studio is a local Python app for Windows and macOS that helps people:

- open a guided Chrome session for YouTube Music or Spotify
- sign in with their own account
- scrape YouTube Music `Liked Music` or Spotify `Liked Songs` through the live browser session
- export the results into `txt`, `csv`, and `json`
- optionally download all or only selected YouTube Music tracks with `yt-dlp`
- optionally extract MP3 audio through `ffmpeg`
- auto-update from GitHub on launch so users can pick up new releases without manually re-downloading the repo

The app runs fully on the user's machine. It does not use personal API keys for exporting either source. The Python dependencies install `yt-dlp` and a bundled ffmpeg fallback automatically.

## Requirements

- Windows or macOS
- Python 3.11 or newer
- Google Chrome
- Internet access the first time dependencies are installed

## Install

### Windows

```powershell
cd D:\liked-music-studio
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### macOS

```bash
cd /path/to/Music-Studio
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

You can still install a system `ffmpeg` if you want, but the app can also fall back to the `imageio-ffmpeg` binary that comes in through `requirements.txt`:

```bash
brew install ffmpeg
```

## Run

### Windows

```powershell
cd D:\liked-music-studio
.venv\Scripts\activate
python main.py
```

Or double-click:

`run-liked-music-studio.cmd`

The Windows launcher creates `.venv` automatically if needed, installs `requirements.txt`, and then starts the app.
It also checks GitHub for updates first and pulls in the newest files automatically.

### macOS

```bash
cd /path/to/Music-Studio
source .venv/bin/activate
python3 main.py
```

Or make the launcher executable once and then open it:

```bash
chmod +x run-liked-music-studio.command
./run-liked-music-studio.command
```

The macOS launcher does the same setup automatically: it creates `.venv` when missing, installs `requirements.txt`, and starts the app.
It also checks GitHub for updates first and pulls in the newest files automatically.

The app opens at:

`http://127.0.0.1:4173`

If a user skips `pip install -r requirements.txt` and launches the app directly with `python main.py`, the app now tries to install missing Python dependencies automatically on first run.
If they use the launchers, the app also checks GitHub on startup and updates itself before launching.

## How to use it

1. Start the app.
2. Click `Choose Save Folder` if you want exports somewhere other than the default `output` folder.
3. Pick either `YouTube Music` or `Spotify` in the source switcher.
4. Click `Open Guided Chrome`.
5. Sign in to that source in the guided Chrome window.
6. Leave Guided Chrome open.
7. Click `Run Export`.
8. Download the generated `txt`, `csv`, or `json` export files.
9. If the export source was YouTube Music, optionally select some tracks or use `Download All Exported`.
10. Turn on `Extract audio into MP3 files with ffmpeg` if you want audio-only output for YouTube-based downloads.

## Output layout

- Export files are written directly into the selected save folder.
- YouTube media downloads are written into a `downloads` subfolder inside that save folder.
- The latest export manifest is stored as `latest-export.json`.

## Project layout

- `main.py` - Python entry point
- `liked_music_studio/server.py` - local HTTP server and API
- `liked_music_studio/devtools.py` - Chrome DevTools playlist scraping
- `liked_music_studio/exports.py` - export file writers and manifest helpers
- `liked_music_studio/downloader.py` - `yt-dlp` and `ffmpeg` download flow
- `public/` - browser UI

## Notes

- The scraper uses a dedicated Chrome profile in `runtime/chrome-profile` so different people can sign in locally without sharing credentials.
- YouTube downloads reuse that same Guided Chrome profile with `yt-dlp --cookies-from-browser`, which helps with age-restricted or sign-in-only videos.
- Some YouTube Music playlist counts do not perfectly match what the live browser session exposes while scrolling. The app keeps both the reported count and the exported count so the result stays honest.
- Spotify support in this repo is metadata export only. It does not try to download audio from Spotify.
- `yt-dlp` is installed through `requirements.txt`. MP3 extraction can use either a system `ffmpeg` or the bundled `imageio-ffmpeg` fallback.
- ZIP installs update by downloading the latest GitHub branch archive and replacing the managed app files while preserving `.venv`, `output`, and `runtime`. Git clones use `git pull --ff-only` when the checkout is clean.
- Set `MUSIC_STUDIO_SKIP_UPDATE=1` before launch if you ever need to skip the auto-updater for troubleshooting.
- On macOS, the app looks for Chrome in both `/Applications` and `~/Applications`. You can always override that with `CHROME_PATH`.
