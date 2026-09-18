import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from main import app
from app.services.scraper_service import get_scraper_service
from app.models.job import JobPosting


@pytest.fixture(autouse=True)
def cleanup_service():
    service = get_scraper_service()
    service.clear_results()
    yield
    service.clear_results()


def _seed_jobs(n=3):
    service = get_scraper_service()
    jobs = [
        JobPosting(job_title=f"SharePoint Developer {i}", company=f"Company {i}", job_description=f"Need SharePoint skills {i}")
        for i in range(n)
    ]
    service._results.extend(jobs)
    return jobs


def test_generate_outreach_batch_requires_lead_ids():
    client = TestClient(app)
    resp = client.post("/api/jobs/generate-outreach-batch", json={})
    assert resp.status_code == 400


def test_generate_outreach_batch_saves_outreach_on_each_job():
    jobs = _seed_jobs(3)
    client = TestClient(app)

    fake_outreach = {
        "email_subject": "Subject",
        "email_body": "Hi there,\n\nBody.",
        "linkedin_variants": ["Hello there"],
        "opening_line": "Opening.",
        "alignment_paragraph": "Alignment.",
    }

    with patch("app.matching.outreach_generator.generate_outreach", new_callable=AsyncMock) as mock_gen, \
         patch("app.knowledge_base.azure_search.AzureSearchKnowledgeBase.search", new_callable=AsyncMock) as mock_search:
        mock_gen.return_value = fake_outreach
        mock_search.return_value = []

        lead_ids = [str(j.id) for j in jobs]
        resp = client.post("/api/jobs/generate-outreach-batch", json={"lead_ids": lead_ids})

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["generated"] == 3
        assert data["failed"] == []
        assert mock_gen.call_count == 3

        service = get_scraper_service()
        for job in service._results:
            assert job.outreach_email_subject == "Subject"
            assert job.outreach_email_body == "Hi there,\n\nBody."
            assert job.outreach_linkedin_message == "Hello there"


def test_generate_outreach_batch_reports_failures_without_failing_whole_batch():
    jobs = _seed_jobs(2)
    client = TestClient(app)

    with patch("app.matching.outreach_generator.generate_outreach", new_callable=AsyncMock) as mock_gen, \
         patch("app.knowledge_base.azure_search.AzureSearchKnowledgeBase.search", new_callable=AsyncMock) as mock_search:
        mock_gen.side_effect = RuntimeError("rate limited")
        mock_search.return_value = []

        lead_ids = [str(j.id) for j in jobs]
        resp = client.post("/api/jobs/generate-outreach-batch", json={"lead_ids": lead_ids})

        assert resp.status_code == 200
        data = resp.json()
        assert data["generated"] == 0
        assert len(data["failed"]) == 2
