# Music-Studio

Music-Studio is a local desktop-style app for exporting liked songs from YouTube Music or Spotify with your own browser session.

It can:

- open a guided Chrome session for YouTube Music or Spotify
- sign in with your own account
- scrape YouTube Music `Liked Music` or Spotify `Liked Songs`
- export results into `txt`, `csv`, and `json`
- optionally download all or selected YouTube Music tracks with `yt-dlp`
- optionally extract MP3 audio through `ffmpeg`
- auto-update source installs from GitHub
- auto-update packaged release builds through the packaged launcher

The app runs on the user's machine and does not use personal API keys.

## Platforms

- Windows
- macOS
- Linux

## Fastest install

If you want the simplest setup, use the packaged GitHub releases:

- Start from the latest release page: [Music-Studio releases](https://github.com/VSTM26/Music-Studio/releases/latest)
- Windows: download the `windows-x64` archive, extract it, then double-click `run-liked-music-studio.bat`
- macOS Intel: download the `macos-x64` archive, extract it, then run `chmod +x run-liked-music-studio.command` once and open it
- macOS Apple Silicon: download the `macos-arm64` archive, extract it, then run `chmod +x run-liked-music-studio.command` once and open it
- Linux: download the `linux-x64` archive, extract it, then run `chmod +x run-liked-music-studio.sh` once and start it

The packaged launchers check GitHub for newer releases and will run a newer cached build automatically when one exists.
Use the packaged launcher instead of starting the raw binary directly if you want that auto-update behavior.

## Source install

Use the source install if you want to hack on the project or run it directly from the repo.

### Requirements

- Python 3.11 or newer
- Google Chrome
- internet access the first time dependencies are installed

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

If you launch from source with one of the repo launchers, it creates `.venv` when needed, installs `requirements.txt`, and checks GitHub for updates first.

## How to use it

1. Start the app.
2. Click `Choose Save Folder` if you want exports somewhere other than the default folder.
3. Pick `YouTube Music` or `Spotify`.
4. Click `Open Guided Chrome`.
5. Sign in inside that guided Chrome window.
6. Leave that window open.
7. Click `Run Export`.
8. Download the generated `txt`, `csv`, or `json` export files.
9. If the export came from YouTube Music, optionally select tracks or use `Download All Exported`.
10. Turn on `Extract audio into MP3 files with ffmpeg` if you want audio-only output.

## Output

- Export files are written into the selected save folder.
- YouTube downloads go into a `downloads` subfolder inside that save folder.
- The latest export manifest is stored as `latest-export.json`.
- Packaged builds keep runtime data under the user data folder for that OS instead of inside the extracted app folder.

## Notes

- The scraper uses a dedicated Chrome profile so each person signs in locally with their own account.
- YouTube downloads reuse that guided Chrome profile with browser cookies, which helps with sign-in-only or age-restricted videos.
- Spotify support is metadata export only. It does not try to download Spotify audio.
- `yt-dlp` installs through `requirements.txt`.
- MP3 extraction can use a system `ffmpeg` or the bundled `imageio-ffmpeg` fallback.
- If MP3 extraction is requested and `ffmpeg` or `ffprobe` is missing, the app tries to install a full FFmpeg toolchain with `winget` on Windows or `brew` on macOS.
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
- `scripts/build_release.py` - packaged release builder
- `public/` - browser UI
