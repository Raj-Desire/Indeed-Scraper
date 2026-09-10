# Stagnant Scraper Auto-Complete & Email Dispatch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically stop scraper, mark status 100% COMPLETED, export Excel, and dispatch email report when 20 consecutive stagnant `GET /api/leads` polls occur with no newly discovered leads.

**Architecture:** A lightweight server-side stagnation watchdog inside `ScraperService` monitors `GET /api/leads` poll sequences. If 20 consecutive requests yield no increase in leads, it triggers `auto_complete()` on `IndeedScraper`, halting page loops, marking progress as `COMPLETED` (100%), and executing the full post-scrape pipeline (Excel export, SharePoint sync, and email dispatch).

**Tech Stack:** Python 3.11+, FastAPI, Playwright (Async), asyncio, openpyxl, MSAL / Microsoft Graph Mail API, pytest.

## Global Constraints
- Target threshold: exactly 20 consecutive stagnant `GET /api/leads` polls.
- Counter MUST reset to 0 whenever the lead count increases.
- Progress MUST report status `completed` and `100%` when auto-completed.
- Existing collected leads MUST be preserved without data loss.
- Completion pipeline (Excel exporter and Graph mail notifier) MUST execute on auto-complete.

---

### Task 1: Stagnation State & Auto-Complete in Scraper Models and Engine

**Files:**
- Modify: `app/models/scraper.py:20-45`
- Modify: `app/scraper/indeed_scraper.py:70-100,260-265`
- Test: `tests/test_stagnant_auto_complete.py`

**Interfaces:**
- Produces:
  - `ScraperProgress.is_auto_completed: bool`
  - `IndeedScraper.auto_complete() -> None`

- [ ] **Step 1: Write the failing unit test for `IndeedScraper.auto_complete()`**

```python
# tests/test_stagnant_auto_complete.py
import pytest
from app.models.scraper import ScraperStatus
from app.scraper.indeed_scraper import IndeedScraper

def test_indeed_scraper_auto_complete():
    scraper = IndeedScraper()
    assert scraper.progress.status == ScraperStatus.IDLE
    assert not getattr(scraper.progress, "is_auto_completed", False)

    scraper.auto_complete()
    assert scraper.progress.status == ScraperStatus.COMPLETED
    assert scraper.progress.is_auto_completed is True
    assert scraper._stop_event.is_set()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stagnant_auto_complete.py::test_indeed_scraper_auto_complete -v`
Expected: FAIL (`AttributeError: 'IndeedScraper' object has no attribute 'auto_complete'`)

- [ ] **Step 3: Implement `is_auto_completed` in `ScraperProgress` and `auto_complete()` in `IndeedScraper`**

Update `app/models/scraper.py`:
```python
class ScraperProgress(BaseModel):
    # ...
    is_auto_completed: bool = False
```

Update `app/scraper/indeed_scraper.py`:
```python
    def auto_complete(self) -> None:
        """Gracefully stop scraping due to stagnation, marking as COMPLETED."""
        self._is_auto_completed = True
        self._stop_event.set()
        self._pause_event.set()
        self._progress.is_auto_completed = True
        self._progress.status = ScraperStatus.COMPLETED
        self._progress.current_page = self._progress.max_pages
        self._progress.add_log("Auto-completion triggered: 20 consecutive stagnant polls. Preserving leads.")
        self._emit_progress(force=True)
```
And in `scrape()` final exit logic:
```python
        if getattr(self, "_is_auto_completed", False):
            final_status = ScraperStatus.COMPLETED
        else:
            final_status = ScraperStatus.STOPPED if self._stop_event.is_set() else ScraperStatus.COMPLETED
        self._progress.status = final_status
        self._emit_progress(force=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_stagnant_auto_complete.py::test_indeed_scraper_auto_complete -v`
Expected: PASS

---

### Task 2: Stagnation Watchdog Logic in `ScraperService`

**Files:**
- Modify: `app/services/scraper_service.py:28-65,120-160`
- Test: `tests/test_stagnant_auto_complete.py`

**Interfaces:**
- Produces:
  - `ScraperService.check_lead_stagnation(current_count: int) -> bool`
  - `ScraperService.trigger_auto_complete() -> None`

- [ ] **Step 1: Write failing test for `ScraperService` stagnation counting and reset**

```python
# tests/test_stagnant_auto_complete.py
import pytest
from unittest.mock import MagicMock
from app.services.scraper_service import ScraperService
from app.models.scraper import ScraperStatus

def test_scraper_service_stagnation_counter():
    service = ScraperService()
    # Mock running task
    service._current_task = MagicMock()
    service._current_task.done.return_value = False

    # Initially 0 stagnant polls
    assert service._consecutive_stagnant_polls == 0

    # 19 stagnant polls with 5 leads -> returns False
    for i in range(1, 20):
        triggered = service.check_lead_stagnation(5)
        assert triggered is False
        assert service._consecutive_stagnant_polls == i

    # Lead count increases -> counter resets to 0
    triggered = service.check_lead_stagnation(6)
    assert triggered is False
    assert service._consecutive_stagnant_polls == 0
    assert service._last_polled_leads_count == 6

    # Now 20 stagnant polls -> 20th poll returns True
    for i in range(1, 20):
        assert service.check_lead_stagnation(6) is False
    assert service.check_lead_stagnation(6) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stagnant_auto_complete.py::test_scraper_service_stagnation_counter -v`
Expected: FAIL (`AttributeError: 'ScraperService' object has no attribute 'check_lead_stagnation'`)

- [ ] **Step 3: Implement stagnation methods in `ScraperService`**

In `app/services/scraper_service.py`:
- In `__init__`:
  ```python
  self._stagnation_limit: int = 20
  self._consecutive_stagnant_polls: int = 0
  self._last_polled_leads_count: int = 0
  ```
- In `start()`:
  ```python
  self._consecutive_stagnant_polls = 0
  self._last_polled_leads_count = 0
  ```
- Add:
  ```python
  def check_lead_stagnation(self, current_count: int) -> bool:
      """Check if consecutive GET /api/leads calls have stagnated without new leads."""
      if not self._is_running():
          return False

      if current_count > self._last_polled_leads_count:
          self._consecutive_stagnant_polls = 0
          self._last_polled_leads_count = current_count
          return False

      self._consecutive_stagnant_polls += 1
      logger.info(
          "Stagnant poll sequence: {}/{} (current leads: {})",
          self._consecutive_stagnant_polls,
          self._stagnation_limit,
          current_count,
      )
      return self._consecutive_stagnant_polls >= self._stagnation_limit

  async def trigger_auto_complete(self) -> None:
      """Trigger graceful completion on scraper when stagnation limit is hit."""
      if self._scraper and self._is_running():
          logger.warning(
              "Stagnation limit ({} polls) reached. Triggering scraper auto-completion...",
              self._stagnation_limit,
          )
          self._scraper.auto_complete()
  ```
- In `_run_pipeline()`:
  Ensure `self._exporter.export(...)` and `self.send_email_notification(...)` execute if `self._results` or if run finished/auto-completed, creating an empty workbook if `self._results` is empty so notification is always sent.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_stagnant_auto_complete.py::test_scraper_service_stagnation_counter -v`
Expected: PASS

---

### Task 3: Hook Stagnation Watchdog into `GET /api/leads` and UI Verification

**Files:**
- Modify: `app/dashboard/router.py:86-133`
- Test: `tests/test_stagnant_auto_complete.py`

**Interfaces:**
- Consumes: `ScraperService.check_lead_stagnation`, `ScraperService.trigger_auto_complete`

- [ ] **Step 1: Write integration test for `GET /api/leads` triggering auto-complete**

```python
# tests/test_stagnant_auto_complete.py
from fastapi.testclient import TestClient
from main import app
from app.services.scraper_service import get_scraper_service
from unittest.mock import MagicMock

def test_api_leads_triggers_auto_complete():
    client = TestClient(app)
    service = get_scraper_service()
    service._is_running = MagicMock(return_value=True)
    service._scraper = MagicMock()
    service._stagnation_limit = 3
    service._consecutive_stagnant_polls = 0
    service._last_polled_leads_count = 0

    # Poll 1 & 2
    r1 = client.get("/api/leads")
    assert r1.status_code == 200
    assert service._consecutive_stagnant_polls == 1

    r2 = client.get("/api/leads")
    assert r2.status_code == 200
    assert service._consecutive_stagnant_polls == 2

    # Poll 3 hits stagnation limit (3)
    r3 = client.get("/api/leads")
    assert r3.status_code == 200
    assert service._consecutive_stagnant_polls == 3
    service._scraper.auto_complete.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stagnant_auto_complete.py::test_api_leads_triggers_auto_complete -v`
Expected: FAIL

- [ ] **Step 3: Wire `check_lead_stagnation` in `app/dashboard/router.py`**

In `app/dashboard/router.py` inside `api_get_leads`:
```python
    # Check for stagnation if scraper is running
    if service._is_running():
        if service.check_lead_stagnation(current_count=len(service.get_results())):
            asyncio.create_task(service.trigger_auto_complete())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_stagnant_auto_complete.py -v`
Expected: All tests in `tests/test_stagnant_auto_complete.py` PASS

---

### Task 4: End-to-End Pipeline & Email Notification Verification

**Files:**
- Test: `tests/test_stagnant_auto_complete.py`

- [ ] **Step 1: Write end-to-end pipeline test**

```python
# tests/test_stagnant_auto_complete.py
import pytest
from unittest.mock import AsyncMock, patch
from app.models.scraper import RunConfig, ScraperStatus
from app.services.scraper_service import ScraperService
from app.models.job import JobPosting

@pytest.mark.asyncio
async def test_auto_complete_pipeline_triggers_export_and_email(tmp_path):
    service = ScraperService()
    service._settings.output_dir = str(tmp_path)
    service._settings.email_notifications_enabled = True

    # Pre-populate 2 leads
    lead1 = JobPosting(job_title="Dev 1", company="Co A", job_url="http://a")
    lead2 = JobPosting(job_title="Dev 2", company="Co B", job_url="http://b")
    service._results = [lead1, lead2]

    # Mock send_email_notification
    service.send_email_notification = AsyncMock(return_value=True)

    class FakeScraper:
        def __init__(self):
            self.progress = type("P", (), {"jobs_found": 2, "status": ScraperStatus.RUNNING, "add_log": lambda msg: None})()
            self._stop_event = asyncio.Event()

        async def scrape(self, config):
            # Simulate infinite loop until auto_complete
            while not self._stop_event.is_set():
                await asyncio.sleep(0.01)

        def auto_complete(self):
            self._stop_event.set()
            self.progress.status = ScraperStatus.COMPLETED

    fake = FakeScraper()
    service._scraper = fake

    # Run pipeline task
    pipeline_task = asyncio.create_task(service._run_pipeline(RunConfig()))
    await asyncio.sleep(0.05)

    # Trigger auto complete
    await service.trigger_auto_complete()
    await pipeline_task

    # Verify email was dispatched with excel path
    assert service.send_email_notification.called
    call_args = service.send_email_notification.call_args[1]
    assert "excel_path" in call_args
    assert call_args["excel_path"] is not None
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_stagnant_auto_complete.py -v`
Expected: PASS
