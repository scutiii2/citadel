@echo off
REM Opens a terminal with .venv_ember_cli active, in this app folder.
cd /d "%~dp0"

if not exist ".venv_ember_cli\Scripts\activate.bat" (
    echo .venv_ember_cli not found. Run run.bat once to create it.
    pause
    exit /b 1
)

cmd /k "call .venv_ember_cli\Scripts\activate.bat"
