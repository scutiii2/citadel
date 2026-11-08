@echo off
REM Opens a terminal with .venv active, in this app folder.
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo .venv not found. Create it first: uv sync
    pause
    exit /b 1
)

cmd /k "call .venv\Scripts\activate.bat"
