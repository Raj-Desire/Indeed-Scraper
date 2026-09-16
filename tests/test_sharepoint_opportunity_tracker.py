"""
Unit & Integration Tests for SharePoint Opportunity Tracker Integration
========================================================================
Verifies:
1. All 30 Opportunity Tracker fields are accurately built and sanitized.
2. MultiChoice arrays, numbers, dates, choices, and internal SharePoint field names are mapped.
3. /api/sharepoint/add-opportunity endpoint receives and processes full CRM opportunity payloads.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.models.opportunity import OpportunityPayload
from main import app
from app.models.job import JobPosting
from app.sharepoint.graph_exporter import GraphSharePointExporter


@pytest.fixture
def mock_settings():
    return Settings(
        azure_tenant_id="test-tenant-id",
        azure_client_id="test-client-id",
        azure_client_secret="test-client-secret",
        sharepoint_site_id="test-site-id",
        sharepoint_list_name="Opportunity Tracker",
        sharepoint_list_id="3dd65b77-27a0-47bf-9068-e3d00b9ce18a",
        sharepoint_auto_sync=False,
    )


def test_build_opportunity_fields_all_30_columns():
    """Verify build_opportunity_fields handles all fields with exact internal names and data types."""
    exporter = GraphSharePointExporter()

    raw_input = {
        "title": "Senior SharePoint SPFx Developer",
        "company": "Acme Corp",
        "contact_name": "Alice Johnson",
        "email": "alice@example.com",
        "phone": "+1 555-0199",
        "country": "US",
        "industry": "IT",
        "lead_source": "LinkedIn",
        "owner": "Meet",
        "priority": "High",
        "date_added": "2026-09-14",
        "status": "New",
        "next_follow_up_date": "2026-09-20",
        "last_activity_date": "2026-09-14",
        "notes": "Excellent candidate lead",
        "technology": ["AI", "SharePoint", "Power Platform"],
        "estimated_value": 7500.50,
        "currency_code": "USD",
        "due_date": "2026-09-30",
        "vp_approval_status": "Not Required",
        "outcome_reason": "New Client",
        "checklist": ["Applied On Source Portal", "Applied On Sales Navigator"],
        "job_requirement": "Must have 5+ years SharePoint Framework (SPFx) experience.",
        "matching_score": 88,
        "matching_skills": ["SharePoint", "SPFx", "TypeScript", "Azure"],
        "matching_reason": "Strong match with existing company knowledge base.",
        "missing_skills": ["Power BI"],
        "experience_criteria": "5+ years",
        "salary_range": "$130k - $160k",
    }

    fields = exporter.build_opportunity_fields(raw_input)

    # Validate exact SharePoint internal column names
    # 'Title' displays as "Prospect/Company Name" in the Opportunity Tracker UI, so it
    # holds the company name; the job title goes to the dedicated 'Job_x0020_Title' column.
    assert fields["Title"] == "Acme Corp"
    assert fields["Job_x0020_Title"] == "Senior SharePoint SPFx Developer"
    assert fields["ContactName"] == "Alice Johnson"
    assert fields["Email"] == "alice@example.com"
    assert fields["Phone"] == "+1 555-0199"
    assert fields["Country"] == "US"
    assert fields["Industry"] == "IT"
    assert fields["LeadSource"] == "LinkedIn"
    assert fields["Owner"] == "Meet"
    assert fields["Priority"] == "High"
    assert fields["Status"] == "New"
    assert fields["DateAdded"] == "2026-09-14T00:00:00Z"
    assert fields["NextFollow_x002d_upDate"] == "2026-09-20T00:00:00Z"
    assert fields["LastActivityDate"] == "2026-09-14T00:00:00Z"
    assert fields["Notes"] == "Excellent candidate lead"
    assert fields["Technology"] == ["AI", "SharePoint", "Power Platform"]
    assert fields["Technology@odata.type"] == "Collection(Edm.String)"
    assert fields["EstimatedValue"] == 7500.50
    assert fields["CurrencyCode"] == "USD"
    assert fields["DueDate"] == "2026-09-30T00:00:00Z"
    assert fields["VPApprovalStatus"] == "Not Required"
    assert fields["OutcomeReason"] == "New Client"
    assert fields["Checklist"] == ["Applied On Source Portal", "Applied On Sales Navigator"]
    assert fields["Checklist@odata.type"] == "Collection(Edm.String)"
    assert fields["Job_x0020_Requirement"] == "Must have 5+ years SharePoint Framework (SPFx) experience."
    assert fields["Matching_x0020_Score"] == 0.88
    assert fields["Matching_x0020_Skills"] == "SharePoint, SPFx, TypeScript, Azure"
    assert fields["Matching_x0020_Reason"] == "Strong match with existing company knowledge base."
    assert fields["Missing_x0020_Skills"] == "Power BI"
    assert fields["Experience_x0020_Criteria"] == "5+ years"
    assert fields["Salary_x0020_Range"] == "$130k - $160k"


@pytest.mark.asyncio
async def test_export_opportunity_graph_api_call():
    """Verify export_opportunity constructs the correct Graph API POST call."""
    exporter = GraphSharePointExporter()
    exporter._settings.sharepoint_site_id = "test-site-id"
    exporter._settings.sharepoint_list_id = "3dd65b77-27a0-47bf-9068-e3d00b9ce18a"

    payload_data = {
        "title": "Lead from Upwork",
        "company": "Upwork Client LLC",
        "owner": "Sizan",
        "lead_source": "Upwork",
        "technology": ["AI", ".NET"],
        "matching_score": 90,
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"id": "item-12345", "webUrl": "https://sharepoint/item/12345"}

    with patch.object(exporter, "_acquire_token", return_value="fake-token"):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            res = await exporter.export_opportunity(payload_data)

            assert res["id"] == "item-12345"
            mock_post.assert_called_once()
            called_args, called_kwargs = mock_post.call_args
            assert "https://graph.microsoft.com/v1.0/sites/test-site-id/lists/3dd65b77-27a0-47bf-9068-e3d00b9ce18a/items" in called_args[0]
            fields = called_kwargs["json"]["fields"]
            assert fields["Title"] == "Upwork Client LLC"
            assert fields["Job_x0020_Title"] == "Lead from Upwork"
            assert fields["Owner"] == "Sizan"
            assert fields["LeadSource"] == "Upwork"
            assert fields["Technology"] == ["AI", ".NET"]
            assert fields["Matching_x0020_Score"] == 0.9


def test_add_opportunity_api_endpoint():
    """Verify /api/sharepoint/add-opportunity endpoint receives and creates SharePoint item."""
    client = TestClient(app)

    opportunity_data = {
        "title": "Power BI & Dynamics Lead",
        "company": "Enterprise Global",
        "country": "UK",
        "industry": "Healthcare",
        "owner": "Chetan",
        "lead_source": "Indeed",
        "priority": "High",
        "status": "New",
        "technology": ["Dynamics", "Power BI"],
        "currency_code": "GBP",
        "estimated_value": 12000.0,
        "notes": "Fast track required",
        "job_requirement": "Dynamics 365 and Power BI developer with Healthcare domain knowledge.",
        "matching_score": 92,
        "matching_skills": ["Dynamics", "Power BI"],
        "matching_reason": "Direct domain match with company profile.",
        "missing_skills": [],
    }

    with patch("app.sharepoint.graph_exporter.GraphSharePointExporter.export_opportunity", new_callable=AsyncMock) as mock_export:
        mock_export.return_value = {"id": "sp-item-999"}
        resp = client.post("/api/sharepoint/add-opportunity", json=opportunity_data)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["data"]["id"] == "sp-item-999"
        mock_export.assert_called_once()


@pytest.mark.asyncio
async def test_batch_export_opportunities_exporter():
    """Verify GraphSharePointExporter.export_opportunities batches multiple items with single session."""
    exporter = GraphSharePointExporter()
    exporter._settings.sharepoint_site_id = "test-site-id"
    exporter._settings.sharepoint_list_id = "3dd65b77-27a0-47bf-9068-e3d00b9ce18a"

    batch_items = [
        {"title": "Role 1", "country": "US", "job_requirement": "Description 1"},
        {"title": "Role 2", "country": "UK", "job_requirement": "Description 2"},
        {"title": "Role 3", "country": "South Africa", "job_requirement": "Description 3"},
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.side_effect = [
        {"id": "item-1"},
        {"id": "item-2"},
        {"id": "item-3"},
    ]

    with patch.object(exporter, "_acquire_token", return_value="fake-token"):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            res = await exporter.export_opportunities(batch_items)

            assert res["success_count"] == 3
            assert res["total"] == 3
            assert len(res["items"]) == 3
            assert len(res["errors"]) == 0
            assert mock_post.call_count == 3


def test_batch_add_opportunity_api_endpoint():
    """Verify /api/sharepoint/batch-add-opportunity endpoint receives and processes multiple opportunities in 1 call."""
    client = TestClient(app)

    batch_data = [
        {
            "title": "Lead 1 - SharePoint Architect",
            "country": "US",
            "owner": "Meet",
            "technology": ["SharePoint", "AI"],
            "job_requirement": "Architect with Azure experience.",
        },
        {
            "title": "Lead 2 - Power Platform Lead",
            "country": "UK",
            "owner": "Sizan",
            "technology": ["Power Platform"],
            "job_requirement": "Power Automate & Power Apps specialist.",
        },
        {
            "title": "Lead 3 - Full Stack .NET",
            "country": "South Africa",
            "owner": "Chetan",
            "technology": [".NET", "AI"],
            "job_requirement": "C# ASP.NET Core developer.",
        }
    ]

    mock_return = {
        "success_count": 3,
        "total": 3,
        "items": [{"id": "sp-1"}, {"id": "sp-2"}, {"id": "sp-3"}],
        "errors": [],
    }

    with patch("app.sharepoint.graph_exporter.GraphSharePointExporter.export_opportunities", new_callable=AsyncMock) as mock_batch_export:
        mock_batch_export.return_value = mock_return
        resp = client.post("/api/sharepoint/batch-add-opportunity", json=batch_data)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["count"] == 3
        assert "Successfully created 3/3 opportunities" in data["message"]
        mock_batch_export.assert_called_once()
        called_args, _ = mock_batch_export.call_args
        assert len(called_args[0]) == 3

