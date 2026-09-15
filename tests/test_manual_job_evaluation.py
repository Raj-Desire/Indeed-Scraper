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


def test_jd_parser_and_auto_fill_extraction():
    """Verify that a raw multi-parameter job description automatically extracts structured fields and unmapped parameters into Notes."""
    client = TestClient(app)

    sample_jd = """Job Title
Project Manager (Microsoft Technologies PowerPortal / PowerApps, SharePoint)
Job Location
Remote/Work From Anywhere Permanently
Job Type
Full Time
No. of Positions
2
Date Posted
February 10, 2026
Preferred Experience
10+
Job Description
We are seeking a highly skilled, dynamic and experienced Project Manager to join our team. As a Project Manager, you will play a pivotal role in overseeing and delivering projects successfully.

Job Requirements
10+ years experience in End to end Project execution covering the entire project life cycle.
Strong understanding and practical experience with Agile/Scrum methodologies and DevOps practices and tools.
Experience managing projects involving Microsoft technologies (e.g., .NET, PowerPortal/PowerApps, SharePoint, SP Online Microsoft 365), Frontend technologies (e.g., HTML, CSS, Vue, React, Angular.js), and Databases (SQL server, MySQL or MongoDB, ElasticSearch).

Email
recruit@panapps.co
Contact
9287292870
"""

    with patch("app.matching.match_service.MatchService.evaluate_job") as mock_eval:
        async def side_effect(job):
            job.match_score = 80
            job.matched_skills = ["SharePoint", "Power Apps", "Project Management"]
            job.missing_skills = []
            job.match_reason = "Strong candidate fit"
            return job

        mock_eval.side_effect = side_effect

        resp = client.post(
            "/api/jobs/manual-evaluate",
            json={
                "job_title": "",
                "job_description": sample_jd,
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        parsed = data.get("parsed_fields", {})

        # Verify auto-extracted structured parameters
        assert parsed["job_title"] == "Project Manager (Microsoft Technologies PowerPortal / PowerApps, SharePoint)"
        assert "10+" in parsed["experience"]
        assert parsed["email"] == "recruit@panapps.co"
        assert parsed["phone"] == "9287292870"
        assert "SharePoint" in parsed["technologies"]
        assert "Power Platform" in parsed["technologies"]

        # Verify unmapped parameters are cleanly bundled into Notes
        assert "Job Location: Remote/Work From Anywhere Permanently" in parsed["notes"]
        assert "Job Type: Full Time" in parsed["notes"]
        assert "No. of Positions: 2" in parsed["notes"]
        assert "Date Posted: February 10, 2026" in parsed["notes"]


def test_dynamic_ai_extraction_user_scenario():
    """Verify that unstructured prompts with salary 15000, mismatch skills, Germany, and owner Sizan are parsed correctly."""
    client = TestClient(app)

    user_jd = """Job Title: Senior Cloud Architect
salry amount 15000
person is from germany
owner is sizan
Need 7+ years of experience with SharePoint Online, Azure, and Power Platform.
Requires legacy Cobol and Ruby on Rails.
"""

    resp = client.post(
        "/api/jobs/manual-evaluate",
        json={
            "job_title": "",
            "job_description": user_jd,
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    parsed = data.get("parsed_fields", {})

    assert parsed["country"] == "DE"
    assert parsed["owner"] == "Sizan"
    assert "15000" in str(parsed["salary_range"])
    assert parsed["estimated_value"] == 15000
    assert parsed["currency_code"] in ["EUR", "USD"]
    assert "SharePoint" in parsed["technologies"]
    # Check that missing/mismatched skills were detected
    if parsed.get("missing_skills"):
        assert any("cobol" in s.lower() or "ruby" in s.lower() for s in parsed["missing_skills"])


def test_manual_evaluate_edit_and_sync_to_sharepoint():
    """Verify that editing evaluated fields and syncing to SharePoint stores the updated edited values."""
    client = TestClient(app)

    with patch("app.matching.match_service.MatchService.evaluate_job") as mock_eval:
        async def side_effect(job):
            job.match_score = 75
            job.matched_skills = ["SharePoint"]
            job.missing_skills = []
            job.match_reason = "Basic SharePoint match"
            return job

        mock_eval.side_effect = side_effect

        # 1. First evaluate raw job description
        eval_resp = client.post(
            "/api/jobs/manual-evaluate",
            json={
                "job_title": "Initial AI Title",
                "job_description": "We need a SharePoint developer for a US based client.",
            },
        )
        assert eval_resp.status_code == 200

        # 2. User changes / edits the fields in the UI
        edited_opportunity = {
            "title": "Principal SharePoint & AI Architect (Edited by User)",
            "country": "UK",
            "industry": "Healthcare",
            "website": "https://custom-company.com/jobs/123",
            "owner": "Sizan",
            "lead_source": "LinkedIn",
            "priority": "High",
            "status": "Qualified",
            "technology": ["AI", "SharePoint", "Power Platform"],
            "currency_code": "GBP",
            "estimated_value": 15000.0,
            "next_follow_up_date": "2026-09-25",
            "due_date": "2026-10-01",
            "contact_name": "Dr. Sarah Connor",
            "email": "sarah.connor@custom-company.com",
            "phone": "+44 7700 900077",
            "salary_range": "£90,000 - £110,000 / yr",
            "experience_criteria": "8+ years",
            "job_requirement": "We need a SharePoint developer for a US based client.",
            "notes": "Edited notes: Client needs fast turnaround and HIPAA / GDPR compliance.",
            "matching_score": 85,
            "matching_skills": ["AI", "SharePoint", "Power Platform"],
            "matching_reason": "High priority healthcare cloud project.",
            "missing_skills": [],
        }

        with patch("app.sharepoint.graph_exporter.GraphSharePointExporter.export_opportunity", new_callable=AsyncMock) as mock_export:
            mock_export.return_value = {"id": "sp-opportunity-777"}

            # 3. User clicks Sync to SharePoint (which posts the edited opportunity)
            sync_resp = client.post("/api/sharepoint/add-opportunity", json=edited_opportunity)
            assert sync_resp.status_code == 200
            data = sync_resp.json()
            assert data["status"] == "success"
            assert data["data"]["id"] == "sp-opportunity-777"

            # Verify that export_opportunity was called with the EDITED values
            mock_export.assert_called_once()
            called_payload = mock_export.call_args[0][0]
            assert called_payload["title"] == "Principal SharePoint & AI Architect (Edited by User)"
            assert called_payload["country"] == "UK"
            assert called_payload["owner"] == "Sizan"
            assert called_payload["technology"] == ["AI", "SharePoint", "Power Platform"]
            assert called_payload["salary_range"] == "£90,000 - £110,000 / yr"
            assert called_payload["contact_name"] == "Dr. Sarah Connor"
            assert called_payload["email"] == "sarah.connor@custom-company.com"

        # 4. Verify in-memory leads also updated to match edited values
        leads_resp = client.get("/api/leads")
        assert leads_resp.status_code == 200
        leads = leads_resp.json()["leads"]
        assert len(leads) == 1
        assert leads[0]["job_title"] == "Principal SharePoint & AI Architect (Edited by User)"
        assert leads[0]["country"] == "UK"
        assert leads[0]["salary"] == "£90,000 - £110,000 / yr"


