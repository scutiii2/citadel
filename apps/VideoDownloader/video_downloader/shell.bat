@echo off
REM Opens a terminal with .venv_video_downloader active, in this app folder.
cd /d "%~dp0"

if not exist ".venv_video_downloader\Scripts\activate.bat" (
    echo .venv_video_downloader not found. Run run.bat once to create it.
    pause
    exit /b 1
)

cmd /k "call .venv_video_downloader\Scripts\activate.bat"
