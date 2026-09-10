# Design Specification: Stagnant Scraper Auto-Complete & Email Dispatch

## Background & Problem
When scraping Indeed across multiple countries, anti-scraping protections or empty results across subsequent pagination pages may cause the scraper to hang, idle, or loop through empty pages without finding further leads.
In this state:
- No error is raised.
- The web frontend continues polling `GET /api/leads` every 2 seconds, generating repeated console log entries:
  `INFO: 127.0.0.1:<port> - "GET /api/leads HTTP/1.1" 200 OK`
- The scraper does not terminate naturally, which prevents the completion pipeline from running. Consequently, the progress does not reach 100%, and the completion email notification containing the scraped Excel workbook is never dispatched, risking data stalling and user inconvenience.

## Goal
Implement a sequence watchdog that monitors `GET /api/leads` requests while scraping is active:
1. If 20 consecutive `GET /api/leads` requests are made with no increase in discovered leads, detect stagnation.
2. If new leads are discovered before reaching 20, reset the counter to 0.
3. Upon reaching 20 stagnant polls:
   - Gracefully terminate the Playwright scraping loop.
   - Set progress status to `COMPLETED` and progress percentage to `100%`.
   - Export all collected leads into an Excel workbook.
   - Run SharePoint sync (if configured).
   - Dispatch the email report with the attached Excel file to designated recipients.
   - Broadcast completion via WebSocket to finalize the frontend UI.

---

## Component Architecture & Detailed Design

### 1. `app/models/scraper.py`
- Add an optional `auto_completed: bool = False` flag to `ScraperProgress` so all consumers (WebSocket, UI, logs) know this run was completed via the stagnation watchdog.

### 2. `app/scraper/indeed_scraper.py`
- Add an `auto_complete()` method on `IndeedScraper`:
  - Sets `self._stop_event.set()` to unblock and break the page/country scraping loop.
  - Sets `self._is_auto_completed = True`.
  - Sets `self._progress.status = ScraperStatus.COMPLETED`.
  - Sets `self._progress.current_page = self._progress.max_pages`.
  - Adds a log: `"Auto-completion triggered: Stagnation threshold reached (20 stagnant polls). Finalizing results."`
  - Calls `self._emit_progress(force=True)`.
- In `scrape()` finally / exit handling:
  - If `self._is_auto_completed`, ensure `final_status` is `ScraperStatus.COMPLETED` rather than `ScraperStatus.STOPPED`.

### 3. `app/services/scraper_service.py`
- Add instance variables initialized in `__init__`:
  - `self._stagnation_limit: int = 20`
  - `self._consecutive_stagnant_polls: int = 0`
  - `self._last_polled_leads_count: int = 0`
- Reset these variables in `start()` when a new scraping run begins.
- Add `check_lead_stagnation(current_count: int) -> bool`:
  - If scraper is not running (`not self._is_running()`), return `False`.
  - If `current_count > self._last_polled_leads_count`:
    - Reset `self._consecutive_stagnant_polls = 0`.
    - Update `self._last_polled_leads_count = current_count`.
    - Return `False`.
  - Else:
    - Increment `self._consecutive_stagnant_polls += 1`.
    - Log: `logger.info("Stagnant poll sequence: {}/{} (current leads: {})", self._consecutive_stagnant_polls, self._stagnation_limit, current_count)`.
    - If `self._consecutive_stagnant_polls >= self._stagnation_limit`:
      - Return `True`.
- Add `async def trigger_auto_complete(self) -> None`:
  - Call `self._scraper.auto_complete()` if `self._scraper` exists.
  - Log: `logger.warning("Scraper auto-completed due to {} consecutive stagnant polls. Preserving {} leads.", self._stagnation_limit, len(self._results))`.
- In `_run_pipeline()`:
  - Ensure export and email notification run reliably:
    - If `self._results` contains leads (or if auto-completed):
      - Export workbook via `self._exporter.export(self._results, output_dir=self._settings.output_dir)`.
      - If `self._settings.sharepoint_auto_sync`: sync to SharePoint.
      - If `self._settings.email_notifications_enabled`: call `self.send_email_notification(...)`.
  - Mark session `completed_at` and `total_scraped`.

### 4. `app/dashboard/router.py`
- In `api_get_leads`:
  - After retrieving `leads = service.get_results()`:
  - If `service._is_running()`:
    - If `service.check_lead_stagnation(current_count=len(leads))`:
      - Asynchronously trigger `asyncio.create_task(service.trigger_auto_complete())`.

### 5. `static/js/app.js`
- Verify WebSocket handler updates UI properly:
  - When `p.status === 'completed'`, sets progress bar width to `100%`, sets text to `100%`, updates status to `"Status: Search Completed"`.
  - Re-enables the Search button and disables the Stop button.

---

## Error Handling & Edge Cases
- **No Leads Scraped (0 Leads)**: If 20 stagnant polls occur when 0 leads were found, an empty valid Excel workbook with column headers will be generated, and the email notification will be sent stating that 0 leads were found, ensuring user visibility without silent failure.
- **Race Conditions**: `trigger_auto_complete` checks if the scraper is already stopped or stopping before triggering to avoid duplicate calls.
- **New Leads Arrive at Count 19**: If new leads arrive on poll 19, `consecutive_stagnant_polls` resets to 0 immediately, allowing scraping to continue uninterrupted.

## Testing & Verification Plan
1. Unit/Integration verification of `check_lead_stagnation`:
   - Simulate 19 stagnant polls -> remains running.
   - Add new lead -> resets counter to 0.
   - Simulate 20 stagnant polls -> triggers `auto_complete()`.
2. Verification of completion pipeline:
   - Confirm status becomes `COMPLETED`.
   - Confirm Excel file is generated.
   - Confirm `send_email_notification` is called with the generated Excel path.
