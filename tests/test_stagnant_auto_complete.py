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


def test_scraper_service_stagnation_counter():
    from unittest.mock import MagicMock
    from app.services.scraper_service import ScraperService

    service = ScraperService()
    # Mock running task
    service._current_task = MagicMock()
    service._current_task.done.return_value = False

    # Set initial known leads to 5
    service._last_polled_leads_count = 5
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


def test_api_leads_triggers_auto_complete():
    from fastapi.testclient import TestClient
    from unittest.mock import MagicMock
    from main import app
    from app.services.scraper_service import get_scraper_service

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


def test_auto_complete_pipeline_triggers_export_and_email(tmp_path):
    import asyncio
    from unittest.mock import AsyncMock
    from app.models.job import JobPosting
    from app.models.scraper import RunConfig, ScraperStatus
    from app.services.scraper_service import ScraperService

    async def _run():
        service = ScraperService()
        service._settings.output_dir = str(tmp_path)
        service._settings.email_notifications_enabled = True

        lead1 = JobPosting(job_title="AI Engineer", company="Test Corp", job_url="http://test.com/1")
        service._results = [lead1]

        service.send_email_notification = AsyncMock(return_value=True)

        class FakeScraper:
            def __init__(self):
                self._stop_event = asyncio.Event()
                self._is_auto_completed = False
                self.progress = type("P", (), {
                    "jobs_found": 1,
                    "status": ScraperStatus.RUNNING,
                    "add_log": lambda msg: None,
                })()

            async def scrape(self, config):
                while not self._stop_event.is_set():
                    await asyncio.sleep(0.01)
                    if False:
                        yield None

            def auto_complete(self):
                self._stop_event.set()
                self._is_auto_completed = True
                self.progress.status = ScraperStatus.COMPLETED

        fake = FakeScraper()
        service._scraper = fake

        # Run pipeline in background
        pipeline_task = asyncio.create_task(service._run_pipeline(RunConfig()))
        await asyncio.sleep(0.05)

        # Trigger auto complete
        fake.auto_complete()
        await pipeline_task

        # Verify Excel was exported and email was dispatched
        assert service.send_email_notification.called
        call_kwargs = service.send_email_notification.call_args[1]
        assert "excel_path" in call_kwargs
        assert call_kwargs["excel_path"] is not None
        assert str(tmp_path) in call_kwargs["excel_path"]

    asyncio.run(_run())




