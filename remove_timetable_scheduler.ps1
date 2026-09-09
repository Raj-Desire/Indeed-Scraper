# Unregister Timetable Indeed Scraper from Windows Task Scheduler
$taskName = "IndeedHourlyTimetableScraper"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Removing Indeed Hourly Timetable Task from Task Scheduler" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Task Name: $taskName"
Write-Host ""

try {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
    Write-Host "✅ SUCCESS! Task '$taskName' has been removed from Windows Task Scheduler." -ForegroundColor Green
} catch {
    if ($_.Exception.Message -like "*No mapping between account names*" -or $_.Exception.Message -like "*cannot find the file*") {
        Write-Host "ℹ️ Task '$taskName' was not found (it was already removed or never registered)." -ForegroundColor Yellow
    } else {
        Write-Host "⚠️ Error removing task: $_" -ForegroundColor Red
        Write-Host "Please make sure you run PowerShell as Administrator." -ForegroundColor Yellow
    }
}
