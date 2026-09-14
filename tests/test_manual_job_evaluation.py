import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from main import app
from app.services.scraper_service import get_scraper_service
from app.matching.models import MatchResult


@pytest.fixture(autouse=True)
def cleanup_service():
    service = get_scraper_service()
    service.clear_results()
    yield
    service.clear_results()


def test_manual_evaluate_validation():
    client = TestClient(app)
    # Missing description
    resp = client.post("/api/jobs/manual-evaluate", json={"job_title": "Test Title"})
    assert resp.status_code == 422

    # Empty description
    resp = client.post("/api/jobs/manual-evaluate", json={"job_title": "Test Title", "job_description": "   "})
    assert resp.status_code == 422


def test_manual_evaluate_success():
    client = TestClient(app)

    fake_result = MatchResult(
        match_score=88,
        matched_skills=["SharePoint", "Power Apps", "Power Automate"],
        missing_skills=["SAP"],
        match_reason="Strong match for Microsoft Power Platform stack.",
        job_summary="Looking for a SharePoint Power Apps specialist to lead automation.",
    )

    with patch("app.matching.match_service.MatchService.evaluate_job") as mock_eval:
        async def side_effect(job):
            job.match_score = fake_result.match_score
            job.matched_skills = fake_result.matched_skills
            job.missing_skills = fake_result.missing_skills
            job.match_reason = fake_result.match_reason
            job.job_summary = fake_result.job_summary
            return job

        mock_eval.side_effect = side_effect

        resp = client.post(
            "/api/jobs/manual-evaluate",
            json={
                "job_title": "Senior SharePoint Developer",
                "company": "Contoso Global",
                "location": "Remote",
                "country": "US",
                "salary_range": "$130k - $150k",
                "experience": "5+ years",
                "job_description": "We need a senior SharePoint and Power Platform engineer with deep SPFx expertise.",
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        lead = data["lead"]
        assert lead["job_title"] == "Senior SharePoint Developer"
        assert lead["company"] == "Contoso Global"
        assert lead["match_score"] == 88
        assert "SharePoint" in lead["matched_skills"]
        assert "SAP" in lead["missing_skills"]

        # Check that it appears in /api/leads
        leads_resp = client.get("/api/leads")
        assert leads_resp.status_code == 200
        leads_data = leads_resp.json()
        assert leads_data["total"] == 1
        assert leads_data["leads"][0]["job_title"] == "Senior SharePoint Developer"

        # Check that /api/export/excel exports it
        export_resp = client.get("/api/export/excel")
        assert export_resp.status_code == 200
        assert "spreadsheetml" in export_resp.headers.get("content-type", "")

        # Check that /api/jobs/clear cleans it up
        clear_resp = client.post("/api/jobs/clear")
        assert clear_resp.status_code == 200
        assert clear_resp.json()["status"] == "cleared"

        leads_after_clear = client.get("/api/leads")
        assert leads_after_clear.json()["total"] == 0
