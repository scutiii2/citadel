@echo off
REM Opens a terminal with .venv_legion active, in this app folder.
cd /d "%~dp0"

if not exist ".venv_legion\Scripts\activate.bat" (
    echo .venv_legion not found. Create it first: py -m venv .venv_legion ^&^& .venv_legion\Scripts\pip install -e .[dev]
    pause
    exit /b 1
)

cmd /k "call .venv_legion\Scripts\activate.bat"
