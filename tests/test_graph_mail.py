"""
Unit Tests for Microsoft 365 Graph Email Notifier
Verifies HTML email report generation, metrics badges, Excel attachments, and settings gates.
"""

import asyncio
import os
from pathlib import Path
from uuid import uuid4
import pytest

from app.models.job import JobPosting, RemoteType
from app.notifications.graph_mail import GraphMailNotifier


def create_sample_jobs() -> list[JobPosting]:
    return [
        JobPosting(
            id=uuid4(),
            indeed_job_id="lead_001",
            job_title="Lead AI Engineer",
            company="DeepAI Labs",
            location="Remote",
            remote_type=RemoteType.FULLY_REMOTE,
            salary_range="$150,000 - $190,000",
            job_description="Developing agentic AI systems and LLM workflows.",
            match_score=85,
            matched_skills=["Python", "LangChain", "Azure OpenAI", "Vector DB"],
            job_url="https://www.indeed.com/viewjob?jk=lead_001",
        ),
        JobPosting(
            id=uuid4(),
            indeed_job_id="lead_002",
            job_title="Data Analyst II",
            company="Analytics Corp",
            location="New York, NY",
            remote_type=RemoteType.HYBRID,
            salary_range="$95,000 - $115,000",
            job_description="Building Power BI dashboards and SQL models.",
            match_score=62,
            matched_skills=["Power BI", "SQL", "Data Modeling"],
            job_url="https://www.indeed.com/viewjob?jk=lead_002",
        ),
        JobPosting(
            id=uuid4(),
            indeed_job_id="lead_003",
            job_title="Junior Developer",
            company="Starter Tech",
            location="Austin, TX",
            remote_type=RemoteType.ON_SITE,
            salary_range="Not listed",
            job_description="Entry level software engineering.",
            match_score=35,
            matched_skills=[],
            job_url="https://www.indeed.com/viewjob?jk=lead_003",
        ),
    ]


def test_build_html_report_structure():
    notifier = GraphMailNotifier()
    jobs = create_sample_jobs()

    html_content = notifier.build_html_report(
        jobs=jobs,
        query="Applied AI Engineer",
        countries=["US"],
    )

    # Check header and metrics
    assert "Indeed Job Sourcing Daily Report" in html_content
    assert "Applied AI Engineer" in html_content
    assert "US" in html_content
    assert "IST (GMT+5:30)" in html_content
    assert "Total Leads" in html_content
    assert ">3<" in html_content  # 3 total leads

    # Check high match (85) and medium match (62)
    assert ">1<" in html_content  # 1 high match (>=70)
    assert "85/100" in html_content
    assert "62/100" in html_content

    # Check job titles and links
    assert "Lead AI Engineer" in html_content
    assert "DeepAI Labs" in html_content
    assert "Data Analyst II" in html_content
    assert "https://www.indeed.com/viewjob?jk=lead_001" in html_content

    # Check skills badges
    assert "LangChain" in html_content
    assert "Power BI" in html_content

    # Check Excel attachment notice
    assert "Attached Workbook" in html_content


def test_send_report_skipped_when_disabled():
    notifier = GraphMailNotifier()
    notifier._settings.email_notifications_enabled = False

    result = asyncio.run(
        notifier.send_report(
            jobs=create_sample_jobs(),
            excel_path=None,
        )
    )
    assert result is False


def test_send_report_skipped_when_sender_missing():
    notifier = GraphMailNotifier()
    notifier._settings.email_notifications_enabled = True
    notifier._settings.mail_sender = ""
    notifier._settings.graph_sender_email = ""
    notifier._settings.notification_email_to = "test@example.com"


    result = asyncio.run(
        notifier.send_report(
            jobs=create_sample_jobs(),
            excel_path=None,
        )
    )
    assert result is False


def test_build_html_report_includes_search_parameters():
    notifier = GraphMailNotifier()
    jobs = create_sample_jobs()

    html_content = notifier.build_html_report(
        jobs=jobs,
        query="Azure Ai engineer",
        countries=["US", "GB"],
        fromage="1",
        location_type="remote",
    )

    # Check search parameters table is present
    assert "Search Parameters & Selected Filters" in html_content
    assert "Selected Countries:" in html_content
    assert "United States (US)" in html_content
    assert "United Kingdom (GB)" in html_content
    assert "Search Keyword / Role:" in html_content
    assert "Azure Ai engineer" in html_content
    assert "Date Posted Filter:" in html_content
    assert "Last 24 hours (1 day)" in html_content
    assert "Location Filter:" in html_content
    assert "Fully Remote Only" in html_content


def test_send_report_includes_sender_in_recipients(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    import httpx

    notifier = GraphMailNotifier()
    notifier._settings.email_notifications_enabled = True
    notifier._settings.mail_sender = "sender@company.com"
    notifier._settings.graph_sender_email = "sender@company.com"
    notifier._settings.notification_email_to = "recipient@company.com"

    monkeypatch.setattr(notifier, "_acquire_token", lambda: "fake-token")

    captured_payload = {}

    async def mock_post(url, json=None, headers=None):
        nonlocal captured_payload
        captured_payload = json
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post = mock_post

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: mock_client)

    result = asyncio.run(
        notifier.send_report(
            jobs=create_sample_jobs(),
            excel_path=None,
            query="Azure Ai engineer",
            countries=["US"],
            fromage="1",
        )
    )

    assert result is True
    recipients = [r["emailAddress"]["address"] for r in captured_payload["message"]["toRecipients"]]
    assert "recipient@company.com" in recipients
    assert "sender@company.com" in recipients  # Sender must be included!


def test_build_html_report_shows_all_selected_keywords_and_indeed_links():
    notifier = GraphMailNotifier()
    jobs = create_sample_jobs()
    jobs[0].search_query = "SharePoint"
    jobs[1].search_query = "Power Apps"
    jobs[2].search_query = "React"

    selected_keywords = ["SharePoint", "Power Apps", "Power Automate", "AI", ".NET", "React", "n8n"]

    html_content = notifier.build_html_report(
        jobs=jobs,
        queries=selected_keywords,
        countries=["US"],
        fromage="1",
        location_type="remote",
    )

    # Verify all selected keywords are shown in the email report
    for kw in selected_keywords:
        assert kw in html_content

    # Verify direct Indeed links and View on Indeed button
    assert "View on Indeed ↗" in html_content
    for j in jobs:
        assert j.job_url in html_content


