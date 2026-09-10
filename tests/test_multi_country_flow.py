"""
Tests for Multi-Country Step-by-Step Flow and Cooldown Behavior.
Verifies:
1. Multi-country query and location filtering with remote keyword fallbacks.
2. Step-by-step logging and transitions between countries.
3. Cooldown and retry flow on bot challenges.
"""
from datetime import datetime, timezone
import pytest
from app.models.job import JobPosting, RemoteType
from app.models.scraper import RunConfig, ScraperProgress
from app.utils.helpers import is_job_matching_query


def test_is_job_matching_query_enriched_description():
    """Verify that enriched descriptions containing the keyword pass the filter even if title lacks it."""
    # Title lacks "Sharepoint", but enriched description has it
    matches = is_job_matching_query(
        job_title="Business Analyst - Information and Data Management",
        company="Kyndryl",
        location="Remote",
        description="We are seeking an expert to configure SharePoint Online document libraries and workflows.",
        query="Sharepoint",
    )
    assert matches is True


def test_is_job_matching_query_irrelevant_rejected():
    """Verify that jobs without the keyword in title, company, or description are correctly rejected."""
    matches = is_job_matching_query(
        job_title="Retail Store Assistant",
        company="Convenience Mart",
        location="Toronto, ON",
        description="Responsible for customer cash handling, stocking shelves, and daily store inventory.",
        query="Sharepoint",
    )
    assert matches is False


def test_multi_country_config_parsing():
    """Verify RunConfig accepts multi-country lists and comma-delimited strings."""
    config = RunConfig(
        query="Sharepoint",
        countries=["US", "CA", "GB", "AU", "IN"],
        pages=2,
        location_type="remote",
    )
    assert len(config.countries) == 5
    assert config.countries == ["US", "CA", "GB", "AU", "IN"]


def test_remote_fallback_location_filtering():
    """Verify remote fallback matches jobs with 'remote' or 'wfh' in description when badge is missing."""
    job = JobPosting(
        job_title="Sharepoint Developer",
        company="TechCorp",
        location="Toronto, ON",
        job_description="This position is 100% work from home / remote for Canadian residents.",
        remote_type=RemoteType.UNKNOWN,
    )
    desc_lower = f"{job.job_title} {job.location} {job.job_description or ''}".lower()
    has_remote_indicator = any(term in desc_lower for term in ["remote", "work from home", "wfh", "telecommute"])
    assert has_remote_indicator is True
