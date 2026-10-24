@echo off
REM Opens a terminal with .venv_garrison active, in this app folder.
cd /d "%~dp0"

if not exist ".venv_garrison\Scripts\activate.bat" (
    echo .venv_garrison not found. Create it first: py -m venv .venv_garrison ^&^& .venv_garrison\Scripts\pip install -e .[dev]
    pause
    exit /b 1
)

cmd /k "call .venv_garrison\Scripts\activate.bat"
