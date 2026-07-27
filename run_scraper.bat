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

:: Check if python is available
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

:: Run application
python main.py

echo.
echo Application stopped.
pause
