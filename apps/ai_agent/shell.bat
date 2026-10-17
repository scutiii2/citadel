@echo off
REM Opens a terminal with .venv_ai_agent active, in this app folder.
cd /d "%~dp0"

if not exist ".venv_ai_agent\Scripts\activate.bat" (
    echo .venv_ai_agent not found. Run run.bat once to create it.
    pause
    exit /b 1
)

cmd /k "call .venv_ai_agent\Scripts\activate.bat"
