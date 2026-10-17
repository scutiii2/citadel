@echo off
REM Opens a terminal with .venv_pdf_merger active, in this app folder.
cd /d "%~dp0"

if not exist ".venv_pdf_merger\Scripts\activate.bat" (
    echo .venv_pdf_merger not found. Run run.bat once to create it.
    pause
    exit /b 1
)

cmd /k "call .venv_pdf_merger\Scripts\activate.bat"
