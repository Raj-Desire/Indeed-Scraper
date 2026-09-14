"""
Unit Tests for Multi-Keyword (5 to 7 Keywords) Scraping Flow.
Verifies RunConfig multi-keyword parsing, backwards compatibility, and pipeline query handling.
"""

import pytest
from app.models.scraper import RunConfig, ScraperProgress, ScraperStatus
from app.utils.helpers import is_job_matching_query


def test_run_config_multi_keyword_list():
    """Verify RunConfig accepts a list of 5 to 7 keywords properly."""
    keywords = [
        "SharePoint Developer",
        "Power Apps Developer",
        "Power Automate Consultant",
        "M365 Consultant",
        "Power Platform Specialist",
    ]
    config = RunConfig(queries=keywords, countries=["US"], max_pages=1)
    assert len(config.queries) == 5
    assert config.queries == keywords
    assert config.query == "SharePoint Developer"
    assert config.country == "US"


def test_run_config_comma_separated_query_string():
    """Verify comma-separated query string automatically expands into queries list."""
    config = RunConfig(
        query="SharePoint Developer, Power Apps, Power Automate",
        countries=["US"],
    )
    assert config.queries == ["SharePoint Developer", "Power Apps", "Power Automate"]
    assert config.query == "SharePoint Developer"


def test_run_config_single_keyword_backward_compatibility():
    """Verify single query string behaves normally as before."""
    config = RunConfig(query="Python Engineer", countries=["US"])
    assert config.queries == ["Python Engineer"]
    assert config.query == "Python Engineer"


def test_run_config_empty_or_whitespace_handling():
    """Verify empty/whitespace items are filtered out cleanly."""
    config = RunConfig(
        queries=[" SharePoint ", "  ", "Power Apps", ""],
        countries=["US"],
    )
    assert config.queries == ["SharePoint", "Power Apps"]
    assert config.query == "SharePoint"


def test_scraper_progress_reflects_current_keyword():
    """Verify ScraperProgress accurately holds current_keyword and country."""
    p = ScraperProgress(
        status=ScraperStatus.RUNNING,
        current_country="US",
        current_keyword="Power Apps Developer",
        current_page=2,
        max_pages=5,
    )
    assert p.current_keyword == "Power Apps Developer"
    assert p.current_country == "US"
    assert p.progress_percent > 0


def test_matching_with_multiple_different_keywords():
    """Verify distinct keywords match respective domain postings."""
    test_cases = [
        ("SharePoint", "Senior SharePoint SPFx Engineer", True),
        ("SharePoint", "Warehouse Manager", False),
        ("Power Apps", "Lead Power Apps Developer", True),
        ("Power Automate", "Lead Power Automate Architect", True),
        ("AI", "Generative AI and LLM Engineer", True),
        (".NET", "Senior C# .NET Core Software Engineer", True),
        (".NET", "Chef / Line Cook", False),
        ("React", "Senior React Frontend Developer", True),
        ("React", "Java Backend Developer", False),
        ("n8n", "Lead n8n Workflow Automation Engineer", True),
        ("n8n", "Dental Assistant", False),
    ]
    for query, title, expected in test_cases:
        matched = is_job_matching_query(
            job_title=title,
            company="Enterprise Corp",
            location="Remote",
            description="Developing enterprise solutions",
            query=query,
        )
        assert matched is expected, f"Query '{query}' vs '{title}' expected {expected}"


def test_seven_core_keywords_default():
    """Verify RunConfig defaults to the 7 core services."""
    config = RunConfig()
    expected_seven = ["SharePoint", "Power Apps", "Power Automate", "AI", ".NET", "React", "n8n"]
    assert config.queries == expected_seven
    assert config.query == "SharePoint"

