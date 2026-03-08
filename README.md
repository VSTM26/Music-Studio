# Music-Studio

Music-Studio is a local Python app for Windows and macOS that helps people:

- open a guided Chrome session for YouTube Music or Spotify
- sign in with their own account
- scrape YouTube Music `Liked Music` or Spotify `Liked Songs` through the live browser session
- export the results into `txt`, `csv`, and `json`
- optionally download all or only selected YouTube Music tracks with `yt-dlp`
- optionally extract MP3 audio through `ffmpeg`

The app runs fully on the user's machine. It does not use personal API keys for exporting either source.

## Requirements

- Windows or macOS
- Python 3.11 or newer
- Google Chrome
- `ffmpeg` on `PATH` if you want MP3 extraction

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

If you want MP3 extraction on macOS, install `ffmpeg` first:

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

The app opens at:

`http://127.0.0.1:4173`

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
- Some YouTube Music playlist counts do not perfectly match what the live browser session exposes while scrolling. The app keeps both the reported count and the exported count so the result stays honest.
- Spotify support in this repo is metadata export only. It does not try to download audio from Spotify.
- `yt-dlp` is installed through `requirements.txt`. `ffmpeg` still needs to be installed separately if you want MP3 extraction for YouTube-based downloads.
- On macOS, the app looks for Chrome in both `/Applications` and `~/Applications`. You can always override that with `CHROME_PATH`.
