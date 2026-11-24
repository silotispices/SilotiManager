@echo off
cd /d "%~dp0"
set "CODEX_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CODEX_PY%" (
    "%CODEX_PY%" "%~dp0siloti_stock_tool.py"
    if errorlevel 1 pause
    exit /b
)
where py >nul 2>nul
if not errorlevel 1 (
    py -3 "%~dp0siloti_stock_tool.py"
    if errorlevel 1 pause
    exit /b
)
echo Python was not found. Install Python 3 from python.org, then run this file again.
pause
