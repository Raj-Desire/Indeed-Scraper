"""Unit tests for mapping raw Dice MCP job dicts into JobPosting."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.job import RemoteType
from app.scraper.dice_mcp_client import map_to_job_posting

RAW_JOB = {
    "guid": "abc-123",
    "title": "Senior Python Developer",
    "companyName": "Acme Tech",
    "jobLocation": {"displayName": "Remote"},
    "salary": "$120,000 - $150,000",
    "detailsPageUrl": "https://www.dice.com/job-detail/abc-123",
    "companyPageUrl": "https://www.dice.com/company/acme-tech",
    "postedDate": "2026-09-15T00:00:00Z",
    "workplaceTypes": ["Remote"],
    "isRemote": True,
    "employmentType": "FULLTIME",
}

DETAILS = {
    "description": "We need a Python developer with AWS experience.",
    "skills": [{"name": "Python"}, {"name": "AWS"}],
}


def test_maps_core_fields():
    job = map_to_job_posting(RAW_JOB, DETAILS, search_query="python developer")

    assert job.job_title == "Senior Python Developer"
    assert job.company == "Acme Tech"
    assert job.location == "Remote"
    assert job.salary_range == "$120,000 - $150,000"
    assert job.job_url == "https://www.dice.com/job-detail/abc-123"
    assert job.apply_url == "https://www.dice.com/job-detail/abc-123"
    assert job.job_description == "We need a Python developer with AWS experience."
    assert job.search_query == "python developer"
    assert job.lead_source == "Dice"


def test_maps_remote_type_from_workplace_types():
    job = map_to_job_posting(RAW_JOB, DETAILS, search_query="python developer")
    assert job.remote_type == RemoteType.FULLY_REMOTE


def test_maps_hybrid_workplace_type():
    raw = dict(RAW_JOB, workplaceTypes=["Hybrid"], isRemote=False)
    job = map_to_job_posting(raw, DETAILS, search_query="python developer")
    assert job.remote_type == RemoteType.HYBRID


def test_maps_onsite_workplace_type():
    raw = dict(RAW_JOB, workplaceTypes=["On-Site"], isRemote=False)
    job = map_to_job_posting(raw, DETAILS, search_query="python developer")
    assert job.remote_type == RemoteType.ON_SITE


def test_missing_workplace_types_defaults_to_unknown():
    raw = dict(RAW_JOB, workplaceTypes=None, isRemote=None)
    job = map_to_job_posting(raw, DETAILS, search_query="python developer")
    assert job.remote_type == RemoteType.UNKNOWN


def test_handles_missing_details_gracefully():
    """get_job_details can fail for an individual result; mapping must still
    succeed using only the search_jobs summary fields."""
    job = map_to_job_posting(RAW_JOB, None, search_query="python developer")
    assert job.job_description == ""
    assert job.job_title == "Senior Python Developer"


def test_handles_missing_optional_raw_fields():
    minimal_raw = {"guid": "x", "title": "Dev", "companyName": "Co"}
    job = map_to_job_posting(minimal_raw, None, search_query="dev")
    assert job.job_title == "Dev"
    assert job.company == "Co"
    assert job.location == ""
    assert job.salary_range == "Not listed"


if __name__ == "__main__":
    print("Run with: python -m pytest tests/test_dice_mapping.py -v")
