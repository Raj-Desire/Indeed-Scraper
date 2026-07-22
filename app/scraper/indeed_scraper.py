"""
Indeed Job Scraper — Playwright Implementation
================================================
Scrapes Indeed search pages for user-entered country, job role/keyword, and max pages.
"""

import asyncio
import random
from collections.abc import Callable, AsyncIterator
from datetime import datetime, timezone
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeout,
)

from app.config.settings import get_settings
from app.models.job import JobPosting
from app.models.scraper import ScraperProgress, ScraperStatus, RunConfig
from app.parser.job_parser import JobParser
from app.utils.helpers import get_indeed_search_url
from app.utils.logger import logger


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


class IndeedScraper:
    """Playwright-based scraper for user-defined Indeed job searches."""

    def __init__(
        self,
        progress_callback: Optional[Callable[[ScraperProgress], None]] = None,
    ) -> None:
        self._settings = get_settings()
        self._parser = JobParser()
        self._progress_callback = progress_callback
        self._progress = ScraperProgress()
        self._seen_job_ids: set[str] = set()

        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._stop_event = asyncio.Event()

    def pause(self) -> None:
        """Pause scraping."""
        self._pause_event.clear()
        self._progress.status = ScraperStatus.PAUSED
        self._emit_progress()

    def resume(self) -> None:
        """Resume scraping."""
        self._pause_event.set()
        self._progress.status = ScraperStatus.RUNNING
        self._emit_progress()

    def stop(self) -> None:
        """Stop scraping."""
        self._stop_event.set()
        self._pause_event.set()
        self._progress.status = ScraperStatus.STOPPING
        self._emit_progress()

    @property
    def progress(self) -> ScraperProgress:
        return self._progress

    async def scrape(self, run_config: RunConfig) -> AsyncIterator[JobPosting]:
        """
        Scrapes job postings for the given RunConfig (country, query, max_pages).
        """
        self._stop_event.clear()
        self._seen_job_ids.clear()

        country = run_config.country or "US"
        query = run_config.query or "AI Developer"
        max_pages = run_config.max_pages or 3

        self._progress = ScraperProgress(
            status=ScraperStatus.RUNNING,
            current_country=country,
            current_keyword=query,
            max_pages=max_pages,
            started_at=datetime.now(tz=timezone.utc),
        )
        self._emit_progress()

        location_param = "remote" if run_config.location_type.lower() == "remote" else ""

        async with async_playwright() as pw:
            browser = await self._launch_browser(pw, run_config.headless)
            context = await self._create_context(browser)
            page = await context.new_page()

            try:
                for page_num in range(max_pages):
                    if self._stop_event.is_set():
                        break

                    await self._pause_event.wait()

                    url = get_indeed_search_url(
                        country_input=country,
                        query=query,
                        location=location_param,
                        page=page_num,
                    )

                    self._progress.current_page = page_num + 1
                    self._progress.add_log(f"Fetching Page {page_num + 1}: {query} ({country})")
                    self._emit_progress()

                    jobs = await self._scrape_page(page, url, country, query)
                    if not jobs:
                        self._progress.add_log(f"No more results on Page {page_num + 1}")
                        break

                    for job in jobs:
                        # Post-scrape location type filter
                        loc_filter = run_config.location_type.lower()
                        if loc_filter != "all":
                            if loc_filter == "remote" and job.remote_type.value != "Fully Remote":
                                continue
                            elif loc_filter == "onsite" and job.remote_type.value != "On-Site":
                                continue
                            elif loc_filter == "hybrid" and job.remote_type.value != "Hybrid":
                                continue
                        yield job

                    await self._random_delay()

            finally:
                await context.close()
                await browser.close()

        final_status = ScraperStatus.STOPPED if self._stop_event.is_set() else ScraperStatus.COMPLETED
        self._progress.status = final_status
        self._emit_progress()

    async def _launch_browser(self, pw, headless_override: Optional[bool]) -> Browser:
        headless = self._settings.scraper_headless if headless_override is None else headless_override
        return await pw.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )

    async def _create_context(self, browser: Browser) -> BrowserContext:
        user_agent = random.choice(USER_AGENTS)
        context = await browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        return context

    async def _scrape_page(
        self,
        page: Page,
        url: str,
        country: str,
        query: str,
    ) -> list[JobPosting]:
        for attempt in range(self._settings.scraper_retry_attempts):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)

                if await self._is_blocked(page):
                    logger.warning("Indeed bot check on attempt {} for URL: {}", attempt + 1, url)
                    if attempt < self._settings.scraper_retry_attempts - 1:
                        await asyncio.sleep(3.0)
                        continue
                    return []

                try:
                    await page.wait_for_selector(
                        '[data-jk], .job_seen_beacon, .jobsearch-ResultsList li',
                        timeout=10000
                    )
                except PlaywrightTimeout:
                    return []

                html = await page.content()
                jobs = self._parser.parse_search_results(
                    html=html,
                    country=country,
                    search_query=query,
                )

                new_jobs = []
                for job in jobs:
                    if not job.indeed_job_id or job.indeed_job_id not in self._seen_job_ids:
                        if job.indeed_job_id:
                            self._seen_job_ids.add(job.indeed_job_id)
                        new_jobs.append(job)
                        self._progress.jobs_found += 1

                self._emit_progress()
                return new_jobs

            except Exception as exc:
                logger.error("Error scraping page: {}", exc)
                if attempt < self._settings.scraper_retry_attempts - 1:
                    await asyncio.sleep(3.0)

        return []

    async def _is_blocked(self, page: Page) -> bool:
        try:
            title = (await page.title()).lower()
            title_blocks = ["just a moment", "attention required", "access denied", "security check", "verify you are human"]
            if any(signal in title for signal in title_blocks):
                return True
            challenge = await page.query_selector("#challenge-stage, #cf-please-wait, .g-recaptcha, iframe[src*='recaptcha']")
            if challenge:
                return True
            return False
        except Exception:
            return False

    async def _random_delay(self) -> None:
        delay = random.uniform(self._settings.scraper_delay_min, self._settings.scraper_delay_max)
        await asyncio.sleep(delay)

    def _emit_progress(self) -> None:
        if self._progress_callback:
            try:
                self._progress_callback(self._progress)
            except Exception:
                pass
