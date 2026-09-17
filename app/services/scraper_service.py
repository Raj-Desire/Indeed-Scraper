"""
Scraper Orchestration Service
==============================
Wires Scraper → Date/Dedup Filter → Excel Export → Web Interface.
Zero AI or Scheduler dependencies.
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from app.config.constants import IST
from app.config.settings import get_settings
from app.excel.exporter import ExcelExporter
from app.filters.date_filter import DateFilter
from app.filters.dedup_filter import DedupFilter
from app.matching.match_service import MatchService
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
        self._last_broadcast_time: float = 0.0

        self._date_filter = DateFilter(max_age_hours=self._settings.filter_max_age_hours)
        self._dedup_filter = DedupFilter()
        self._exporter = ExcelExporter()
        self._match_service: Optional[MatchService] = None
        self._email_sent: bool = False

        logger.info("ScraperService initialized (simple mode)")

    async def start(self, run_config: Optional[RunConfig] = None) -> str:
        """Start scraping run for user-entered parameters."""
        if self._is_running():
            raise RuntimeError("A scraping run is already in progress.")

        # Clean up any lingering stopped/cancelled task before creating a new one
        if self._current_task is not None and not self._current_task.done():
            logger.info("Cleaning up lingering previous task before starting new scrape...")
            self._current_task.cancel()
            try:
                await asyncio.wait_for(self._current_task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass
            self._current_task = None

        config = run_config or RunConfig()
        session_id = str(uuid4())[:8] #generate unique id 

        self._dedup_filter.reset()
        self._results = []
        self._email_sent = False

        session = ScraperSession(
            session_id=session_id,
            run_config=config,
            started_at=datetime.now(tz=IST),
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

    async def stop(self) -> None:
        """Stop scraping and await graceful termination of background task."""
        self.stop_signal()
        if self._current_task and not self._current_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._current_task), timeout=1.2)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                if self._current_task and not self._current_task.done():
                    logger.info("Cancelling lingering scraper task after stop...")
                    self._current_task.cancel()
                    try:
                        await asyncio.wait_for(self._current_task, timeout=1.0)
                    except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                        pass
        self._current_task = None

    def stop_signal(self) -> None:
        """Immediately signal stop to scraper and broadcast progress."""
        if self._scraper:
            self._scraper.stop()
            self._scraper.progress.status = ScraperStatus.STOPPED
            self._scraper.progress.add_log("🛑 Stop requested by user. Terminating active operations...")
            self._broadcast_progress(self._scraper.progress, force=True)

    def get_progress(self) -> ScraperProgress:
        if self._scraper:
            return self._scraper.progress
        return ScraperProgress(status=ScraperStatus.IDLE)

    def get_results(self) -> list[JobPosting]:
        return list(self._results)

    def get_session(self) -> Optional[ScraperSession]:
        return self._current_session

    async def evaluate_manual_job(
        self,
        job_title: str,
        company: str,
        job_description: str,
        location: str = "Remote",
        country: str = "US",
        job_url: str = "",
        salary_range: str = "Not listed",
        experience: str = "Not specified",
        remote_type_str: str = "Remote",
        skip_match: bool = False,
    ) -> JobPosting:
        """
        Manually evaluate a single job description with AI knowledge-base matching
        and store it in results for direct UI display and Excel export.

        Args:
            skip_match: When True, skip this method's own internal KB-match call.
                Set this when the caller has already computed match_score/matched_skills/
                missing_skills/match_reason via a consolidated single LLM call (e.g. the
                manual-evaluate endpoint) and will set those fields on the returned
                JobPosting itself - avoids a second, redundant KB search + LLM call.
        """
        from app.models.job import RemoteType
        
        rem_lower = (remote_type_str or "").lower()
        if "remote" in rem_lower:
            rem_type = RemoteType.FULLY_REMOTE
        elif "hybrid" in rem_lower:
            rem_type = RemoteType.HYBRID
        elif "site" in rem_lower or "onsite" in rem_lower:
            rem_type = RemoteType.ON_SITE
        else:
            rem_type = RemoteType.UNKNOWN

        job = JobPosting(
            job_title=job_title.strip() or "Untitled Role",
            company=company.strip(),
            location=location.strip() or "Remote",
            country=country.strip() or "US",
            job_url=job_url.strip(),
            salary_range=salary_range.strip() or "Not listed",
            experience=experience.strip() or "Not specified",
            job_description=job_description.strip(),
            remote_type=rem_type,
            search_query="Manual Entry",
            posted_date_raw="Just now",
            posted_date=datetime.now(tz=IST),
        )

        if skip_match:
            return self._store_manual_job(job)

        if self._match_service is None and self._settings.enable_kb_matching:
            self._match_service = MatchService()

        if self._match_service is not None:
            try:
                logger.info("Evaluating manual job match for: '{}' at '{}'...", job.job_title, job.company)
                await self._match_service.evaluate_job(job)
                logger.info("Manual job match verdict: Score={}/100 | Skills={}", job.match_score, job.matched_skills)
            except Exception as match_err:
                logger.error("Error evaluating manual job '{}': {}", job.job_title, match_err)

        return self._store_manual_job(job)

    def _store_manual_job(self, job: JobPosting) -> JobPosting:
        """Insert a manually-created job into results and refresh session/progress metadata."""
        # Prepend to results so newly added job appears at top
        self._results.insert(0, job)

        # Ensure session exists so Excel exporter has metadata
        if self._current_session is None:
            self._current_session = ScraperSession(
                session_id=str(uuid4())[:8],
                run_config=RunConfig(
                    countries=[job.country],
                    queries=["Manual Entry"],
                    query="Manual Entry",
                ),
                started_at=datetime.now(tz=IST),
                total_scraped=len(self._results),
            )
        else:
            self._current_session.total_scraped = len(self._results)

        if self._scraper:
            self._scraper.progress.jobs_found = len(self._results)
            self._scraper.progress.add_log(f"Added manual job '{job.job_title}' (Score: {job.match_score or 'N/A'}/100)")
            self._broadcast_progress(self._scraper.progress, force=True)

        return job

    def clear_results(self) -> None:
        """Clear gathered results and reset deduplication filter."""
        self._results.clear()
        self._dedup_filter.reset()
        if self._scraper:
            self._scraper.progress.jobs_found = 0
            self._scraper.progress.add_log("Cleared all job leads from dashboard.")
            self._broadcast_progress(self._scraper.progress, force=True)
        if self._current_session:
            self._current_session.total_scraped = 0
        self._email_sent = False

    def add_progress_callback(self, callback: callable) -> None:
        self._progress_callbacks.append(callback)

    async def _run_pipeline(self, config: RunConfig) -> None:
        """Execute pipeline for a single run."""
        pipeline_error: Optional[str] = None
        try:
            if self._match_service is None and self._settings.enable_kb_matching:
                self._match_service = MatchService()

            async for job in self._scraper.scrape(config):
                filtered = self._date_filter.filter([job])
                if not filtered:
                    continue

                deduped = self._dedup_filter.filter(filtered)
                if not deduped:
                    continue

                if self._match_service is not None:
                    for matched_job in deduped:
                        try:
                            logger.info("Evaluating AI KB match for: '{}' at '{}'...", matched_job.job_title, matched_job.company)
                            await self._match_service.evaluate_job(matched_job)
                            logger.info("AI match verdict for '{}': Score={}/100 | Skills={}", matched_job.job_title, matched_job.match_score, matched_job.matched_skills)
                        except Exception as match_err:
                            logger.error("KB matching error for '{}': {}", matched_job.job_title, match_err)

                self._results.extend(deduped)
                logger.info("Added {} job(s) to live dashboard (Total leads: {})", len(deduped), len(self._results))
                # Sync progress.jobs_found with active unique results count
                self._scraper.progress.jobs_found = len(self._results)
                self._on_progress_update(self._scraper.progress)

        except asyncio.CancelledError:
            logger.info("Pipeline task cancelled by user request.")
            if self._scraper:
                self._scraper.progress.status = ScraperStatus.STOPPED
                self._scraper.progress.add_log("🛑 Scraping stopped.")
                self._broadcast_progress(self._scraper.progress, force=True)
        except Exception as exc:
            logger.error("Pipeline error: {}", exc)
            pipeline_error = str(exc)
            if self._scraper:
                progress = self._scraper.progress
                progress.status = ScraperStatus.ERROR
                progress.last_error = str(exc)
                self._broadcast_progress(progress, force=True)
        else:
            pipeline_error = None
        finally:
            try:
                await asyncio.shield(self._finalize_run(config, error_note=pipeline_error))
            except Exception as fin_err:
                logger.error("Pipeline finalization error: {}", fin_err)

            if self._match_service is not None:
                try:
                    await self._match_service.close()
                except Exception as close_err:
                    logger.error("Error closing match service: {}", close_err)
                finally:
                    self._match_service = None

    async def _finalize_run(self, config: RunConfig, error_note: Optional[str] = None) -> None:
        """
        Guaranteed post-execution finalizer.
        Ensures that whenever leads were gathered (or an error occurred),
        the Excel workbook is exported, SharePoint is synced, and Microsoft Graph email
        is dispatched regardless of whether status was completed, partial, or stopped.
        """
        excel_path: Optional[str] = None
        active_cfg = self._current_session.run_config if self._current_session else config
        if self._results:
            try:
                exported = self._exporter.export(
                    self._results,
                    output_dir=self._settings.output_dir,
                    query=active_cfg.query if active_cfg else "",
                    countries=active_cfg.countries if active_cfg else [],
                    fromage=active_cfg.fromage if active_cfg else "all",
                    location_type=active_cfg.location_type if active_cfg else "all",
                )
                excel_path = str(exported)
                if self._current_session:
                    self._current_session.excel_path = excel_path
                logger.info("Excel exported to: {}", excel_path)
            except Exception as exp_err:
                logger.error("Error during final Excel export: {}", exp_err)

            # Auto-sync to SharePoint if enabled
            if self._settings.sharepoint_auto_sync:
                try:
                    logger.info("Auto-syncing {} scraped jobs to SharePoint List via Microsoft Graph API...", len(self._results))
                    await self.export_sharepoint()
                except Exception as sp_err:
                    logger.error("Auto SharePoint export error: {}", sp_err)

        # Determine run status for notification
        current_scraper_status = getattr(getattr(self._scraper, "progress", None), "status", None)
        if error_note:
            final_status = "partial" if self._results else "error"
        elif current_scraper_status == ScraperStatus.STOPPED:
            final_status = "stopped"
        else:
            final_status = "completed"

        if self._current_session:
            self._current_session.completed_at = datetime.now(tz=IST)
            self._current_session.total_scraped = len(self._results)

        # Background notification dispatch
        if self._settings.email_notifications_enabled:
            # Deliver if we collected leads OR if an error occurred (alert)
            if self._results or error_note:
                try:
                    active_cfg = self._current_session.run_config if self._current_session else config
                    cfg_queries = getattr(active_cfg, "queries", None) or getattr(config, "queries", None)
                    cfg_query = getattr(active_cfg, "query", "") or getattr(config, "query", "")
                    logger.info(
                        "Dispatching Graph email notification (Status: '{}', Leads: {})...",
                        final_status, len(self._results)
                    )
                    sent = await self.send_email_notification(
                        excel_path=excel_path,
                        query=cfg_query,
                        queries=cfg_queries,
                        countries=active_cfg.countries if active_cfg else config.countries,
                        fromage=active_cfg.fromage if active_cfg else config.fromage,
                        location_type=active_cfg.location_type if active_cfg else config.location_type,
                        status=final_status,
                        error_note=error_note,
                    )
                    if sent:
                        self._email_sent = True
                except Exception as mail_err:
                    logger.error("Notification dispatch failed: {}", mail_err)

    async def export_sharepoint(self, selected_ids: Optional[list[str]] = None, owner: Optional[str] = None) -> int:
        """Export current session results to SharePoint List via Graph API."""
        from app.sharepoint.graph_exporter import GraphSharePointExporter
        sp_exporter = GraphSharePointExporter()
        leads_to_export = self._results
        if selected_ids is not None:
            id_set = {str(i) for i in selected_ids}
            leads_to_export = [j for j in self._results if str(j.id) in id_set]
        return await sp_exporter.export_jobs(leads_to_export, owner=owner)

    async def send_email_notification(
        self,
        excel_path: Optional[str] = None,
        query: str = "",
        queries: Optional[list[str]] = None,
        countries: Optional[list[str]] = None,
        fromage: str = "1",
        location_type: str = "remote",
        status: str = "completed",
        error_note: Optional[str] = None,
    ) -> bool:
        """Send daily email report with Excel attachment via Microsoft Graph API."""
        from app.notifications.graph_mail import GraphMailNotifier
        notifier = GraphMailNotifier()
        sent = await notifier.send_report(
            jobs=self._results,
            excel_path=excel_path,
            query=query,
            queries=queries,
            countries=countries,
            fromage=fromage,
            location_type=location_type,
            status=status,
            error_note=error_note,
        )
        if sent:
            self._email_sent = True
        return sent

    def is_email_sent(self) -> bool:
        """Return whether an email has already been dispatched for the current session."""
        return self._email_sent

    def mark_email_sent(self, sent: bool = True) -> None:
        """Set the email sent status."""
        self._email_sent = sent

    def _is_running(self) -> bool:
        if self._current_task is None or self._current_task.done():
            return False
        # If scraper was marked stopped or stopping, it is NOT actively running
        if self._scraper and (
            self._scraper._stop_event.is_set()
            or getattr(self._scraper.progress, "status", None) in (ScraperStatus.STOPPED, ScraperStatus.STOPPING)
        ):
            return False
        return True

    def _on_progress_update(self, progress: ScraperProgress) -> None:
        self._broadcast_progress(progress)

    def _broadcast_progress(self, progress: ScraperProgress, force: bool = False) -> None:
        """Throttle progress updates to maximum 2/sec when running, unless status changed."""
        now = time.monotonic()
        status = getattr(progress, "status", None)
        if not force and status == ScraperStatus.RUNNING and (now - self._last_broadcast_time < 0.5):
            return

        self._last_broadcast_time = now
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
