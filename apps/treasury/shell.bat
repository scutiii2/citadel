@echo off
REM Opens a terminal with .venv_treasury active, in this app folder.
cd /d "%~dp0"

if not exist ".venv_treasury\Scripts\activate.bat" (
    echo .venv_treasury not found. Create it first: py -m venv .venv_treasury ^&^& .venv_treasury\Scripts\pip install -e .[dev]
    pause
    exit /b 1
)

cmd /k "call .venv_treasury\Scripts\activate.bat"
