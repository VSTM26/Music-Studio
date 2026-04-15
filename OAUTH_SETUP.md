# Google OAuth Setup

Google OAuth is now **legacy** in this repo.

Music Studio v1 no longer depends on hosted Google login for the main YouTube flow. The intended product path is:

1. load the unpacked Chrome extension
2. sign into YouTube in Chrome
3. import the user's current browser session
4. let the local helper use that session for downloads

The older OAuth files can stay in the repo temporarily for compatibility work, but they are not the primary path for YouTube likes anymore.
