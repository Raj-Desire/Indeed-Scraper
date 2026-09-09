# Setup Windows Task Scheduler for Daily Indeed Scraping
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$batchFile = Join-Path $scriptDir "run_scheduled.bat"
$taskName = "IndeedDailyJobScraper"
$time = "08:00"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Registering Daily Indeed Scraper in Windows Task Scheduler" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Task Name:   $taskName"
Write-Host "Schedule:    Daily at $time AM"
Write-Host "Target:      $batchFile"
Write-Host ""

try {
    # Native PowerShell registration handles paths with spaces perfectly
    $action = New-ScheduledTaskAction -Execute $batchFile -WorkingDirectory $scriptDir
    $trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]"$time")
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

    Write-Host "✅ SUCCESS! Task '$taskName' registered successfully." -ForegroundColor Green
    Write-Host "The scraper will automatically run every day at $time AM," -ForegroundColor Green
    Write-Host "enrich full descriptions, evaluate AI matches, sync to SharePoint, and email you." -ForegroundColor Green
} catch {
    Write-Host "⚠️ Warning: Task registration failed: $_" -ForegroundColor Yellow
    Write-Host "Please make sure you run PowerShell as Administrator." -ForegroundColor Yellow
}
