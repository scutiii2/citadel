@echo off
REM Opens a terminal with .venv_launcher active, in this app folder.
cd /d "%~dp0"

if not exist ".venv_launcher\Scripts\activate.bat" (
    echo .venv_launcher not found. Run run.bat once to create it.
    pause
    exit /b 1
)

cmd /k "call .venv_launcher\Scripts\activate.bat"
