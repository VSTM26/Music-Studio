@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  set "BOOTSTRAP_PYTHON="
  set "BOOTSTRAP_ARGS="

  where py >nul 2>nul
  if not errorlevel 1 (
    set "BOOTSTRAP_PYTHON=py"
    set "BOOTSTRAP_ARGS=-3"
  ) else (
    where python >nul 2>nul
    if not errorlevel 1 (
      set "BOOTSTRAP_PYTHON=python"
    )
  )

  if not defined BOOTSTRAP_PYTHON (
    echo Python 3 was not found on PATH.
    echo Install Python 3.11 or newer, then run this launcher again.
    pause
    exit /b 1
  )

  echo Creating virtual environment...
  call %BOOTSTRAP_PYTHON% %BOOTSTRAP_ARGS% -m venv .venv
  if errorlevel 1 (
    echo Failed to create the virtual environment.
    pause
    exit /b 1
  )
)

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Failed to install dependencies.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" main.py
