# Remove Daily Indeed Scraper from Windows Task Scheduler
$taskName = "IndeedDailyJobScraper"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Removing Daily Indeed Scraper from Windows Task Scheduler" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# Check if task exists
$taskExists = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($taskExists) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "✅ SUCCESS! Task '$taskName' has been completely deleted." -ForegroundColor Green
} else {
    Write-Host "ℹ️ Task '$taskName' is not currently registered. Nothing to delete." -ForegroundColor Yellow
}
