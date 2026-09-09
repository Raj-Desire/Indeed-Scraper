@echo off
title Indeed Job Scraper - Initial Setup & Installation
echo ============================================================
echo   Indeed Job Scraper - 1-Click Setup & Installation
echo ============================================================
echo.

cd /d "%~dp0"

:: 1. Check Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10 or higher from python.org
    echo Make sure to check 'Add Python to PATH' during installation.
    echo.
    pause
    exit /b 1
)

echo [1/5] Checking Python installation...
python --version

:: 2. Create Virtual Environment if not present
if not exist "venv\Scripts\python.exe" (
    echo.
    echo [2/5] Creating Python virtual environment (venv)...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment!
        pause
        exit /b 1
    )
) else (
    echo.
    echo [2/5] Virtual environment already exists.
)

:: 3. Install Requirements
echo.
echo [3/5] Installing required dependencies from requirements.txt...
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\pip.exe install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Python dependencies!
    pause
    exit /b 1
)

:: 4. Install Playwright Chromium Browser
echo.
echo [4/5] Setting up browser automation engine...
venv\Scripts\playwright.exe install chromium

:: 5. Create .env template if missing
echo.
echo [5/5] Checking environment configuration (.env)...
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo Created default .env from template.
    )
) else (
    echo Existing .env file found.
)

:: Create Desktop Shortcut
echo.
echo Creating Desktop Shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_shortcut.ps1"

echo.
echo ============================================================
echo   SETUP COMPLETED SUCCESSFULLY!
echo ============================================================
echo 1. Edit your credentials in .env (if needed).
echo 2. Double-click 'Indeed Scraper' on your Desktop to run!
echo ============================================================
echo.
pause
