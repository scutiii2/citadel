@echo off
REM ai_agent dev launcher - starts every agent in agents\*.json (copy
REM agents\agents.json.template to start) under src.supervisor, one child
REM process per agent on that file's port.
REM LABEL: AI Agent
REM DESCRIPTION: Starts every configured AI agent (agents\*.json) - each talks to mcp_server as an MCP client and serves MCP to ember_api.

cd /d "%~dp0"

if not exist ".venv_ai_agent\Scripts\python.exe" (
    echo Creating virtual environment .venv_ai_agent ...
    py -m venv .venv_ai_agent
    call .venv_ai_agent\Scripts\activate
    echo Installing ai_agent in editable mode ...
    pip install -e ".[dev]"
) else (
    call .venv_ai_agent\Scripts\activate
)

:run
py -m src.supervisor

echo.
echo ----------------------------------------
echo  ai_agent supervisor stopped.
choice /C RQ /N /M "Press [R] to restart, [Q] to quit: "
if errorlevel 2 goto :end
if errorlevel 1 goto :run

:end
