# Render Setup

## Environment variables

Add these in your Render service settings:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `OAUTH_REDIRECT_URI=https://your-render-app.onrender.com/api/auth/callback`

## Deploy

Push this repo to GitHub and let Render redeploy from that branch.

The container is now a plain Python web service. It no longer starts Chrome, VNC, noVNC, or nginx.

## Browser recommendation

For the smoothest local-save experience, open the hosted site in Chrome or Edge so the site can write finished files directly into a folder the user chooses.
