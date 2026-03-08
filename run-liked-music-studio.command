#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

bootstrap_python=""
if [ -x ".venv/bin/python3" ]; then
  bootstrap_python=".venv/bin/python3"
elif [ -x ".venv/bin/python" ]; then
  bootstrap_python=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  bootstrap_python="python3"
elif command -v python >/dev/null 2>&1; then
  bootstrap_python="python"
else
  echo "Python 3 was not found on PATH."
  echo "Install Python 3.11 or newer, then run this launcher again."
  exit 1
fi

if [ ! -x ".venv/bin/python3" ] && [ ! -x ".venv/bin/python" ]; then
  echo "Creating virtual environment..."
  "$bootstrap_python" -m venv .venv
fi

venv_python=".venv/bin/python3"
if [ ! -x "$venv_python" ]; then
  venv_python=".venv/bin/python"
fi

echo "Checking for updates..."
"$venv_python" -m liked_music_studio.updater

echo "Installing dependencies..."
"$venv_python" -m pip install -r requirements.txt

exec "$venv_python" main.py
