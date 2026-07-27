"""
Scraper Orchestration Service
==============================
Wires Scraper → Date/Dedup Filter → Excel Export → Web Interface.
Zero AI or Scheduler dependencies.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from app.config.settings import get_settings
from app.excel.exporter import ExcelExporter
from app.filters.date_filter import DateFilter
from app.filters.dedup_filter import DedupFilter
from app.models.job import JobPosting
from app.models.scraper import RunConfig, ScraperProgress, ScraperSession, ScraperStatus
from app.scraper.indeed_scraper import IndeedScraper
from app.utils.logger import logger


class ScraperService:
    """Orchestrates job scraping, deduplication, and export."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._scraper: Optional[IndeedScraper] = None
        self._current_task: Optional[asyncio.Task] = None
        self._results: list[JobPosting] = []
        self._current_session: Optional[ScraperSession] = None
        self._progress_callbacks: list[callable] = []

        self._date_filter = DateFilter(max_age_hours=self._settings.filter_max_age_hours)
        self._dedup_filter = DedupFilter()
        self._exporter = ExcelExporter()

        logger.info("ScraperService initialized (simple mode)")

    async def start(self, run_config: Optional[RunConfig] = None) -> str:
        """Start scraping run for user-entered parameters."""
        if self._is_running():
            raise RuntimeError("A scraping run is already in progress.")

        config = run_config or RunConfig()
        session_id = str(uuid4())[:8] #generate unique id 

        self._dedup_filter.reset()
        self._results = []

        session = ScraperSession(
            session_id=session_id,
            run_config=config,
            started_at=datetime.now(tz=timezone.utc),
        )
        self._current_session = session

        self._scraper = IndeedScraper(progress_callback=self._on_progress_update)
        self._current_task = asyncio.create_task(
            self._run_pipeline(config),
            name=f"scraper-{session_id}",
        )

        logger.info("Scraper started: country='{}', query='{}', pages={}", config.country, config.query, config.max_pages)
        return session_id

    def pause(self) -> None:
        if self._scraper:
            self._scraper.pause()

    def resume(self) -> None:
        if self._scraper:
            self._scraper.resume()

    def stop(self) -> None:
        if self._scraper:
            self._scraper.stop()

    def get_progress(self) -> ScraperProgress:
        if self._scraper:
            self._scraper.progress.jobs_found = len(self._results)
            return self._scraper.progress
        return ScraperProgress(status=ScraperStatus.IDLE)

    def get_results(self) -> list[JobPosting]:
        return list(self._results)

    def get_session(self) -> Optional[ScraperSession]:
        return self._current_session

    def add_progress_callback(self, callback: callable) -> None:
        self._progress_callbacks.append(callback)

    async def _run_pipeline(self, config: RunConfig) -> None:
        """Execute pipeline for a single run."""
        try:
            async for job in self._scraper.scrape(config):
                filtered = self._date_filter.filter([job])
                if not filtered:
                    self._on_progress_update(self._scraper.progress)
                    continue

                deduped = self._dedup_filter.filter(filtered)
                if not deduped:
                    self._on_progress_update(self._scraper.progress)
                    continue

                self._results.extend(deduped)
                self._on_progress_update(self._scraper.progress)

            # Ensure final progress.jobs_found is strictly in sync with len(self._results)
            if self._scraper:
                self._on_progress_update(self._scraper.progress)

            if self._results:
                excel_path = self._exporter.export(
                    self._results,
                    output_dir=self._settings.output_dir,
                )
                if self._current_session:
                    self._current_session.excel_path = str(excel_path)
                logger.info("Excel exported to: {}", excel_path)

                # Auto-sync to SharePoint if enabled
                if self._settings.sharepoint_auto_sync:
                    try:
                        logger.info("Auto-syncing scraped jobs to SharePoint List via Microsoft Graph API...")
                        await self.export_sharepoint()
                    except Exception as sp_err:
                        logger.error("Auto SharePoint export error: {}", sp_err)

            if self._current_session:
                self._current_session.completed_at = datetime.now(tz=timezone.utc)
                self._current_session.total_scraped = len(self._results)

        except Exception as exc:
            logger.error("Pipeline error: {}", exc)
            if self._scraper:
                progress = self._scraper.progress
                progress.status = ScraperStatus.ERROR
                progress.last_error = str(exc)
                self._broadcast_progress(progress)

    async def export_sharepoint(self) -> int:
        """Export current session results to SharePoint List via Graph API."""
        from app.sharepoint.graph_exporter import GraphSharePointExporter
        sp_exporter = GraphSharePointExporter()
        return await sp_exporter.export_jobs(self._results)

    def _is_running(self) -> bool:
        return self._current_task is not None and not self._current_task.done()

    def _on_progress_update(self, progress: ScraperProgress) -> None:
        progress.jobs_found = len(self._results)
        self._broadcast_progress(progress)

    def _broadcast_progress(self, progress: ScraperProgress) -> None:
        for callback in self._progress_callbacks:
            try:
                callback(progress)
            except Exception:
                pass


_scraper_service: Optional[ScraperService] = None


def get_scraper_service() -> ScraperService:
    global _scraper_service
    if _scraper_service is None:
        _scraper_service = ScraperService()
    return _scraper_service
