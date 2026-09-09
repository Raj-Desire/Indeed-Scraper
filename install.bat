@echo off
setlocal enabledelayedexpansion
title Indeed Job Scraper - Setup & Installation
echo ============================================================
echo   Indeed Job Scraper - Automated Setup & Installation
echo ============================================================
echo.

cd /d "%~dp0"

:: -----------------------------------------------------------------------------
:: Step 1: Detect Working Python Installation (checks 'python', 'py -3', 'py')
:: -----------------------------------------------------------------------------
echo [1/5] Detecting Python environment...
set "PY_CMD="

python --version >nul 2>nul
if %errorlevel% equ 0 (
    set "PY_CMD=python"
) else (
    py -3 --version >nul 2>nul
    if %errorlevel% equ 0 (
        set "PY_CMD=py -3"
    ) else (
        py --version >nul 2>nul
        if %errorlevel% equ 0 (
            set "PY_CMD=py"
        )
    )
)

if "%PY_CMD%"=="" (
    echo.
    echo ============================================================
    echo [ERROR] Python is not installed or not found in PATH!
    echo ============================================================
    echo 1. Download Python 3.10+ from: https://www.python.org/downloads/
    echo 2. IMPORTANT: During installation, CHECK the box:
    echo    "Add Python to PATH" or "Add python.exe to PATH"
    echo 3. After installing Python, run this install.bat again.
    echo ============================================================
    echo.
    pause
    exit /b 1
)

echo Python found: %PY_CMD%
%PY_CMD% --version
echo.

:: -----------------------------------------------------------------------------
:: Step 2: Validate or Create Virtual Environment
:: -----------------------------------------------------------------------------
echo [2/5] Setting up virtual environment (venv)...

set "NEED_VENV=0"
if not exist "venv\Scripts\python.exe" (
    set "NEED_VENV=1"
) else (
    :: Test if existing venv is valid (in case folder was copied from another PC)
    venv\Scripts\python.exe -c "exit(0)" >nul 2>nul
    if %errorlevel% neq 0 (
        echo Existing venv is invalid or from another PC. Recreating fresh venv...
        rmdir /s /q venv >nul 2>nul
        set "NEED_VENV=1"
    )
)

if "!NEED_VENV!"=="1" (
    echo Creating fresh virtual environment...
    %PY_CMD% -m venv venv
    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] Failed to create virtual environment with %PY_CMD%!
        echo Trying alternative venv creation...
        python -m venv venv 2>nul
    )
)

if not exist "venv\Scripts\python.exe" (
    echo.
    echo ============================================================
    echo [ERROR] Could not create venv\Scripts\python.exe!
    echo Please make sure you have write permissions in this folder.
    echo ============================================================
    pause
    exit /b 1
)
echo Virtual environment ready.
echo.

:: -----------------------------------------------------------------------------
:: Step 3: Install Required Dependencies
:: -----------------------------------------------------------------------------
echo [3/5] Installing dependencies from requirements.txt...
echo Please wait, this may take 1-2 minutes on first install...

venv\Scripts\python.exe -m pip install --no-warn-script-location -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo [WARNING] Standard install had an issue. Retrying with --prefer-binary...
    venv\Scripts\python.exe -m pip install --prefer-binary --no-warn-script-location -r requirements.txt
    if %errorlevel% neq 0 (
        echo.
        echo ============================================================
        echo [ERROR] Failed to install requirements!
        echo Please check your internet connection and try again.
        echo ============================================================
        pause
        exit /b 1
    )
)
echo Dependencies installed successfully.
echo.

:: -----------------------------------------------------------------------------
:: Step 4: Install Browser Engine
:: -----------------------------------------------------------------------------
echo [4/5] Setting up browser automation engine (Playwright Chromium)...
venv\Scripts\python.exe -m playwright install chromium
if %errorlevel% neq 0 (
    echo [NOTE] Playwright download skipped or using system browser.
    echo The scraper will automatically use your installed Google Chrome if available.
) else (
    echo Browser engine ready.
)
echo.

:: -----------------------------------------------------------------------------
:: Step 5: Environment File & Desktop Shortcut
:: -----------------------------------------------------------------------------
echo [5/5] Finalizing setup...
if not exist ".env" (
    if exist ".env.example" (
        copy /y ".env.example" ".env" >nul
        echo Created default .env configuration file from template.
    )
) else (
    echo Existing .env configuration file found.
)

:: Create Desktop Shortcut
if exist "setup_shortcut.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_shortcut.ps1" >nul 2>nul
    if %errorlevel% equ 0 (
        echo Desktop shortcut created.
    ) else (
        echo Note: Could not create desktop shortcut automatically. You can double-click run_scraper.bat to start.
    )
)

echo.
echo ============================================================
echo   SETUP COMPLETED SUCCESSFULLY!
echo ============================================================
echo You can now:
echo 1. Check/edit credentials in .env (if needed).
echo 2. Double-click the 'Indeed Scraper' icon on your Desktop, OR
echo    double-click 'run_scraper.bat' in this folder to launch.
echo ============================================================
echo.
pause
