# Desktop Build Notes

Music Studio is now designed to run as a desktop app on Windows, macOS, and Linux.

## Recommended packager

Use `PyInstaller`.

Important: build on each target operating system separately.

- build Windows releases on Windows
- build macOS releases on macOS
- build Linux releases on Linux

## Basic build flow

```powershell
cd C:\path\to\Music-Studio
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --name "Music Studio" --windowed --add-data "public;public" main.py
```

## Notes

- `public/` must be bundled because it contains the desktop UI.
- the app writes runtime data under the user's local application data directory, not inside the bundled app folder.
- if you only want the backend service, run:

```powershell
python main.py --helper-only
```
