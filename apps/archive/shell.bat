@echo off
REM Opens a terminal with .venv_archive active, in this app folder.
cd /d "%~dp0"

if not exist ".venv_archive\Scripts\activate.bat" (
    echo .venv_archive not found. Run run.bat once to create it.
    pause
    exit /b 1
)

cmd /k "call .venv_archive\Scripts\activate.bat"
