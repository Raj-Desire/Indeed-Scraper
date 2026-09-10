"""
Unit Tests for ScraperService Finalizer & Guaranteed Email Notification
Verifies that Excel is exported and email notification is sent on partial results,
bot blocks, early stops, and clean completions.
"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.models.job import JobPosting, RemoteType
from app.models.scraper import RunConfig, ScraperStatus
from app.services.scraper_service import ScraperService


class _SimulatedScraper:
    def __init__(self, jobs, fail_after_index=None):
        self._jobs = jobs
        self._fail_after = fail_after_index
        self.progress = MagicMock()
        self.progress.jobs_found = 0
        self.progress.status = ScraperStatus.RUNNING
        self.progress.last_error = ""

    async def scrape(self, config):
        if self._fail_after == 0:
            self.progress.status = ScraperStatus.ERROR
            raise RuntimeError("Indeed bot check triggered or network timeout")
        for idx, job in enumerate(self._jobs):
            if self._fail_after is not None and idx >= self._fail_after:
                self.progress.status = ScraperStatus.ERROR
                raise RuntimeError("Indeed bot check triggered or network timeout")
            yield job
        if self._fail_after is not None and len(self._jobs) >= self._fail_after:
            self.progress.status = ScraperStatus.ERROR
            raise RuntimeError("Indeed bot check triggered or network timeout")
        self.progress.status = ScraperStatus.COMPLETED


def test_finalize_exports_and_notifies_on_partial_failure(tmp_path):
    """When a bot check or error aborts scraping after finding jobs, results must be saved and emailed."""
    service = ScraperService()
    service._settings.output_dir = str(tmp_path)
    service._settings.email_notifications_enabled = True
    service._settings.enable_kb_matching = False  # Avoid slow external LLM calls during test

    job1 = JobPosting(
        job_title="Lead 1",
        company="Co 1",
        job_description="Desc 1",
        posted_date=datetime.now(tz=timezone.utc),
    )
    job2 = JobPosting(
        job_title="Lead 2",
        company="Co 2",
        job_description="Desc 2",
        posted_date=datetime.now(tz=timezone.utc),
    )

    # Scrapes 2 jobs, then fails immediately after
    service._scraper = _SimulatedScraper([job1, job2], fail_after_index=2)
    service._date_filter.filter = lambda j: j
    service._dedup_filter.filter = lambda j: j

    # Mock send_email_notification
    service.send_email_notification = AsyncMock(return_value=True)

    config = RunConfig(query="Python Engineer", countries=["US"])
    asyncio.run(service._run_pipeline(config))

    # Assert leads were preserved
    assert len(service._results) == 2
    assert service._results[0].job_title == "Lead 1"
    assert service._results[1].job_title == "Lead 2"

    # Assert notification was dispatched with 'partial' status
    assert service.send_email_notification.called
    call_kwargs = service.send_email_notification.call_args.kwargs
    assert call_kwargs["status"] == "partial"
    assert "Indeed bot check" in call_kwargs["error_note"]
    assert call_kwargs["excel_path"] is not None


def test_finalize_notifies_alert_on_zero_leads_error():
    """When an error happens before any jobs are found, an alert notification is sent."""
    service = ScraperService()
    service._settings.email_notifications_enabled = True
    service._settings.enable_kb_matching = False

    # Fails immediately
    service._scraper = _SimulatedScraper([], fail_after_index=0)
    service._date_filter.filter = lambda j: j
    service._dedup_filter.filter = lambda j: j

    service.send_email_notification = AsyncMock(return_value=True)

    config = RunConfig(query="Python Engineer", countries=["US"])
    asyncio.run(service._run_pipeline(config))

    assert len(service._results) == 0
    assert service.send_email_notification.called
    call_kwargs = service.send_email_notification.call_args.kwargs
    assert call_kwargs["status"] == "error"
    assert "Indeed bot check" in call_kwargs["error_note"]


def test_finalize_notifies_completed_on_clean_run(tmp_path):
    """When scraping completes without errors, status is 'completed'."""
    service = ScraperService()
    service._settings.output_dir = str(tmp_path)
    service._settings.email_notifications_enabled = True
    service._settings.enable_kb_matching = False

    job1 = JobPosting(
        job_title="Lead 1",
        company="Co 1",
        job_description="Desc 1",
        posted_date=datetime.now(tz=timezone.utc),
    )

    service._scraper = _SimulatedScraper([job1], fail_after_index=None)
    service._date_filter.filter = lambda j: j
    service._dedup_filter.filter = lambda j: j

    service.send_email_notification = AsyncMock(return_value=True)

    config = RunConfig(query="Python Engineer", countries=["US"])
    asyncio.run(service._run_pipeline(config))

    assert len(service._results) == 1
    assert service.send_email_notification.called
    call_kwargs = service.send_email_notification.call_args.kwargs
    assert call_kwargs["status"] == "completed"
    assert call_kwargs["error_note"] is None
