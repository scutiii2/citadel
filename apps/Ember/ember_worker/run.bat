@echo off
REM ember_worker launcher. Creates .venv_ember_worker on first run and installs
REM this project into it in editable mode. Arguments are passed through:
REM   run.bat pair <ember_url> <token> --provider claude
REM   run.bat status
REM   run.bat                      (connects every paired worker)
REM
REM LABEL: Ember Worker
REM DESCRIPTION: Connects your own Claude Code and Codex CLIs to Ember's Forge page.
REM LAUNCHER: skip
cd /d "%~dp0"

if not exist ".venv_ember_worker\Scripts\python.exe" (
    echo Creating virtual environment .venv_ember_worker ...
    py -m venv .venv_ember_worker
    call .venv_ember_worker\Scripts\activate
    echo Installing ember_worker in editable mode ...
    pip install -e ".[dev]"
) else (
    call .venv_ember_worker\Scripts\activate
)

python -m src.run %*
