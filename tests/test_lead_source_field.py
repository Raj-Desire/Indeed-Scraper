"""Unit tests for JobPosting.lead_source and its use in SharePoint export."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.job import JobPosting


def test_job_posting_lead_source_defaults_to_indeed():
    job = JobPosting(job_title="Dev", company="Acme")
    assert job.lead_source == "Indeed"


def test_job_posting_lead_source_can_be_set_to_dice():
    job = JobPosting(job_title="Dev", company="Acme", lead_source="Dice")
    assert job.lead_source == "Dice"


def test_export_jobs_uses_job_lead_source_not_hardcoded():
    """graph_exporter must read job.lead_source per-job, not hardcode 'Indeed'."""
    import app.sharepoint.graph_exporter as ge_mod

    captured_payloads = []

    class _FakeResponse:
        status_code = 201

        def json(self):
            return {"id": "1"}

    class _FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            captured_payloads.append(json)
            return _FakeResponse()

    exporter = ge_mod.GraphSharePointExporter()
    exporter._settings.sharepoint_site_id = "site-1"
    exporter._settings.sharepoint_list_id = "list-1"
    exporter._acquire_token = lambda: "fake-token"

    orig_async_client = ge_mod.httpx.AsyncClient
    ge_mod.httpx.AsyncClient = _FakeAsyncClient
    try:
        job = JobPosting(job_title="Dev", company="Acme", lead_source="Dice")
        asyncio.run(exporter.export_jobs([job]))
    finally:
        ge_mod.httpx.AsyncClient = orig_async_client

    assert len(captured_payloads) == 1
    assert captured_payloads[0]["fields"]["LeadSource"] == "Dice"


if __name__ == "__main__":
    test_job_posting_lead_source_defaults_to_indeed()
    test_job_posting_lead_source_can_be_set_to_dice()
    test_export_jobs_uses_job_lead_source_not_hardcoded()
    print("OK")
