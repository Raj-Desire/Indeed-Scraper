"""Unit tests for DiceService orchestration (MCP client, matching, export mocked)."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.job import JobPosting
from app.services.dice_service import DiceService


class _FakeDiceClient:
    def __init__(self, search_results, details_by_guid=None):
        self._search_results = search_results
        self._details_by_guid = details_by_guid or {}
        self.search_calls = []
        self.details_calls = []

    async def search_jobs(self, *, keyword, **filters):
        self.search_calls.append((keyword, filters))
        return self._search_results

    async def get_job_details(self, job_id):
        self.details_calls.append(job_id)
        return self._details_by_guid.get(job_id, {"description": "", "skills": []})

    async def close(self):
        pass


class _FakeMatchService:
    def __init__(self):
        self.evaluated = []

    async def evaluate_job(self, job):
        self.evaluated.append(job)
        job.match_score = 88
        return job

    async def close(self):
        pass


class _FakeSharePointExporter:
    def __init__(self):
        self.exported = None

    async def export_jobs(self, jobs, owner=None):
        self.exported = (jobs, owner)
        return len(jobs)


def test_search_maps_dedupes_and_scores_results():
    raw_results = [
        {"guid": "a1", "title": "Python Dev", "companyName": "Acme"},
        {"guid": "a2", "title": "Python Dev", "companyName": "Acme"},  # duplicate title+company
    ]
    dice_client = _FakeDiceClient(raw_results, {"a1": {"description": "JD text", "skills": []}})
    match_service = _FakeMatchService()

    service = DiceService(dice_client=dice_client, match_service=match_service)
    results = asyncio.run(service.search(keyword="python"))

    assert len(results) == 1  # second was deduped by title+company fingerprint
    assert results[0].job_title == "Python Dev"
    assert results[0].lead_source == "Dice"
    assert results[0].match_score == 88
    assert len(match_service.evaluated) == 1


def test_search_passes_filters_through_to_client():
    dice_client = _FakeDiceClient([])
    service = DiceService(dice_client=dice_client, match_service=_FakeMatchService())
    asyncio.run(service.search(keyword="python", location="Remote", easy_apply=True))

    assert dice_client.search_calls[0] == ("python", {"location": "Remote", "easy_apply": True})


def test_get_results_and_clear_results():
    dice_client = _FakeDiceClient([{"guid": "a1", "title": "Dev", "companyName": "Acme"}])
    service = DiceService(dice_client=dice_client, match_service=_FakeMatchService())
    asyncio.run(service.search(keyword="python"))

    assert len(service.get_results()) == 1
    service.clear_results()
    assert service.get_results() == []


def test_export_sharepoint_delegates_to_exporter():
    dice_client = _FakeDiceClient([{"guid": "a1", "title": "Dev", "companyName": "Acme"}])
    service = DiceService(dice_client=dice_client, match_service=_FakeMatchService())
    asyncio.run(service.search(keyword="python"))

    fake_exporter = _FakeSharePointExporter()
    service._sharepoint_exporter = fake_exporter  # injected for the test

    count = asyncio.run(service.export_sharepoint(owner="Meet"))

    assert count == 1
    assert fake_exporter.exported[1] == "Meet"


def test_export_sharepoint_filters_by_selected_ids():
    dice_client = _FakeDiceClient([
        {"guid": "a1", "title": "Dev One", "companyName": "Acme"},
        {"guid": "a2", "title": "Dev Two", "companyName": "Beta"},
    ])
    service = DiceService(dice_client=dice_client, match_service=_FakeMatchService())
    results = asyncio.run(service.search(keyword="python"))

    fake_exporter = _FakeSharePointExporter()
    service._sharepoint_exporter = fake_exporter

    keep_id = str(results[0].id)
    asyncio.run(service.export_sharepoint(selected_ids=[keep_id]))

    assert len(fake_exporter.exported[0]) == 1
    assert str(fake_exporter.exported[0][0].id) == keep_id


if __name__ == "__main__":
    print("Run with: python -m pytest tests/test_dice_service.py -v")
