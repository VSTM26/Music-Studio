# Google OAuth Setup

## Required environment variables

Set these on Render:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `OAUTH_REDIRECT_URI`

Example redirect URI:

`https://your-render-app.onrender.com/api/auth/callback`

## Google Cloud Console

1. Create or open a Google Cloud project.
2. Enable the YouTube Data API v3.
3. Create an OAuth client of type `Web application`.
4. Add your Render callback URL to the authorized redirect URIs list.

## Scope used by the app

- `https://www.googleapis.com/auth/youtube.readonly`

That scope is used to read the signed-in user's YouTube liked videos.
