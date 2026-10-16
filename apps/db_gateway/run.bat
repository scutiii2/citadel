@echo off
REM db_gateway dev launcher - serves database instances over HTTP on the
REM port in configs\config_app.json (8071 by default).
REM LABEL: DB Gateway
REM DESCRIPTION: Database gateway: named instances that share cached connections to SQLite, SQL and Firestore. No LLM, no billing.

cd /d "%~dp0"

REM server_launcher reads this default port; src\config.py lets DB_GATEWAY_PORT override the config.
set DB_GATEWAY_PORT=8071

if not exist ".venv_db_gateway\Scripts\python.exe" (
    echo Creating virtual environment .venv_db_gateway ...
    py -m venv .venv_db_gateway
    call .venv_db_gateway\Scripts\activate
    echo Installing db_gateway in editable mode ...
    pip install -e ".[dev]"
) else (
    call .venv_db_gateway\Scripts\activate
)

:run
py -m src.run

echo.
echo ----------------------------------------
echo  db_gateway stopped.
choice /C RQ /N /M "Press [R] to restart, [Q] to quit: "
if errorlevel 2 goto :end
if errorlevel 1 goto :run

:end
