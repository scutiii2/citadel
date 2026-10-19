@echo off
rem Publish the deployment files to the live branch. Pass --dry-run to preview.
py "%~dp0publish_live.py" %*
echo.
pause
