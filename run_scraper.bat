@echo off
title Indeed Job Scraper
echo ============================================================
echo Starting Indeed Job Scraper Application...
echo Please wait, browser will open automatically in a moment.
echo Do not close this window while using the scraper.
echo ============================================================
echo.

:: Navigate to script directory
cd /d "%~dp0"

:: Check for virtual environment; if missing, auto-run install.bat
if not exist "venv\Scripts\python.exe" (
    echo [NOTE] Virtual environment not found. Launching initial setup...
    echo.
    call install.bat
    if not exist "venv\Scripts\python.exe" (
        exit /b 1
    )
)

set "PYTHON_EXE=venv\Scripts\python.exe"


:: Run application
"%PYTHON_EXE%" main.py


echo.
echo Application stopped.
pause
