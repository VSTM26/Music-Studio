# Desktop Build Notes

Music Studio ships as a packaged desktop GUI app for Windows, macOS, and Linux.

## Local packaging

Build on the target operating system you want to ship for:

```powershell
cd C:\path\to\Music-Studio
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
python scripts/build_desktop_release.py
```

The packaged asset is written to `release/`.

## What gets built

- Windows: `Music-Studio-Windows.zip`
  - contains `Music Studio.exe`
- macOS: `Music-Studio-macOS.zip`
  - contains `Music Studio.app`
- Linux: `Music-Studio-Linux.tar.gz`
  - contains the `Music Studio` executable bundle

## GitHub releases

- pushing a `v*` tag triggers `.github/workflows/release.yml`
- GitHub Actions builds the GUI bundle on each operating system
- the workflow publishes those packaged app files to the matching GitHub release

## Notes

- the desktop UI from `public/desktop.*` is bundled into the packaged app
- runtime data still lives under the user's application-data folder, not inside the app bundle
- if you only want the helper service for testing, run `python main.py --helper-only`
