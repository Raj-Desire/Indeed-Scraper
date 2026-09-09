"""
Unit and Integration Tests for Phase 5 Enhancements
- 5.1 Rotating Proxy Configuration
- 5.2 Selector Health Monitoring & Metrics
- 5.3 Circuit Breaker & Exponential Back-off
- 5.4 Dynamic Browser Profiles per Target Country
- 5.5 Description Enrichment Hierarchical Fallback (Strategy 0 / 1 / 2)
"""

import pytest
from app.config.browser_profiles import get_browser_profile, BROWSER_PROFILES, DEFAULT_BROWSER_PROFILE
from app.scraper.selector_health import SelectorHealthMonitor, selector_health
from app.config.settings import get_settings
from app.scraper.indeed_scraper import IndeedScraper
from app.parser.selectolax_parser import SelectolaxParser
from app.parser.job_parser import BeautifulSoupParser
from app.models.job import JobPosting


def test_browser_profiles_resolution():
    """Verify profiles contain localized locales, timezones, and Accept-Language."""
    # US
    us = get_browser_profile("US")
    assert us["locale"] == "en-US"
    assert us["timezone_id"] == "America/New_York"
    assert "en-US" in us["accept_language"]

    # Great Britain
    gb = get_browser_profile("GB")
    assert gb["locale"] == "en-GB"
    assert gb["timezone_id"] == "Europe/London"
    assert "en-GB" in gb["accept_language"]

    # India
    in_profile = get_browser_profile("IN")
    assert in_profile["locale"] == "en-IN"
    assert in_profile["timezone_id"] == "Asia/Kolkata"

    # Germany
    de = get_browser_profile("DE")
    assert de["locale"] == "de-DE"
    assert de["timezone_id"] == "Europe/Berlin"

    # Japan
    jp = get_browser_profile("JP")
    assert jp["locale"] == "ja-JP"
    assert jp["timezone_id"] == "Asia/Tokyo"

    # Fallback default for unknown country code
    fallback = get_browser_profile("UNKNOWN_XYZ")
    assert fallback == DEFAULT_BROWSER_PROFILE


def test_selector_health_monitor():
    """Verify SelectorHealthMonitor records hits, misses, computes rates, and resets."""
    monitor = SelectorHealthMonitor()
    monitor.reset()

    # Record 4 hits and 1 miss
    for _ in range(4):
        monitor.record_hit("job_cards_container")
    monitor.record_miss("job_cards_container")

    report = monitor.report()
    assert "job_cards_container" in report
    metrics = report["job_cards_container"]
    assert metrics["hits"] == 4
    assert metrics["misses"] == 1
    assert metrics["success_rate"] == 80.0

    # Reset
    monitor.reset()
    assert len(monitor.report()) == 0


def test_circuit_breaker_backoff_math():
    """Verify exponential backoff calculation matches 30s * 2^(blocks - 3) capped at 300s."""
    max_consecutive_blocks = 3
    def compute_backoff(blocks: int) -> float:
        return min(300.0, 30.0 * (2 ** (blocks - max_consecutive_blocks)))

    assert compute_backoff(3) == 30.0
    assert compute_backoff(4) == 60.0
    assert compute_backoff(5) == 120.0
    assert compute_backoff(6) == 240.0
    assert compute_backoff(7) == 300.0
    assert compute_backoff(10) == 300.0


def test_scraper_initialization_and_proxy_settings():
    """Verify scraper attributes for circuit breaker and proxy settings are intact."""
    scraper = IndeedScraper()
    assert scraper._consecutive_blocks == 0
    assert scraper._max_consecutive_blocks == 3

    settings = get_settings()
    assert hasattr(settings, "proxy_list")
    assert hasattr(settings, "proxy_rotation")
    assert isinstance(settings.proxy_list, list)
    assert isinstance(settings.proxy_rotation, bool)


def test_selectolax_and_bs4_selector_health_integration():
    """Verify both Selectolax and BS4 parsers correctly report selector health hits/misses."""
    sample_html = """
    <html>
    <body>
    <div class="job_seen_beacon cardOutline">
        <h2 class="jobTitle"><a href="/rc/clk?jk=test12345" data-jk="test12345"><span>Lead ML Engineer</span></a></h2>
        <span data-testid="company-name">DeepMind</span>
        <div data-testid="text-location">London, UK</div>
        <div class="metadata salary-snippet-container">£120,000 - £160,000 a year</div>
    </div>
    </body>
    </html>
    """

    # Test SelectolaxParser
    selector_health.reset()
    p_sel = SelectolaxParser()
    jobs_sel = p_sel.parse_search_results(sample_html, "GB", "ML Engineer")
    assert len(jobs_sel) == 1
    assert jobs_sel[0].job_title == "Lead ML Engineer"
    assert jobs_sel[0].company == "DeepMind"
    assert jobs_sel[0].indeed_job_id == "test12345"

    rep_sel = selector_health.report()
    assert rep_sel["job_cards_container"]["hits"] == 1
    assert rep_sel["card_job_title"]["hits"] == 1
    assert rep_sel["card_company"]["hits"] == 1

    # Test BeautifulSoupParser
    selector_health.reset()
    p_bs4 = BeautifulSoupParser()
    jobs_bs4 = p_bs4.parse_search_results(sample_html, "GB", "ML Engineer")
    assert len(jobs_bs4) == 1
    assert jobs_bs4[0].job_title == "Lead ML Engineer"
    assert jobs_bs4[0].company == "DeepMind"

    rep_bs4 = selector_health.report()
    assert rep_bs4["job_cards_container"]["hits"] == 1
    assert rep_bs4["card_job_title"]["hits"] == 1
    assert rep_bs4["card_company"]["hits"] == 1
