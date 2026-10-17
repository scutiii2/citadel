@echo off
REM Opens a terminal with .venv_db_gateway active, in this app folder.
cd /d "%~dp0"

if not exist ".venv_db_gateway\Scripts\activate.bat" (
    echo .venv_db_gateway not found. Run run.bat once to create it.
    pause
    exit /b 1
)

cmd /k "call .venv_db_gateway\Scripts\activate.bat"
