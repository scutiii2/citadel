@echo off
REM chat_cli launcher. Creates .venv_ember_cli on first run and installs this
REM project into it in editable mode. Arguments are passed on:
REM   run.bat --user ada --ask
REM An interactive terminal chat, not a server, so server_launcher skips it:
REM LAUNCHER: skip
cd /d "%~dp0"

if not exist ".venv_ember_cli\Scripts\python.exe" (
    echo Creating virtual environment .venv_ember_cli ...
    py -m venv .venv_ember_cli
    call .venv_ember_cli\Scripts\activate
    echo Installing chat_cli in editable mode ...
    pip install -e ".[dev]"
) else (
    call .venv_ember_cli\Scripts\activate
)

py -m src.main %*
