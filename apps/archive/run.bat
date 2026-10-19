@echo off
REM Catalog service dev launcher. Creates .venv_archive on first run and
REM installs this project into it in editable mode.
REM
REM LABEL: Catalog Service
REM DESCRIPTION: Cross-project reuse catalog for mcp_server and ai_agent - scans @catalog-decorated functions/classes and serves them over HTTP.
cd /d "%~dp0"

if not exist ".venv_archive\Scripts\python.exe" (
    echo Creating virtual environment .venv_archive ...
    py -m venv .venv_archive
    call .venv_archive\Scripts\activate
    echo Installing catalog_service in editable mode ...
    pip install -e ".[dev]"
) else (
    call .venv_archive\Scripts\activate
)

:run
py -m src.run

echo.
echo ----------------------------------------
echo  Catalog service stopped.
choice /C RQ /N /M "Press [R] to restart, [Q] to quit: "
if errorlevel 2 goto :end
if errorlevel 1 goto :run

:end
