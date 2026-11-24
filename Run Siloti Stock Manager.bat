@echo off
cd /d "%~dp0"
set "CODEX_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CODEX_PY%" (
    "%CODEX_PY%" "%~dp0server.py"
    if errorlevel 1 pause
    exit /b
)
where py >nul 2>nul
if not errorlevel 1 (
    py -3 "%~dp0server.py"
    if errorlevel 1 pause
    exit /b
)
where python >nul 2>nul
if not errorlevel 1 (
    python "%~dp0server.py"
    if errorlevel 1 pause
    exit /b
)
echo Python 3 was not found. Install Python 3, then run this file again.
pause
