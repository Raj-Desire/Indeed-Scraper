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

:: Check for Python in virtual environment first, then system PATH
if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if %errorlevel% neq 0 (
        echo [ERROR] Python is not installed or not in PATH!
        echo Please install Python 3.10+ and add it to PATH.
        pause
        exit /b 1
    )
    set "PYTHON_EXE=python"
)

:: Run application
"%PYTHON_EXE%" main.py


echo.
echo Application stopped.
pause
