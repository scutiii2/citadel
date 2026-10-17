@echo off
REM Opens a terminal with .venv_catalog active, in this app folder.
cd /d "%~dp0"

if not exist ".venv_catalog\Scripts\activate.bat" (
    echo .venv_catalog not found. Run run.bat once to create it.
    pause
    exit /b 1
)

cmd /k "call .venv_catalog\Scripts\activate.bat"
