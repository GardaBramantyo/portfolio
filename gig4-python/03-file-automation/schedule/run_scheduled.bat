@echo off
REM Runs the file automation job (organize + merge). Point Windows Task Scheduler at this file.
REM Uses .venv\Scripts\python.exe if a virtual environment exists, otherwise "python" on PATH.
cd /d "%~dp0.."
if not exist logs mkdir logs
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" file_automator.py run --config config.toml >> logs\scheduled.log 2>&1
exit /b %ERRORLEVEL%
