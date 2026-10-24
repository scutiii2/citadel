@echo off
REM Opens a terminal with .venv_mcp active, in this app folder.
cd /d "%~dp0"

if not exist ".venv_mcp\Scripts\activate.bat" (
    echo .venv_mcp not found. Create it first: py -m venv .venv_mcp ^&^& .venv_mcp\Scripts\pip install -e .[dev]
    pause
    exit /b 1
)

cmd /k "call .venv_mcp\Scripts\activate.bat"
