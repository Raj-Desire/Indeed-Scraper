# Setup Windows Task Scheduler for Hourly Indeed Scraping via Centralized Timetable
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$batchFile = Join-Path $scriptDir "run_scheduled.bat"
$taskName = "IndeedHourlyTimetableScraper"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Registering Centralized Timetable in Windows Task Scheduler" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Task Name:   $taskName"
Write-Host "Schedule:    Repeats Hourly (24/7) to check config\schedule.json"
Write-Host "Target:      $batchFile"
Write-Host ""

try {
    # Action
    $action = New-ScheduledTaskAction -Execute $batchFile -Argument "--timetable" -WorkingDirectory $scriptDir
    
    # Trigger: Starts today at midnight and repeats every 1 hour
    $startDate = (Get-Date).Date
    $trigger = New-ScheduledTaskTrigger -Once -At $startDate -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 1000)
    
    # Settings: Start on batteries, wake if available
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

    # Register task
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

    Write-Host "✅ SUCCESS! Task '$taskName' registered successfully." -ForegroundColor Green
    Write-Host ""
    Write-Host "How it works:" -ForegroundColor Cyan
    Write-Host "1. Task Scheduler wakes up every hour." -ForegroundColor White
    Write-Host "2. It checks config\schedule.json for the current hour (e.g. 13:00 -> sharepoint, 14:00 -> AI)." -ForegroundColor White
    Write-Host "3. If a slot is scheduled, it scrapes, enriches descriptions, saves Excel, and syncs." -ForegroundColor White
    Write-Host "4. If no job is scheduled for that hour, it quietly exits with zero CPU usage." -ForegroundColor White
    Write-Host ""
    Write-Host "To change times or keywords, simply edit config\schedule.json anytime!" -ForegroundColor Yellow
} catch {
    Write-Host "⚠️ Warning: Task registration failed: $_" -ForegroundColor Yellow
    Write-Host "Please make sure you run PowerShell as Administrator." -ForegroundColor Yellow
}
