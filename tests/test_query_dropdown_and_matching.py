"""
Unit Tests for the 5 Preset Dropdown Keywords and Custom Query Matching.
Verifies that SharePoint, .NET, AI, Power Automate, Power Apps, and custom keywords
match jobs properly and are accepted by the scraping pipeline.
"""

import pytest
from app.utils.helpers import is_job_matching_query
from app.models.scraper import RunConfig


@pytest.mark.parametrize(
    "query,job_title,description,expected",
    [
        ("SharePoint", "Senior SharePoint Developer", "Building modern SPFx solutions on M365", True),
        ("SharePoint", "Java Developer", "Spring boot microservices backend", False),
        (".NET", "Senior .NET Core Engineer", "C#, ASP.NET, Azure and SQL server", True),
        (".NET", "Python Engineer", "Django and Flask development", False),
        ("AI", "Generative AI Engineer", "LLM pipelines, RAG, and OpenAI APIs", True),
        ("AI", "Warehouse Associate", "Shipping and receiving inventory in dock", False),
        ("Power Automate", "Power Automate Specialist", "Automating business approval workflows", True),
        ("Power Automate", "Frontend Designer", "Figma and CSS layout only", False),
        ("Power Apps", "Lead Power Apps Developer", "Model-driven and canvas apps for enterprise", True),
        ("Power Apps", "DBA Administrator", "Oracle database tuning", False),
        ("Prompt Engineer", "Prompt Engineer & LLM Evaluator", "Optimizing system prompts and benchmarks", True),
    ],
)
def test_five_keywords_and_custom_matching(query, job_title, description, expected):
    matched = is_job_matching_query(
        job_title=job_title,
        company="Tech Company",
        location="Remote",
        description=description,
        query=query,
    )
    assert matched is expected, f"Query '{query}' expected {expected} for title '{job_title}'"


def test_run_config_accepts_all_five_keywords():
    for kw in ["SharePoint", ".NET", "AI", "Power Automate", "Power Apps", "Custom Role"]:
        config = RunConfig(query=kw, countries=["US"])
        assert config.query == kw


def test_scraper_log_and_timestamps_use_ist():
    from app.config.constants import IST, get_ist_now
    from app.models.scraper import ScraperProgress
    from datetime import timedelta

    # Verify IST offset is GMT+5:30
    now_ist = get_ist_now()
    assert now_ist.utcoffset() == timedelta(hours=5, minutes=30)
    assert now_ist.tzinfo == IST

    # Verify log messages contain IST timestamp
    p = ScraperProgress()
    p.add_log("Search started successfully")
    assert len(p.log_messages) == 1
    assert "IST]" in p.log_messages[0]
