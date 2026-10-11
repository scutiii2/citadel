@echo off
REM Rebuilds the Ascension game UI (web\dist), which the game backend serves.
REM Installs the web dependencies first when web\node_modules is missing.
REM Reload the game in Ember afterwards; no backend restart is needed.

cd /d "%~dp0"

if not exist "web\node_modules" (
    echo Installing web dependencies ...
    call npm --prefix web ci
    if errorlevel 1 goto :failed
)

echo Building Ascension UI ...
call npm --prefix web run build
if errorlevel 1 goto :failed

echo.
echo Build finished: web\dist
pause
exit /b 0

:failed
echo.
echo Build failed.
pause
exit /b 1
