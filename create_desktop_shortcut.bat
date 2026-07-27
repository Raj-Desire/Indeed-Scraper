@echo off
setlocal
echo Creating Desktop Shortcut for Indeed Scraper...

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_shortcut.ps1"

echo.
pause

