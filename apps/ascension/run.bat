@echo off
REM ascension dev launcher - serves the game backend (Ascension) over HTTP on the
REM port in configs\config_app.json (8060 by default).
REM LABEL: Ascension
REM DESCRIPTION: Game backend for Ember (Ascension: collect and battle Ascended). Battle engine, Laya-assisted AI and saved progress. No LLM, no billing.

cd /d "%~dp0"

if not exist ".venv_ascension\Scripts\python.exe" (
    echo Creating virtual environment .venv_ascension ...
    py -m venv .venv_ascension
    call .venv_ascension\Scripts\activate
    echo Installing ascension in editable mode ...
    pip install -e ".[dev]"
) else (
    call .venv_ascension\Scripts\activate
)

:run
py -m src.run

echo.
echo ----------------------------------------
echo  ascension stopped.
choice /C RQ /N /M "Press [R] to restart, [Q] to quit: "
if errorlevel 2 goto :end
if errorlevel 1 goto :run

:end
