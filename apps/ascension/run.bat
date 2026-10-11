@echo off
REM Ascension launcher - builds and serves the game UI and backend on the
REM port in configs\config_app.json (8060 by default).
REM Rebuild after UI edits: npm --prefix web run build.
REM LABEL: Ascension
REM DESCRIPTION: Ascension game UI and API for Ember. Collect and battle Ascended, with Laya-assisted AI and saved progress. No LLM, no billing.

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
if not exist "web\dist\index.html" (
    if exist "web\package.json" (
        echo Building Ascension UI ...
        call npm --prefix web ci
        if errorlevel 1 goto :end
        call npm --prefix web run build
        if errorlevel 1 goto :end
    ) else (
        echo UI sources are not installed yet; starting the backend with the UI-not-built response.
    )
)
python -m src.run

echo.
echo ----------------------------------------
echo  ascension stopped.
choice /C RQ /N /M "Press [R] to restart, [Q] to quit: "
if errorlevel 2 goto :end
if errorlevel 1 goto :run

:end
