@echo off
rem Run inside a window that stays open, so output survives a double-click or an error.
if not "%FS_TEST_CHILD%"=="1" (
    set "FS_TEST_CHILD=1"
    cmd /k ""%~f0" %*"
    exit /b
)
setlocal
cd /d "%~dp0"
title DB Gateway - Firestore contract test

rem Runs tests/test_backend_contract.py against the local Firestore emulator.
rem Needs Java and Node. Missing ones are installed with winget, then run this again
rem in a new terminal so the new PATH is picked up.
rem The emulator starts for the test and stops afterwards. No real project is used.

set "PY=.venv_db_gateway\Scripts\python.exe"

if not exist "%PY%" (
    echo Missing %PY%. Run run.bat once to create the venv, then try again.
    exit /b 1
)

rem firebase-tools needs Java 21 or newer. An older Java (such as 8) may come first on PATH,
rem so put an installed Temurin 21 in front of it for this run.
for /d %%d in ("C:\Program Files\Eclipse Adoptium\jre-21*" "C:\Program Files\Eclipse Adoptium\jdk-21*") do set "PATH=%%~d\bin;%PATH%"

set "JAVA_MAJOR=0"
for /f "tokens=3" %%v in ('java -version 2^>^&1 ^| findstr /i "version"') do for /f "delims=." %%m in ("%%~v") do set "JAVA_MAJOR=%%m"
if %JAVA_MAJOR% lss 21 (
    echo Found Java %JAVA_MAJOR%, but 21 or newer is needed. Installing Temurin 21. This leaves your other Java alone.
    winget install EclipseAdoptium.Temurin.21.JRE --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo Install failed. Accept the administrator prompt when it appears, then run this script again.
        exit /b 1
    )
    echo Java 21 installed. Run this script again.
    exit /b 1
)

where node >nul 2>&1 || (
    echo Installing Node.js LTS.
    winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
    echo Node installed. Open a new terminal and run this script again.
    exit /b 1
)

"%PY%" -m pip install -q -e ".[firestore]"
if errorlevel 1 exit /b 1

rem emulators:exec starts the emulator, sets FIRESTORE_EMULATOR_HOST, runs the command, stops it.
call npx --yes firebase-tools emulators:exec --only firestore --project demo-test "%PY% -m pytest tests/test_backend_contract.py -rs"
exit /b %errorlevel%
