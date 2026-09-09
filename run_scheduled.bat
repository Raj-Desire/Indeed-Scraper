@echo off
setlocal enabledelayedexpansion

:: Navigate to project root directory
cd /d "%~dp0"

echo ======================================================================
echo [%date% %time%] Triggering Daily Scheduled Indeed Scraper
echo ======================================================================

:: Ensure virtual environment exists
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found in venv\Scripts\python.exe!
    pause
    exit /b 1
)

:: Default search parameters when run automatically by Task Scheduler
:: Runs in timetable mode matching the current time in config\schedule.json
if "%~1"=="" (
    set ARGS=--timetable
) else (
    set ARGS=%*
)

:: Run the scheduled headless scrape
venv\Scripts\python.exe scripts\run_scheduled_scrape.py !ARGS!

set EXIT_CODE=%ERRORLEVEL%
echo.
echo ======================================================================
echo [%date% %time%] Scheduled Run Finished with Exit Code: !EXIT_CODE!
echo ======================================================================

exit /b !EXIT_CODE!
