@echo off
REM chess dev launcher - serves the chess and Tetris backend over HTTP on the
REM port in configs\config_app.json (8060 by default).
REM LABEL: Chess
REM DESCRIPTION: Game backend for Ember (chess, Tetris): engines, a Laya-assisted opponent and per-user game sessions. No LLM, no billing.

cd /d "%~dp0"

if not exist ".venv_chess\Scripts\python.exe" (
    echo Creating virtual environment .venv_chess ...
    py -m venv .venv_chess
    call .venv_chess\Scripts\activate
    echo Installing chess in editable mode ...
    pip install -e ".[dev]"
) else (
    call .venv_chess\Scripts\activate
)

:run
py -m src.run

echo.
echo ----------------------------------------
echo  chess stopped.
choice /C RQ /N /M "Press [R] to restart, [Q] to quit: "
if errorlevel 2 goto :end
if errorlevel 1 goto :run

:end
