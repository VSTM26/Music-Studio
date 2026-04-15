# Render Setup

Render is no longer the primary product path for Music Studio v1.

The main architecture is now:

- unpacked Chrome extension for the user interface
- local Python helper on `127.0.0.1:4173`
- local Chrome browser session import for YouTube authentication

If this repo is still deployed on Render, treat that deployment as a secondary landing page or documentation surface only. The main download/authentication flow should run locally through the extension and helper.
