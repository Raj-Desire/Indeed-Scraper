"""
Indeed Job Scraper — Playwright Implementation
================================================
Scrapes Indeed search pages for user-entered country, job role/keyword, and max pages.
"""

import asyncio
import json
from pathlib import Path
import random
import time
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

from app.config.browser_profiles import get_browser_profile
from app.config.constants import (
    resolve_country_timezone,
    resolve_country_locale,
    resolve_country_domain,
    IST,
)
from app.config.settings import get_settings
from app.models.job import JobPosting
from app.models.scraper import ScraperProgress, ScraperStatus, RunConfig
from app.parser import get_parser
from app.scraper.selector_health import selector_health
from app.utils.helpers import get_indeed_search_url, is_job_matching_query
from app.utils.logger import logger


# Curated realistic viewports with market-share distribution weights
VIEWPORT_POOL = [
    {"width": 1366, "height": 768},   # Common laptop (22%)
    {"width": 1920, "height": 1080},  # Desktop FHD (18%)
    {"width": 1440, "height": 900},   # MacBook (12%)
    {"width": 1280, "height": 800},   # Older MacBook / small laptop (8%)
    {"width": 1536, "height": 864},   # Surface Laptop / high-DPI Windows (7%)
    {"width": 1600, "height": 900},   # Dell / HP laptop (6%)
]
VIEWPORT_WEIGHTS = [22, 18, 12, 8, 7, 6]

# Modern browser User-Agents (Chrome 135+, Firefox 130+, Edge 135+)
USER_AGENTS = [
    # Chrome on Windows (x64) - matched to Chrome 133-136
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0",
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
        self._last_emit_time: float = 0.0
        self._consecutive_blocks: int = 0
        self._max_consecutive_blocks: int = 3

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
        Scrapes job postings for the given RunConfig (countries, query, max_pages).
        """
        self._stop_event.clear()

        countries = run_config.countries or ["US"]
        query = run_config.query or "AI Developer"
        max_pages_per_country = run_config.max_pages or 3
        total_pages_overall = max_pages_per_country * len(countries)
        # Resolve once for the entire run — both are constant per run_config
        fromage_param = run_config.fromage or "all"
        location_param = "remote" if run_config.location_type.lower() == "remote" else ""

        self._progress = ScraperProgress(
            status=ScraperStatus.RUNNING,
            current_country=countries[0],
            current_keyword=query,
            max_pages=total_pages_overall,
            started_at=datetime.now(tz=IST),
        )
        # Instantiate parser dynamically based on configuration
        parser_engine = run_config.parser_engine or self._settings.scraper_parser_engine
        self._parser = get_parser(parser_engine)
        self._progress.add_log(f"Using parser engine: {self._parser.__class__.__name__}")
        self._progress.add_log(f"Targeting {len(countries)} countries: {', '.join(countries)}")
        self._emit_progress()

        async with async_playwright() as pw:
            browser = await self._launch_browser(pw, run_config.headless)

            try:
                processed_pages_count = 0
                for c_idx, country in enumerate(countries):
                    if self._stop_event.is_set():
                        break

                    # Reset consecutive blocks counter for each country independently
                    self._consecutive_blocks = 0
                    self._progress.current_country = country
                    self._progress.add_log(f"🌍 Country {c_idx+1}/{len(countries)}: Starting {country}...")
                    self._emit_progress(force=True)

                    # Phase 5.1: Select proxy if rotation is enabled
                    proxy_url = None
                    if self._settings.proxy_rotation and self._settings.proxy_list:
                        proxy_url = self._settings.proxy_list[c_idx % len(self._settings.proxy_list)]
                        proxy_display = proxy_url.split("@")[-1] if "@" in proxy_url else proxy_url
                        self._progress.add_log(f"Using rotating proxy for {country}: {proxy_display}")

                    # Context and page are owned exclusively by the outer loop.
                    # Session state is restored from sessions/ if valid (<6 hours)
                    # Phase 5.4: Dynamic browser profile applied per country
                    country_context = await self._create_context(browser, country, proxy_url=proxy_url)
                    country_page = await country_context.new_page()

                    try:
                        for page_num in range(max_pages_per_country):
                            if self._stop_event.is_set():
                                break

                            await self._pause_event.wait()

                            url = get_indeed_search_url(
                                country_input=country,
                                query=query,
                                location=location_param,
                                page=page_num,
                                fromage=fromage_param,
                            )

                            processed_pages_count += 1
                            self._progress.current_page = processed_pages_count
                            log_msg = f"Fetching Page {page_num + 1}/{max_pages_per_country} ({country}): {query}"
                            logger.info("{} | Target URL: {}", log_msg, url)
                            self._progress.add_log(log_msg)
                            self._emit_progress()

                            jobs = await self._scrape_page(
                                country_context, country_page, url, country, query
                            )

                            if not jobs:
                                is_blocked = self._consecutive_blocks > 0
                                if is_blocked:
                                    # 60-second cooldown break to let Indeed anti-bot trust score recover
                                    cooldown_secs = 60
                                    logger.warning(
                                        "Indeed verification detected for {} on Page {}. Pausing for {}s cooldown before retrying...",
                                        country, page_num + 1, cooldown_secs
                                    )
                                    self._progress.add_log(
                                        f"⚠️ Bot verification on {country}. Pausing {cooldown_secs}s cooldown to reset trust..."
                                    )
                                    self._emit_progress(force=True)

                                    for remaining in range(cooldown_secs, 0, -15):
                                        if self._stop_event.is_set():
                                            break
                                        await asyncio.sleep(min(15.0, remaining))
                                        if remaining > 15 and not self._stop_event.is_set():
                                            self._progress.add_log(
                                                f"Cooldown active for {country}: retrying in {remaining - 15}s..."
                                            )
                                            self._emit_progress(force=True)

                                    if not self._stop_event.is_set():
                                        self._progress.add_log(
                                            f"🔄 Cooldown complete. Retrying {country} with fresh session..."
                                        )
                                        self._emit_progress(force=True)
                                        country_page, country_context = await self._recycle_context(
                                            browser, country_context, country, proxy_url=proxy_url
                                        )
                                        self._consecutive_blocks = 0
                                        jobs = await self._scrape_page(
                                            country_context, country_page, url, country, query
                                        )
                                        if jobs:
                                            self._progress.add_log(
                                                f"✅ Cooldown retry succeeded! Captured {len(jobs)} jobs for {country}."
                                            )
                                            self._emit_progress(force=True)
                                else:
                                    # Zero results on clean search: recycle context once and retry
                                    logger.info(
                                        "Page {} ({}) returned 0 jobs. Recalibrating session with fresh context...",
                                        page_num + 1, country,
                                    )
                                    country_page, country_context = await self._recycle_context(
                                        browser, country_context, country, proxy_url=proxy_url
                                    )
                                    jobs = await self._scrape_page(
                                        country_context, country_page, url, country, query
                                    )

                            if not jobs:
                                if self._consecutive_blocks > 0:
                                    self._progress.add_log(
                                        f"⚠️ {country} still restricted after cooldown. Preserving {self._progress.jobs_found} leads; transitioning to next country..."
                                    )
                                else:
                                    self._progress.add_log(f"No more results found for {country} on Page {page_num + 1}")

                                # Advance progress counter to the end of this country so progress bar doesn't stall
                                processed_pages_count = (c_idx + 1) * max_pages_per_country
                                self._progress.current_page = processed_pages_count
                                self._emit_progress(force=True)
                                await self._adaptive_delay(status="zero_results", page_num=page_num)
                                break

                            # Phase 3.3: Save successful session state for country
                            await self._save_session_state(country_context, country)

                            matched_jobs_count = 0
                            for job in jobs:
                                # Post-scrape location type filter
                                loc_filter = run_config.location_type.lower()
                                if loc_filter != "all":
                                    remote_val = job.remote_type.value if hasattr(job.remote_type, "value") else str(job.remote_type)
                                    if loc_filter == "remote" and remote_val != "Fully Remote":
                                        desc_lower = f"{job.job_title} {job.location} {job.job_description or ''}".lower()
                                        if any(term in desc_lower for term in ["remote", "work from home", "wfh", "telecommute"]):
                                            pass
                                        else:
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

                                matched_jobs_count += 1
                                logger.info("Job passed query filter: '{}' at '{}' ({})", job.job_title, job.company, job.location)
                                self._progress.jobs_found += 1
                                self._emit_progress()
                                yield job

                            if matched_jobs_count == 0 and len(jobs) > 0:
                                log_note = f"Parsed {len(jobs)} raw jobs for {country} (Page {page_num + 1}), but none matched location/query filters."
                                logger.info(log_note)
                                self._progress.add_log(log_note)
                                self._emit_progress(force=True)
                            elif matched_jobs_count > 0:
                                log_note = f"✅ Captured {matched_jobs_count} matching leads for {country} (Page {page_num + 1}). Total leads: {self._progress.jobs_found}"
                                self._progress.add_log(log_note)
                                self._emit_progress(force=True)

                            # Phase 3.5: Adaptive inter-page delay based on page index and result count
                            await self._adaptive_delay(status="success", page_num=page_num, jobs_count=len(jobs))

                    finally:
                        try:
                            # Save cookies before closing context
                            await self._save_session_state(country_context, country)
                            await country_context.close()
                        except Exception:
                            pass

                    # Step-by-step country transition feedback
                    next_c_idx = c_idx + 1
                    if next_c_idx < len(countries):
                        next_country = countries[next_c_idx]
                        self._progress.add_log(
                            f"🏁 Finished {country} (leads so far: {self._progress.jobs_found}). Step by step moving to next country: {next_country}..."
                        )
                        self._emit_progress(force=True)
                    else:
                        self._progress.add_log(
                            f"🏁 Finished {country} (leads so far: {self._progress.jobs_found}). All selected countries completed!"
                        )
                        self._emit_progress(force=True)

            finally:
                try:
                    await browser.close()
                except Exception:
                    pass
                # Phase 5.2: Generate selector health diagnostics report
                try:
                    health_report = selector_health.report()
                    if health_report:
                        self._progress.add_log(f"Selector Health: {len(health_report)} selectors evaluated")
                except Exception as h_err:
                    logger.debug("Selector health report error: {}", h_err)

        final_status = ScraperStatus.STOPPED if self._stop_event.is_set() else ScraperStatus.COMPLETED
        self._progress.status = final_status
        self._emit_progress()

    async def _launch_browser(self, pw, headless_override: Optional[bool]) -> Browser:
        headless = self._settings.scraper_headless if headless_override is None else headless_override
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-infobars",
        ]
        # Prefer installed Google Chrome channel to pass Cloudflare / Turnstile bot checks cleanly
        try:
            browser = await pw.chromium.launch(
                channel="chrome",
                headless=headless,
                args=launch_args,
            )
            logger.info("Launched browser using installed Google Chrome channel (headless={})", headless)
            return browser
        except Exception as e:
            logger.warning("Could not launch Chrome channel ({}); falling back to bundled Chromium", e)
            return await pw.chromium.launch(
                headless=headless,
                args=launch_args,
            )

    async def _create_context(
        self,
        browser: Browser,
        country: str = "US",
        proxy_url: Optional[str] = None,
    ) -> BrowserContext:
        """
        Create a new browser context with a hardened fingerprint matching target country & platform:
        - Weighted randomized viewport selection
        - Phase 5.4: Country-specific browser profile (locale, timezone, Accept-Language)
        - Screen and window dimensions matched to chosen viewport
        - Realistic Chrome Plugin objects
        - Subtle canvas noise injection (1-bit perturbation)
        - Webdriver & WebGL vendor evasion
        - Phase 5.1: Per-context rotating proxy support
        - Session cookie & state restoration from sessions/ (if < 6 hours old)
        """
        profile = get_browser_profile(country)
        user_agent = random.choice(USER_AGENTS)
        timezone_id = profile["timezone_id"]
        locale = profile["locale"]
        accept_language = profile["accept_language"]
        viewport = random.choices(VIEWPORT_POOL, weights=VIEWPORT_WEIGHTS, k=1)[0]
        vp_width = viewport["width"]
        vp_height = viewport["height"]

        # Infer OS platform from UA string for navigator consistency
        if "Macintosh" in user_agent:
            platform_str = "MacIntel"
        elif "Windows" in user_agent:
            platform_str = "Win32"
        else:
            platform_str = "Linux x86_64"

        # Check for persistent session storage state (valid within 6 hours)
        storage_state = None
        session_file = Path("sessions") / f"{country.upper()}_session.json"
        if session_file.exists():
            try:
                age_seconds = time.time() - session_file.stat().st_mtime
                if age_seconds < 21600:  # 6 hours
                    storage_state = str(session_file)
                    logger.info("Restoring saved session state for {} (age: {:.1f}m)", country, age_seconds / 60)
                else:
                    logger.debug("Session state for {} expired ({:.1f}h old), using clean session", country, age_seconds / 3600)
            except Exception as e:
                logger.debug("Error checking session file: {}", e)

        context_kwargs = {
            "user_agent": user_agent,
            "viewport": viewport,
            "locale": locale,
            "timezone_id": timezone_id,
            "extra_http_headers": {
                "Accept-Language": accept_language,
            },
        }
        if storage_state:
            context_kwargs["storage_state"] = storage_state

        # Phase 5.1: Configure proxy if provided
        if proxy_url:
            from urllib.parse import urlparse
            try:
                parsed = urlparse(proxy_url)
                if parsed.hostname:
                    server_str = f"{parsed.scheme or 'http'}://{parsed.hostname}"
                    if parsed.port:
                        server_str += f":{parsed.port}"
                    proxy_dict = {"server": server_str}
                    if parsed.username:
                        proxy_dict["username"] = parsed.username
                    if parsed.password:
                        proxy_dict["password"] = parsed.password
                    context_kwargs["proxy"] = proxy_dict
                else:
                    context_kwargs["proxy"] = {"server": proxy_url}
                logger.info("Configured proxy for context ({}): {}", country, context_kwargs["proxy"].get("server"))
            except Exception as p_err:
                logger.warning("Failed to parse proxy URL '{}': {}", proxy_url, p_err)

        context = await browser.new_context(**context_kwargs)

        init_script = f"""
            // 1. Webdriver evasion
            Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});
            delete Object.getPrototypeOf(navigator).webdriver;

            // 2. Align navigator properties
            const rawUa = navigator.userAgent.replace('HeadlessChrome', 'Chrome');
            Object.defineProperty(navigator, 'userAgent', {{ get: () => rawUa }});
            Object.defineProperty(navigator, 'appVersion', {{ get: () => rawUa.replace('Mozilla/', '') }});
            Object.defineProperty(navigator, 'platform', {{ get: () => '{platform_str}' }});

            // 3. Screen and window dimensions matched to viewport
            Object.defineProperty(screen, 'width', {{ get: () => {vp_width} }});
            Object.defineProperty(screen, 'height', {{ get: () => {vp_height} }});
            Object.defineProperty(screen, 'availWidth', {{ get: () => {vp_width} }});
            Object.defineProperty(screen, 'availHeight', {{ get: () => {vp_height - 40} }});
            Object.defineProperty(window, 'outerWidth', {{ get: () => {vp_width} }});
            Object.defineProperty(window, 'outerHeight', {{ get: () => {vp_height} }});

            // 4. Mock realistic Chrome plugins (PDF Viewer, Chrome PDF Viewer, Chromium PDF Viewer)
            Object.defineProperty(navigator, 'plugins', {{
                get: () => {{
                    const pluginsData = [
                        {{ name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }},
                        {{ name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }},
                        {{ name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }}
                    ];
                    const pArray = Object.create(PluginArray.prototype);
                    pluginsData.forEach((p, idx) => {{
                        const plugin = Object.create(Plugin.prototype);
                        Object.defineProperties(plugin, {{
                            name: {{ get: () => p.name }},
                            filename: {{ get: () => p.filename }},
                            description: {{ get: () => p.description }},
                            length: {{ get: () => 0 }}
                        }});
                        pArray[idx] = plugin;
                        pArray[p.name] = plugin;
                    }});
                    Object.defineProperty(pArray, 'length', {{ get: () => pluginsData.length }});
                    pArray.item = function(index) {{ return this[index] || null; }};
                    pArray.namedItem = function(name) {{ return this[name] || null; }};
                    pArray.refresh = function() {{}};
                    return pArray;
                }}
            }});

            // 5. Mock Chrome runtime properties
            window.chrome = {{ runtime: {{}}, loadTimes: function() {{}}, csi: function() {{}}, app: {{}} }};
            Object.defineProperty(navigator, 'languages', {{ get: () => ['{locale}', 'en'] }});

            // 6. Permissions query spoofing
            if (navigator.permissions && navigator.permissions.query) {{
                const originalQuery = navigator.permissions.query;
                navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({{ state: Notification.permission }}) :
                        originalQuery(parameters)
                );
            }}
        """

        await context.add_init_script(init_script)
        return context

    async def _recycle_context(
        self,
        browser: Browser,
        old_context: BrowserContext,
        country: str = "US",
        proxy_url: Optional[str] = None,
    ) -> tuple[Page, BrowserContext]:
        """Close the old context and create a fresh one for the given country."""
        try:
            if old_context:
                await old_context.close()
        except Exception:
            pass
        new_context = await self._create_context(browser, country, proxy_url=proxy_url)
        new_page = await new_context.new_page()
        return new_page, new_context

    async def _scrape_page(
        self,
        context: BrowserContext,
        page: Page,
        url: str,
        country: str,
        query: str,
    ) -> list[JobPosting]:
        """
        Navigate to a single search results page and return parsed job postings.

        Context lifecycle is managed entirely by the caller (scrape()).
        This method never creates or closes a BrowserContext — it only uses the
        context to open detail pages (new_page) for description enrichment.

        Returns an empty list on any unrecoverable failure so the caller can
        decide whether to recycle the context and retry.
        """
        for attempt in range(self._settings.scraper_retry_attempts):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)

                # Transient Turnstile / Cloudflare challenge settlement:
                # If page title indicates a security check or challenge, give it a few seconds to auto-resolve
                for _ in range(3):
                    t_title = (await page.title()).lower()
                    if any(t in t_title for t in ["security check", "just a moment", "verify you are human", "attention required"]):
                        logger.debug("Transient challenge detected (title: '{}'), waiting for settlement...", t_title)
                        await asyncio.sleep(2.0)
                    else:
                        break

                if await self._is_blocked(page):
                    self._consecutive_blocks += 1
                    logger.warning(
                        "Indeed bot check on attempt {} for URL: {} (consecutive blocks: {}).",
                        attempt + 1, url, self._consecutive_blocks,
                    )
                    await self._adaptive_delay(status="blocked")
                    if attempt < self._settings.scraper_retry_attempts - 1:
                        continue
                    return []

                try:
                    await page.wait_for_selector(
                        '[data-jk], .job_seen_beacon, .jobsearch-ResultsList li',
                        timeout=10000
                    )
                except PlaywrightTimeout:
                    if attempt < self._settings.scraper_retry_attempts - 1:
                        await asyncio.sleep(2.0)
                        continue
                    return []

                # Phase 3.2: Human-like reading scroll with micro-pauses
                await self._human_scroll(page)

                html = await page.content()
                jobs = self._parser.parse_search_results(
                    html=html,
                    country=country,
                    search_query=query,
                )
                title = await page.title()
                logger.info("Indeed search page loaded: '{}' | Extracted {} raw job cards", title, len(jobs))

                # Reset circuit breaker on successful page scrape
                if jobs and self._consecutive_blocks > 0:
                    logger.info("Circuit breaker reset: scraped successfully after {} block(s)", self._consecutive_blocks)
                    self._consecutive_blocks = 0

                # Strategy 0: Direct same-origin internal fetch evaluated inside page session
                # Fast, lightweight, avoids opening extra browser tabs or navigating away
                for job in jobs:
                    if job.indeed_job_id and (not job.has_full_description or len(job.job_description or "") < 300):
                        try:
                            desc_html = await page.evaluate(
                                """async (jk) => {
                                    try {
                                        const ctrl = new AbortController();
                                        const tid = setTimeout(() => ctrl.abort(), 3500);
                                        const res = await fetch(`/viewjob?jk=${jk}&t=jobsearch`, {
                                            credentials: 'same-origin',
                                            signal: ctrl.signal
                                        });
                                        clearTimeout(tid);
                                        if (res.ok) return await res.text();
                                    } catch (e) {}
                                    return null;
                                }""",
                                job.indeed_job_id,
                            )
                            if desc_html:
                                self._parser.enrich_with_description(job, desc_html)
                                if job.has_full_description or len(job.job_description or "") > 300:
                                    logger.info("Enriched full description for '{}' ({} chars)", job.job_title, len(job.job_description))
                            await asyncio.sleep(random.uniform(0.1, 0.2))
                        except Exception as s0_err:
                            logger.debug("Strategy 0 fetch error for {}: {}", job.job_title, s0_err)

                # Strategy 1 (Fallback): For remaining jobs lacking description, use a single dedicated worker tab
                # Crucial: NEVER click links on the search results `page` to prevent page destruction or navigation away!
                domain = resolve_country_domain(country)
                remaining_needing_detail = [
                    j for j in jobs
                    if (not j.has_full_description or len(j.job_description or "") < 300) and j.indeed_job_id
                ][:2]

                if remaining_needing_detail:
                    try:
                        async with asyncio.timeout(12.0):
                            worker_page = None
                            try:
                                worker_page = await context.new_page()
                                for r_job in remaining_needing_detail:
                                    if self._stop_event.is_set():
                                        break
                                    try:
                                        target_url = f"https://{domain}/viewjob?jk={r_job.indeed_job_id}"
                                        await worker_page.goto(target_url, wait_until="domcontentloaded", timeout=6000)
                                        w_html = await worker_page.content()
                                        self._parser.enrich_with_description(r_job, w_html)
                                        if r_job.has_full_description or len(r_job.job_description or "") > 300:
                                            logger.info("Worker tab enriched full description for '{}' ({} chars)", r_job.job_title, len(r_job.job_description))
                                    except Exception as w_err:
                                        logger.debug("Worker tab enrichment error for {}: {}", r_job.job_title, w_err)
                            except Exception as wp_err:
                                logger.debug("Could not create worker tab for detail enrichment: {}", wp_err)
                            finally:
                                if worker_page:
                                    try:
                                        await worker_page.close()
                                    except Exception:
                                        pass
                    except (asyncio.TimeoutError, Exception) as enrich_err:
                        logger.debug("Worker tab enrichment window ended: {}", enrich_err)

                # Strategy 2: Parallel detail page fetch with semaphore (Phase 4.1)
                jobs_needing_detail = [
                    j for j in jobs
                    if (not j.has_full_description or len(j.job_description or "") < 300) and j.job_url
                ][:2]

                if jobs_needing_detail:
                    try:
                        async with asyncio.timeout(10.0):
                            semaphore = asyncio.Semaphore(2)

                            async def _fetch_detail_concurrent(job_to_enrich: JobPosting) -> None:
                                async with semaphore:
                                    detail_page = None
                                    try:
                                        detail_page = await context.new_page()
                                        await detail_page.goto(job_to_enrich.job_url, wait_until="domcontentloaded", timeout=6000)
                                        await asyncio.sleep(random.uniform(0.1, 0.2))
                                        detail_html = await detail_page.content()
                                        self._parser.enrich_with_description(job_to_enrich, detail_html)
                                        if job_to_enrich.has_full_description or len(job_to_enrich.job_description or "") > 300:
                                            logger.info("Strategy 2 enriched full description for '{}' ({} chars)", job_to_enrich.job_title, len(job_to_enrich.job_description))
                                    except Exception as detail_err:
                                        logger.debug("Detail page fetch skipped for {}: {}", job_to_enrich.job_title, detail_err)
                                    finally:
                                        if detail_page:
                                            try:
                                                await detail_page.close()
                                            except Exception:
                                                pass

                            await asyncio.gather(*[_fetch_detail_concurrent(j) for j in jobs_needing_detail], return_exceptions=True)
                    except (asyncio.TimeoutError, Exception) as s2_err:
                        logger.debug("Strategy 2 enrichment window ended: {}", s2_err)

                return jobs

            except Exception as exc:
                logger.error("Error scraping page on attempt {}: {}", attempt + 1, exc)
                if attempt < self._settings.scraper_retry_attempts - 1:
                    await asyncio.sleep(2.0)

        return []

    async def _human_click(self, page: Page, element) -> None:
        """
        Phase 3.1: Simulate human-like mouse movement to an element with jitter before clicking.
        """
        try:
            box = await element.bounding_box()
            if not box:
                await element.click(timeout=3000)
                return

            # Target a point within element's central 60%
            target_x = box["x"] + random.uniform(box["width"] * 0.2, box["width"] * 0.8)
            target_y = box["y"] + random.uniform(box["height"] * 0.2, box["height"] * 0.8)

            # Start from random screen position
            start_x = random.uniform(100, 600)
            start_y = random.uniform(100, 400)

            # 6-10 steps with slight coordinate jitter to simulate human hand tremor
            steps = random.randint(6, 10)
            for i in range(1, steps + 1):
                t = i / steps
                ix = start_x + (target_x - start_x) * t + random.uniform(-2, 2)
                iy = start_y + (target_y - start_y) * t + random.uniform(-2, 2)
                await page.mouse.move(ix, iy)
                await asyncio.sleep(random.uniform(0.01, 0.025))

            await page.mouse.click(target_x, target_y)
        except Exception as e:
            logger.debug("Fallback click after human_click error: {}", e)
            try:
                await element.click(timeout=3000)
            except Exception:
                pass

    async def _human_scroll(self, page: Page) -> None:
        """
        Simulate natural user scroll with quick, smooth chunk increments (1-2s total).
        """
        try:
            total_height = await page.evaluate("document.body.scrollHeight")
            if not total_height or total_height < 400:
                return

            target_max = min(total_height * 0.75, 2000)
            current = 0
            while current < target_max:
                chunk = random.randint(350, 600)
                current = min(current + chunk, int(target_max))
                await page.evaluate(f"window.scrollTo({{top: {current}, behavior: 'smooth'}})")
                await asyncio.sleep(random.uniform(0.1, 0.2))
        except Exception:
            pass

    async def _warm_up_visit(self, page: Page, country: str) -> None:
        """
        Phase 3.4: Warm up the session before executing search queries.
        Simulates natural user behavior: landing on homepage, observing, and getting baseline cookies.
        """
        try:
            domain = resolve_country_domain(country)
            home_url = f"https://{domain}/"
            logger.info("Warming up browser session on homepage: {}", home_url)
            await page.goto(home_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(random.uniform(1.5, 2.5))
        except Exception as e:
            logger.debug("Warm-up visit skipped/completed with notice: {}", e)

    async def _save_session_state(self, context: BrowserContext, country: str) -> None:
        """
        Phase 3.3: Save cookies and storage state to persist session continuity between runs.
        """
        try:
            sessions_dir = Path("sessions")
            sessions_dir.mkdir(parents=True, exist_ok=True)
            session_file = sessions_dir / f"{country.upper()}_session.json"
            state = await context.storage_state()
            session_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
            logger.debug("Saved session state to {}", session_file)
        except Exception as e:
            logger.debug("Could not save session state: {}", e)

    async def _adaptive_delay(
        self,
        status: str = "success",
        page_num: int = 0,
        jobs_count: int = 0,
    ) -> None:
        """
        Phase 3.5: Variable inter-page delays based on page content, engagement, and fatigue.
        - After 0 results: 4–7s back-off
        - After blocked page: 8–15s
        - After success: 2–4s (engaged) + fatigue after page 4
        - Occasional coffee/tab-switch pause every 4–6 pages
        """
        if status == "zero_results":
            delay = random.uniform(4.0, 7.0)
        elif status == "blocked":
            delay = random.uniform(8.0, 15.0)
        else:
            base_delay = random.uniform(self._settings.scraper_delay_min, self._settings.scraper_delay_max)
            # Add fatigue simulation after 4 pages
            fatigue = max(0, page_num - 3) * 0.8
            delay = base_delay + fatigue

            # Random 15% chance of coffee/tab-switch pause if on page 3+
            if page_num >= 3 and random.random() < 0.15:
                pause = random.uniform(6.0, 12.0)
                logger.debug("Simulating natural micro-break: {:.1f}s", pause)
                delay += pause

        await asyncio.sleep(delay)

    async def _is_blocked(self, page: Page) -> bool:
        """
        Multi-layered bot detection check:
        1. URL redirects to challenge/verification/denial routes.
        2. Known challenge titles (Cloudflare, PerimeterX, Shield, etc.).
        3. Challenge DOM elements and iframes (reCAPTCHA, Turnstile, Cloudflare).
        4. Text-based soft-blocks ("unusual traffic", "access denied", "robot").
        5. Suspicious empty jobs container when not a genuine zero-results page.
        """
        try:
            # 1. Check URL patterns
            current_url = page.url.lower()
            url_block_patterns = ["/sorry", "/blocked", "/verify", "captcha", "challenge"]
            if any(pattern in current_url for pattern in url_block_patterns):
                logger.warning("Detected soft-block via URL: {}", current_url)
                return True

            # 2. Check page title
            title = (await page.title()).lower()
            title_blocks = [
                "just a moment",
                "attention required",
                "access denied",
                "security check",
                "verify you are human",
                "robot check",
                "blocked",
            ]
            if any(signal in title for signal in title_blocks):
                logger.warning("Detected block via page title: {}", title)
                return True

            # 3. Check challenge DOM elements / iframes
            challenge = await page.query_selector(
                "#challenge-stage, #cf-please-wait, .g-recaptcha, "
                "iframe[src*='recaptcha'], iframe[src*='cloudflare'], iframe[src*='challenges']"
            )
            if challenge:
                logger.warning("Detected challenge element in DOM")
                return True

            # 4. Check page body text for Indeed soft-blocks
            try:
                body_text = (await page.inner_text("body")).lower()[:1000]
                soft_block_phrases = [
                    "please verify you are a human",
                    "let us know you're not a robot",
                    "our systems have detected unusual traffic",
                    "access to this page has been denied",
                    "too many requests",
                    "pardon our interruption",
                ]
                if any(phrase in body_text for phrase in soft_block_phrases):
                    logger.warning("Detected soft-block text in page body")
                    return True
            except Exception:
                pass

            return False
        except Exception:
            return False

    async def _random_delay(self) -> None:
        delay = random.uniform(self._settings.scraper_delay_min, self._settings.scraper_delay_max)
        await asyncio.sleep(delay)

    def _emit_progress(self, force: bool = False) -> None:
        """Throttle progress updates to maximum 2/sec when running unless state changed."""
        now = time.monotonic()
        if not force and self._progress.status == ScraperStatus.RUNNING and (now - self._last_emit_time < 0.5):
            return

        self._last_emit_time = now
        if self._progress_callback:
            try:
                self._progress_callback(self._progress)
            except Exception:
                pass
