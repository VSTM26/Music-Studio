# Music-Studio

Music-Studio is a local Python app for exporting liked songs from YouTube Music or Spotify with your own browser session.

It can:

- open a guided Chrome session for YouTube Music or Spotify
- sign in with your own account
- scrape YouTube Music `Liked Music` or Spotify `Liked Songs`
- export results into `txt`, `csv`, and `json`
- optionally download all or selected YouTube Music tracks with `yt-dlp`
- optionally paste your own YouTube or other `yt-dlp`-supported links directly into the app
- optionally extract MP3 audio through `ffmpeg`
- auto-update source installs from GitHub when you use the repo launchers

The app runs locally and does not use personal API keys.

## Platforms

- Windows
- macOS
- Linux

## Requirements

- Python 3.11 or newer
- Google Chrome
- internet access the first time dependencies are installed

## Get the source

Clone the repo or download the source ZIP from GitHub:

- Repo: [VSTM26/Music-Studio](https://github.com/VSTM26/Music-Studio)

## Install and run

### Windows

```powershell
cd C:\path\to\Music-Studio
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Or double-click:

`run-liked-music-studio.cmd`

or:

`run-liked-music-studio.bat`

### macOS

```bash
cd /path/to/Music-Studio
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

Or:

```bash
chmod +x run-liked-music-studio.command
./run-liked-music-studio.command
```

If macOS blocks the launcher the first time, use `Control-click > Open`, or go to `System Settings > Privacy & Security > Open Anyway`.

### Linux

```bash
cd /path/to/Music-Studio
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

Or:

```bash
chmod +x run-liked-music-studio.sh
./run-liked-music-studio.sh
```

If you use one of the repo launchers, it creates `.venv` when needed, installs `requirements.txt`, checks GitHub for updates, and then starts the app.

## How to use it

1. Start the app.
2. Click `Choose Save Folder` if you want exports somewhere other than the default `output` folder.
3. Pick `YouTube Music` or `Spotify`.
4. Click `Open Guided Chrome`.
5. Sign in inside that guided Chrome window.
6. Leave that window open.
7. Click `Run Export`.
8. Download the generated `txt`, `csv`, or `json` export files.
9. If the export came from YouTube Music, optionally select tracks or use `Download All Exported`.
10. Turn on `Extract audio into MP3 files with ffmpeg` if you want audio-only output.
11. If you already have links, skip the export flow and use the `Direct Links` section instead.

## Project folders

- `output/` stores exports in the repo folder by default
- `output/downloads/` stores YouTube downloads
- `runtime/` stores the guided Chrome profile and updater state
- `public/` contains the browser UI

## Notes

- The scraper uses a dedicated Chrome profile in `runtime/chrome-profile` so each person signs in locally with their own account.
- YouTube downloads reuse that guided Chrome profile with browser cookies, which helps with sign-in-only or age-restricted videos.
- For YouTube downloads that need authentication, Music Studio first exports cookies from the Guided Chrome DevTools session into a `yt-dlp` cookie file so it does not depend on Chrome's locked cookie database.
- Direct-link downloads support pasted YouTube URLs, playlists, and most other links that `yt-dlp` can handle.
- Spotify support is metadata export only. It does not try to download Spotify audio.
- `yt-dlp` installs through `requirements.txt`.
- MP3 extraction can use a system `ffmpeg`, app-local portable `ffmpeg` + `ffprobe`, or the bundled `imageio-ffmpeg` fallback for download-only flows.
- If MP3 extraction is requested and `ffmpeg` or `ffprobe` is missing, the app first tries a full FFmpeg toolchain install with `winget` on Windows or `brew` on macOS, then falls back to downloading portable binaries into `runtime/tools/ffmpeg`.
- If port `4173` is busy, the app automatically moves to the next open local port and logs the new URL.
- On Linux, Chrome can be discovered as `google-chrome`, `google-chrome-stable`, `chromium`, or `chromium-browser`.
- Set `MUSIC_STUDIO_SKIP_UPDATE=1` if you need to skip the source updater while troubleshooting.

## Project layout

- `main.py` - Python entry point
- `liked_music_studio/server.py` - local HTTP server and API
- `liked_music_studio/devtools.py` - Chrome DevTools playlist scraping
- `liked_music_studio/exports.py` - export file writers and manifest helpers
- `liked_music_studio/downloader.py` - `yt-dlp` and `ffmpeg` download flow
- `liked_music_studio/updater.py` - source install updater
- `public/` - browser UI
