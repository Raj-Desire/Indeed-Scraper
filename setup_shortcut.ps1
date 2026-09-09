$desktop = [System.Environment]::GetFolderPath('Desktop')
if (-not (Test-Path $desktop)) {
    $desktop = Join-Path $env:USERPROFILE "Desktop"
    if (-not (Test-Path $desktop)) {
        New-Item -ItemType Directory -Path $desktop -Force | Out-Null
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$targetBat = Join-Path $scriptDir "run_scraper.bat"
$shortcutPath = Join-Path $desktop "Indeed Scraper.lnk"

$wsShell = New-Object -ComObject WScript.Shell
$shortcut = $wsShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetBat
$shortcut.WorkingDirectory = $scriptDir
$shortcut.Description = "Launch Indeed Job Scraper UI"

# Set application icon
$venvPython = Join-Path $scriptDir "venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $shortcut.IconLocation = "$venvPython,0"
} else {
    $shortcut.IconLocation = "shell32.dll,220"
}

$shortcut.Save()

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " SUCCESS! Desktop shortcut created successfully:" -ForegroundColor Green
Write-Host "   $shortcutPath" -ForegroundColor White
Write-Host " You can now double-click 'Indeed Scraper' on your Desktop." -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

