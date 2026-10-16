@echo off
rem Run inside a window that stays open, so output survives a double-click or an error.
if not "%PG_TEST_CHILD%"=="1" (
    set "PG_TEST_CHILD=1"
    cmd /k ""%~f0" %*"
    exit /b
)
setlocal
cd /d "%~dp0"
title DB Gateway - Postgres contract test

rem Throwaway local Postgres for tests/test_backend_contract.py.
rem   test_postgres.bat          install Postgres 16 if missing, then run the test
rem   test_postgres.bat remove   uninstall Postgres 16 again
rem The password is a throwaway for a local test server. Never reuse it anywhere else.

set "PG_PASS=gwtest_pw"
set "PG_DB=gwtest"
set "PG_PORT=5432"
set "PG_BIN=C:\Program Files\PostgreSQL\16\bin"
set "PY=.venv_db_gateway\Scripts\python.exe"

if /i "%~1"=="remove" (
    winget uninstall PostgreSQL.PostgreSQL.16
    exit /b %errorlevel%
)

if not exist "%PY%" (
    echo Missing %PY%. Run run.bat once to create the venv, then try again.
    exit /b 1
)

if not exist "%PG_BIN%\psql.exe" (
    echo Installing PostgreSQL 16. Approve the admin prompt if one appears.
    winget install PostgreSQL.PostgreSQL.16 --accept-package-agreements --accept-source-agreements --override "--mode unattended --unattendedmodeui none --superpassword %PG_PASS% --serverport %PG_PORT%"
    if errorlevel 1 (
        echo Install failed. Try again from an administrator terminal.
        exit /b 1
    )
)

rem The installer starts the service. Wait until it accepts connections.
set "READY="
for /l %%i in (1,1,30) do if not defined READY (
    "%PG_BIN%\pg_isready.exe" -q -h localhost -p %PG_PORT% && set "READY=1" || timeout /t 1 /nobreak >nul
)
if not defined READY (
    echo Postgres is not accepting connections on port %PG_PORT%.
    exit /b 1
)

set "PGPASSWORD=%PG_PASS%"
"%PG_BIN%\psql.exe" -U postgres -h localhost -p %PG_PORT% -tAc "SELECT 1 FROM pg_database WHERE datname='%PG_DB%'" | find "1" >nul || "%PG_BIN%\psql.exe" -U postgres -h localhost -p %PG_PORT% -c "CREATE DATABASE %PG_DB%;"

"%PY%" -m pip install -q -e ".[postgres]"
if errorlevel 1 exit /b 1

set "DB_GATEWAY_TEST_POSTGRES_DSN=postgresql://postgres:%PG_PASS%@localhost:%PG_PORT%/%PG_DB%"
"%PY%" -m pytest tests/test_backend_contract.py -rs
exit /b %errorlevel%
