# Render.com Environment Variables Setup

To make OAuth authentication work on render.com, you need to set these environment variables in your render.com dashboard:

## Steps:

1. Go to https://dashboard.render.com
2. Select your service: **music-studio** (or whatever your service is named)
3. Go to **Settings** → **Environment**
4. Add these three environment variables:

### Variable 1: GOOGLE_CLIENT_ID
- **Key**: `GOOGLE_CLIENT_ID`
- **Value**: `60550032844-nvo233680ksmqm53ubd9u3ae6au5mdhh.apps.googleusercontent.com`

### Variable 2: GOOGLE_CLIENT_SECRET
- **Key**: `GOOGLE_CLIENT_SECRET`
- **Value**: Your client secret from Google Cloud Console (from client_secret.json)
- *Note: This is sensitive - do NOT commit to GitHub*

### Variable 3: OAUTH_REDIRECT_URI
- **Key**: `OAUTH_REDIRECT_URI`
- **Value**: `https://music-studio-uwdb.onrender.com/api/auth/callback`
- *Important: Must match exactly what you configured in Google Cloud Console*

## After Setting Variables:

1. Click **Save**
2. Your service will automatically redeploy
3. Wait 2-3 minutes for the deployment to complete
4. Test by visiting https://music-studio-uwdb.onrender.com and clicking "Sign in with Google"

## Where to Find These Values:

- **GOOGLE_CLIENT_ID & GOOGLE_CLIENT_SECRET**: 
  - Google Cloud Console → Your Project → Credentials → OAuth 2.0 Client IDs → Download JSON
  - OR from the client_secret.json file you downloaded earlier

## Troubleshooting:

If OAuth still fails:
1. Double-check the OAUTH_REDIRECT_URI matches exactly in Google Cloud Console
2. Make sure GOOGLE_CLIENT_SECRET is the actual secret, not the Client ID
3. Check render.com deployment logs for error messages

