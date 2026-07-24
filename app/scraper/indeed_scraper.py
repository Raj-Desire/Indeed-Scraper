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
from app.parser import get_parser
from app.utils.helpers import get_indeed_search_url, is_job_matching_query
from app.utils.logger import logger


USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    # Chrome on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
]


class IndeedScraper:
    """Playwright-based scraper for user-defined Indeed job searches."""

    def __init__(
        self,
        progress_callback: Optional[Callable[[ScraperProgress], None]] = None,
    ) -> None:
        self._settings = get_settings()
        self._parser = None  # Will be dynamically instantiated per run
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
        # Instantiate parser dynamically based on configuration
        parser_engine = run_config.parser_engine or self._settings.scraper_parser_engine
        self._parser = get_parser(parser_engine)
        self._progress.add_log(f"Using parser engine: {self._parser.__class__.__name__}")
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

                    jobs = await self._scrape_page(browser, context, page, url, country, query)
                    if not jobs:
                        # Retry page once with a fresh recycled context before giving up
                        logger.info("Page {} returned 0 jobs. Recalibrating session with fresh context...", page_num + 1)
                        page, context = await self._recycle_context(browser, context)
                        jobs = await self._scrape_page(browser, context, page, url, country, query)

                    if not jobs:
                        self._progress.add_log(f"No more results found on Page {page_num + 1}")
                        break

                    for job in jobs:
                        # Post-scrape location type filter
                        loc_filter = run_config.location_type.lower()
                        if loc_filter != "all":
                            remote_val = job.remote_type.value if hasattr(job.remote_type, "value") else job.remote_type
                            if loc_filter == "remote" and remote_val != "Fully Remote":
                                                    continue
                            elif loc_filter == "onsite" and remote_val != "On-Site":
                                                    continue
                            elif loc_filter == "hybrid" and remote_val != "Hybrid":
                                                    continue

                        # Strict job role / keyword match filter
                        if run_config.query and run_config.query.strip():
                            if not is_job_matching_query(
                                job_title=job.job_title,
                                company=job.company,
                                location=job.location,
                                description=job.job_description,
                                query=run_config.query,
                            ):
                                continue

                        self._progress.jobs_found += 1
                        self._emit_progress()
                        yield job

                    await self._random_delay()

            finally:
                try:
                    await context.close()
                except Exception:
                    pass
                try:
                    await browser.close()
                except Exception:
                    pass

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
                "--disable-infobars",
            ],
        )

    async def _create_context(self, browser: Browser) -> BrowserContext:
        user_agent = random.choice(USER_AGENTS)
        context = await browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="Asia/Kolkata",
        )
        # Apply anti-detection injections matching navigator properties
        await context.add_init_script("""
            // Webdriver evasion
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            delete Object.getPrototypeOf(navigator).webdriver;

            // Align navigator UserAgent properties
            const ua = navigator.userAgent.replace('HeadlessChrome', 'Chrome');
            Object.defineProperty(navigator, 'userAgent', { get: () => ua });
            Object.defineProperty(navigator, 'appVersion', { get: () => ua.replace('Mozilla/', '') });
            Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });

            // Mock Chrome runtime properties
            window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
            // Mock languages & plugins
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });

            // WebGL Vendor Spoofing
            if (typeof WebGLRenderingContext !== 'undefined') {
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) return 'Google Inc. (NVIDIA)';
                    if (parameter === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)';
                    return getParameter.apply(this, arguments);
                };
            }
        """)
        return context

    async def _recycle_context(self, browser: Browser, old_context: BrowserContext) -> tuple[Page, BrowserContext]:
        try:
            await old_context.close()
        except Exception:
            pass
        new_context = await self._create_context(browser)
        new_page = await new_context.new_page()
        return new_page, new_context

    async def _scrape_page(
        self,
        browser: Browser,
        context: BrowserContext,
        page: Page,
        url: str,
        country: str,
        query: str,
    ) -> list[JobPosting]:
        current_page = page
        current_context = context

        for attempt in range(self._settings.scraper_retry_attempts):
            try:
                await current_page.goto(url, wait_until="domcontentloaded", timeout=30000)

                if await self._is_blocked(current_page):
                    logger.warning("Indeed bot check on attempt {} for URL: {}. Recycling context...", attempt + 1, url)
                    if attempt < self._settings.scraper_retry_attempts - 1:
                        current_page, current_context = await self._recycle_context(browser, current_context)
                        await asyncio.sleep(random.uniform(2.0, 4.0))
                        continue
                    return []

                try:
                    await current_page.wait_for_selector(
                        '[data-jk], .job_seen_beacon, .jobsearch-ResultsList li',
                        timeout=10000
                    )
                except PlaywrightTimeout:
                    if attempt < self._settings.scraper_retry_attempts - 1:
                        current_page, current_context = await self._recycle_context(browser, current_context)
                        await asyncio.sleep(2.0)
                        continue
                    return []

                # Human-like scrolling
                try:
                    await current_page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
                    await asyncio.sleep(random.uniform(0.4, 0.8))
                    await current_page.evaluate("window.scrollTo(0, document.body.scrollHeight / 1.8)")
                    await asyncio.sleep(random.uniform(0.4, 0.8))
                    await current_page.evaluate("window.scrollTo(0, 0)")
                    await asyncio.sleep(random.uniform(0.2, 0.5))
                except Exception:
                    pass

                html = await current_page.content()
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

                return new_jobs

            except Exception as exc:
                logger.error("Error scraping page on attempt {}: {}", attempt + 1, exc)
                if attempt < self._settings.scraper_retry_attempts - 1:
                    current_page, current_context = await self._recycle_context(browser, current_context)
                    await asyncio.sleep(2.0)

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
