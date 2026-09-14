"""
Unit Tests for ScraperService Stop & Restart Lifecycle
Verifies that:
1. Stopping a run allows an immediate new search without 'already in progress' denial.
2. Lingering tasks from a stopped run are cleanly cancelled and reset.
3. Concurrently starting while genuinely running still prevents duplicates.
"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.models.job import JobPosting
from app.models.scraper import RunConfig, ScraperStatus
from app.services.scraper_service import ScraperService


class _SimulatedSlowScraper:
    def __init__(self):
        self.progress = MagicMock()
        self.progress.jobs_found = 0
        self.progress.status = ScraperStatus.RUNNING
        self._stop_event = asyncio.Event()

    def stop(self):
        self._stop_event.set()
        self.progress.status = ScraperStatus.STOPPED

    async def scrape(self, config):
        while not self._stop_event.is_set():
            await asyncio.sleep(0.05)
        self.progress.status = ScraperStatus.STOPPED


@pytest.mark.anyio
async def test_scraper_service_stop_and_immediate_restart(tmp_path):
    """When a run is stopped, starting a new run succeeds immediately without 409 conflict."""
    service = ScraperService()
    service._settings.output_dir = str(tmp_path)
    service._settings.email_notifications_enabled = False
    service._settings.enable_kb_matching = False

    # Start first job
    config1 = RunConfig(query="SharePoint", countries=["US"])
    session_id_1 = await service.start(config1)
    assert session_id_1 is not None
    assert service._current_task is not None
    assert not service._current_task.done()

    # Second start while running must raise RuntimeError
    with pytest.raises(RuntimeError, match="already in progress"):
        await service.start(RunConfig(query="Power Apps", countries=["GB"]))

    # Stop the running scraper
    await service.stop()
    assert service._is_running() is False

    # Immediately start a DIFFERENT job query and country
    config2 = RunConfig(query="Power Apps", countries=["GB"])
    session_id_2 = await service.start(config2)
    assert session_id_2 is not None
    assert session_id_2 != session_id_1
    assert service.get_session().run_config.query == "Power Apps"
    assert service.get_session().run_config.countries == ["GB"]

    # Clean up second task
    await service.stop()
    assert service._is_running() is False


@pytest.mark.anyio
async def test_scraper_service_is_running_flag_when_stopped():
    """_is_running() must return False as soon as scraper is marked stopped, even before task teardown."""
    service = ScraperService()
    sim_scraper = _SimulatedSlowScraper()
    service._scraper = sim_scraper
    
    # Create a dummy task that stays alive
    async def dummy_slow_task():
        while not sim_scraper._stop_event.is_set():
            await asyncio.sleep(0.05)

    service._current_task = asyncio.create_task(dummy_slow_task())
    assert service._is_running() is True

    # Signal stop
    service.stop_signal()
    # Even though task is not done yet, _is_running() must report False
    assert service._is_running() is False

    # Await clean stop
    await service.stop()
    assert service._current_task is None
