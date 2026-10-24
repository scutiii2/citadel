@echo off
rem Deploy menu: publish the code to the live branch and/or copy the git-ignored .env and
rem config_*.json files to the deployment machine over scp.
rem Override the target: set DEPLOY_HOST / DEPLOY_DIR before running.
setlocal enabledelayedexpansion
if not defined DEPLOY_HOST set "DEPLOY_HOST=root@scutiserver1.local"
if not defined DEPLOY_DIR set "DEPLOY_DIR=/media/ZimaOS-HD/Apps/Citadel"
set "ROOT=%~dp0.."
set "APPS=apps/armory apps/garrison apps/treasury apps/Ember/ember_api"

:menu
echo.
echo Target: %DEPLOY_HOST%:%DEPLOY_DIR%
echo.
echo   1  Publish code to the live branch
echo   2  Push .env and config files to the server
echo   3  Both (publish, then push)
echo   4  Preview publish ^(dry run^)
echo   5  Preview push ^(dry run^)
echo   Q  Quit
echo.
choice /c 12345Q /n /m "What do you want to do? "
set "PICK=%errorlevel%"
if %PICK%==6 exit /b 0
if %PICK%==1 call :publish
if %PICK%==2 call :push
if %PICK%==3 call :publish && call :push
if %PICK%==4 call :publish --dry-run
if %PICK%==5 call :push --dry-run
goto menu

rem :publish [--dry-run]
:publish
py "%~dp0publish_live.py" %*
if errorlevel 1 (echo Publish failed. & exit /b 1)
if "%~1"=="" call :reminder "Code is on the live branch. On the server:" "git pull"
exit /b 0

rem :push [--dry-run]
:push
set "DRY="
if /i "%~1"=="--dry-run" set "DRY=1"
set /a COUNT=0, FAILED=0
call :send ".env"
call :composefile
for %%A in (%APPS%) do (
    call :send "%%A/.env"
    for %%F in ("%ROOT%\%%A\configs\config_*.json") do call :send "%%A/configs/%%~nxF"
)
echo.
echo Copied !COUNT! file(s), !FAILED! failed.
if !FAILED! gtr 0 (echo Check ssh access to %DEPLOY_HOST% and that %DEPLOY_DIR% exists. & exit /b 1)
if not defined DRY call :reminder ".env and config files are on the server. On the server:" "docker compose up -d --build" "(run git pull first if the code changed; if only .env/config changed, add --force-recreate)"
exit /b 0

rem Make plain "docker compose" on the server use the Zima overlay too (dev .env stays untouched).
:composefile
if defined DRY (echo would set COMPOSE_FILE in the server .env & exit /b 0)
ssh "%DEPLOY_HOST%" "grep -q '^COMPOSE_FILE=' '%DEPLOY_DIR%/.env' || printf '\nCOMPOSE_FILE=docker-compose.yml:docker-compose.zima.yml\n' >> '%DEPLOY_DIR%/.env'"
if errorlevel 1 (echo FAILED  COMPOSE_FILE in server .env & set /a FAILED+=1) else (echo set     COMPOSE_FILE in server .env)
exit /b 0

rem :reminder <heading> <command> [note]
:reminder
echo.
echo ---- NEXT ON THE SERVER ----
echo %~1
echo   cd %DEPLOY_DIR%
echo   %~2
if not "%~3"=="" echo   %~3
echo ----------------------------
exit /b 0

rem :send <path relative to the Citadel root, same path on the server>
:send
set "SRC=%ROOT%\%~1"
if not exist "%SRC%" (echo skip    %~1 ^(missing locally^) & exit /b 0)
if defined DRY (echo would copy %~1 & set /a COUNT+=1 & exit /b 0)
scp -q "%SRC%" "%DEPLOY_HOST%:%DEPLOY_DIR%/%~1"
if errorlevel 1 (echo FAILED  %~1 & set /a FAILED+=1) else (echo copied  %~1 & set /a COUNT+=1)
exit /b 0
