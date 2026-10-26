@echo off
rem Build and (re)start the legion container from the root docker-compose.yml on this machine.
rem Needs Docker Desktop running and a root .env with INTERNAL_API_TOKEN. Extra args go to "up"
rem (e.g. dev_deploy.bat --no-deps). Dependencies that are not running yet are started, not rebuilt.
setlocal
set "SERVICE=legion"
pushd "%~dp0../.." || exit /b 1

docker compose up -d --build %* %SERVICE%
if errorlevel 1 (
    echo.
    echo Deploy of %SERVICE% failed.
    popd
    pause
    exit /b 1
)

echo.
docker compose ps %SERVICE%
echo.
echo Logs:  docker compose logs -f %SERVICE%

popd
pause
