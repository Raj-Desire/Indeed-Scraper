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
$shortcut.Save()

Write-Host "============================================================"
Write-Host "SUCCESS! Desktop shortcut created at:"
Write-Host "  $shortcutPath"
Write-Host "============================================================"
