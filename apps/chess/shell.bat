@echo off
REM Opens a terminal with .venv_chess active, in this app folder.
cd /d "%~dp0"

if not exist ".venv_chess\Scripts\activate.bat" (
    echo .venv_chess not found. Run run.bat once to create it.
    pause
    exit /b 1
)

cmd /k "call .venv_chess\Scripts\activate.bat"
