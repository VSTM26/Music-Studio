# Liked Music Studio

Liked Music Studio is a local Python app for Windows that helps people:

- open a guided Chrome session for YouTube Music
- sign in with their own account
- scrape the `Liked Music` playlist through the live browser session
- export the results into `txt`, `csv`, and `json`
- optionally download all or only selected tracks with `yt-dlp`
- optionally extract MP3 audio through `ffmpeg`

The app runs fully on the user's machine. It does not need Google Cloud OAuth setup.

## Requirements

- Windows
- Python 3.11 or newer
- Google Chrome
- `ffmpeg` on `PATH` if you want MP3 extraction

## Install

```powershell
cd D:\liked-music-studio
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```powershell
cd D:\liked-music-studio
.venv\Scripts\activate
python main.py
```

Or double-click:

`run-liked-music-studio.cmd`

The app opens at:

`http://127.0.0.1:4173`

## How to use it

1. Start the app.
2. Click `Choose Save Folder` if you want exports somewhere other than the default `output` folder.
3. Click `Open Guided Chrome`.
4. Sign in to YouTube Music in that guided Chrome window.
5. Leave Guided Chrome open.
6. Click `Run Export`.
7. Download the generated `txt`, `csv`, or `json` export files.
8. Optionally select some tracks or use `Download All Exported`.
9. Turn on `Extract audio into MP3 files with ffmpeg` if you want audio-only output.

## Output layout

- Export files are written directly into the selected save folder.
- Media downloads are written into a `downloads` subfolder inside that save folder.
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
- `yt-dlp` is installed through `requirements.txt`. `ffmpeg` still needs to be installed separately if you want MP3 extraction.
