# OAuth Setup Guide for render.com Deployment

## Overview
This guide explains how to set up Google OAuth for the "Download from Link" feature on your render.com deployment.

## What Was Added
- Google OAuth 2.0 authentication for direct YouTube downloads
- Users can now sign in with Google to get authorized access
- Tokens are stored server-side and used for authenticated yt-dlp downloads
- **Note**: Export Music Library still uses Guided Chrome (unchanged)

## Setup Steps

### 1. Create a Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the YouTube Data API v3 (search for it in APIs & Services > Library)

### 2. Create OAuth 2.0 Credentials
1. Go to APIs & Services > Credentials
2. Click "Create Credentials" > "OAuth client ID"
3. If prompted, create a consent screen first:
   - User Type: External
   - Scopes: Add these:
     - `https://www.googleapis.com/auth/youtube.readonly`
     - `https://www.googleapis.com/auth/youtube.force-ssl`
4. For Application type, choose "Web application"
5. Add Authorized redirect URIs:
   - `https://your-render-app.onrender.com/api/auth/callback`
   - `http://localhost:4173/api/auth/callback` (for local testing)
6. Copy the Client ID and Client Secret

### 3. Set Environment Variables on render.com
In your render.com service settings, add these environment variables:

```
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here
OAUTH_REDIRECT_URI=https://your-render-app.onrender.com/api/auth/callback
```

Replace `your-render-app.onrender.com` with your actual render.com domain.

### 4. Deploy Changes
Push these changes to your repository:
- `requirements.txt` (updated with google-auth-oauthlib, ytmusic)
- `main.py` (updated dependencies check)
- `liked_music_studio/oauth.py` (new file)
- `liked_music_studio/server.py` (updated with OAuth endpoints)
- `public/index.html` (updated UI)
- `public/app.js` (updated JavaScript)

render.com will automatically redeploy and install new dependencies.

## How It Works

### User Workflow
1. User goes to "Download from Link" section
2. Clicks "Sign in with Google" button
3. Gets redirected to Google's OAuth consent screen
4. Authorizes the app
5. Gets redirected back, token stored
6. Pastes YouTube links and downloads

### Behind the Scenes
1. `/api/auth/start` generates OAuth URL with secure state token
2. User authorizes on Google
3. Google redirects to `/api/auth/callback` with authorization code
4. Server exchanges code for access token
5. Token stored in `runtime/oauth/youtube_oauth_token.json`
6. Direct downloads use token for authentication

## Troubleshooting

### "OAuth not configured" error
- Make sure all three environment variables are set on render.com
- Check that credentials are correct in Google Cloud Console

### "Failed to exchange code for token"
- Verify the redirect URI exactly matches in Google Cloud Console
- Check that OAUTH_REDIRECT_URI environment variable matches

### Downloads still require sign-in
- The token provides authorization but some videos may still require additional verification
- Users can open Guided Chrome as a fallback for special cases

## Optional: Local Testing
For local development, you can test OAuth:
1. Set environment variables locally:
   ```
   export GOOGLE_CLIENT_ID=your_client_id
   export GOOGLE_CLIENT_SECRET=your_client_secret
   export OAUTH_REDIRECT_URI=http://localhost:4173/api/auth/callback
   ```
2. Run the app normally
3. Use the sign-in flow to test

## Notes
- OAuth tokens are per-session (stored in `runtime/oauth/`)
- Users can sign out at any time
- Export Music Library workflow is unchanged (still uses Guided Chrome)
- For most public YouTube videos, OAuth signup is optional but recommended
- For private/restricted videos, users can still use Guided Chrome
