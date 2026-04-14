# Music Studio

Music Studio is now a hosted, Google-login-first downloader for YouTube links and YouTube liked videos.

## What it does

- lets a user paste one or more supported media links
- lets a user sign in with Google and pull from their YouTube liked videos
- runs `yt-dlp` on the server
- saves finished files into a folder the user chooses in their own browser
- optionally extracts MP3 audio with `ffmpeg`

## Hosted flow

1. Open the Render site.
2. Click `Choose Local Folder` in Chrome or Edge.
3. Either:
   - paste links and click `Download Pasted Links`, or
   - sign in with Google and click `Download My Liked Videos`
4. Wait for the server job to finish.
5. Music Studio writes the finished files into the chosen folder on the user's machine.

Browsers without the File System Access API can still use the app, but they will need to download finished files manually from the file list.

## Local development

```powershell
cd C:\path\to\Music-Studio
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

The app serves on `PORT` when set, otherwise it defaults to `4173`.

## Render environment variables

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `OAUTH_REDIRECT_URI`

Use your Render app callback URL for `OAUTH_REDIRECT_URI`, for example:

`https://your-app.onrender.com/api/auth/callback`

## Notes

- This version removes the old remote browser / VNC workflow.
- Google sign-in is used for reading a user's YouTube liked videos.
- Pasted links can still be downloaded without Google sign-in.
- The browser-side local folder flow works best on HTTPS in Chromium-based browsers.
