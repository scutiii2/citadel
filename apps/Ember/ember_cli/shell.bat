@echo off
REM Opens a terminal with .venv_ember_cli active, in this app folder.
cd /d "%~dp0"

if not exist ".venv_ember_cli\Scripts\activate.bat" (
    echo .venv_ember_cli not found. Create it first: py -m venv .venv_ember_cli ^&^& .venv_ember_cli\Scripts\pip install -e .[dev]
    pause
    exit /b 1
)

cmd /k "call .venv_ember_cli\Scripts\activate.bat"
