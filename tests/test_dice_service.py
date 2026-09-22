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


def test_search_skips_scoring_when_kb_matching_disabled_and_no_match_service_injected():
    """Mirrors ScraperService._run_pipeline's enable_kb_matching killswitch: when no
    match_service is injected and the setting is off, scoring must not happen at all."""
    dice_client = _FakeDiceClient([{"guid": "a1", "title": "Dev", "companyName": "Acme"}])
    service = DiceService(dice_client=dice_client)  # no match_service injected
    service._settings.enable_kb_matching = False

    results = asyncio.run(service.search(keyword="python"))

    assert len(results) == 1
    assert results[0].match_score is None
    assert service._match_service is None


def test_search_lazily_builds_match_service_when_kb_matching_enabled_and_none_injected(monkeypatch):
    """When nothing is injected but the setting is on, DiceService should lazily
    construct a real MatchService the same way ScraperService does."""
    import app.services.dice_service as dice_service_mod

    dice_client = _FakeDiceClient([{"guid": "a1", "title": "Dev", "companyName": "Acme"}])
    service = DiceService(dice_client=dice_client)  # no match_service injected
    service._settings.enable_kb_matching = True

    fake_instance = _FakeMatchService()
    monkeypatch.setattr(dice_service_mod, "MatchService", lambda: fake_instance)

    results = asyncio.run(service.search(keyword="python"))

    assert service._match_service is fake_instance
    assert len(fake_instance.evaluated) == 1
    assert results[0].match_score == 88


def test_search_still_scores_with_injected_match_service_regardless_of_setting():
    """Existing tests inject a match_service directly; the lazy-construction change
    must not affect that path even when enable_kb_matching is False."""
    dice_client = _FakeDiceClient([{"guid": "a1", "title": "Dev", "companyName": "Acme"}])
    match_service = _FakeMatchService()
    service = DiceService(dice_client=dice_client, match_service=match_service)
    service._settings.enable_kb_matching = False

    results = asyncio.run(service.search(keyword="python"))

    assert len(match_service.evaluated) == 1
    assert results[0].match_score == 88


def test_search_multi_runs_one_call_per_keyword_country_pair():
    dice_client = _FakeDiceClient([{"guid": "a1", "title": "Dev", "companyName": "Acme"}])
    service = DiceService(dice_client=dice_client, match_service=_FakeMatchService())

    asyncio.run(service.search_multi(keywords=["python", "java"], countries=["United States", "Canada"]))

    assert len(dice_client.search_calls) == 4
    called_pairs = {(kw, filters.get("location")) for kw, filters in dice_client.search_calls}
    assert called_pairs == {
        ("python", "United States"), ("python", "Canada"),
        ("java", "United States"), ("java", "Canada"),
    }


def test_search_multi_with_no_countries_omits_location_filter():
    dice_client = _FakeDiceClient([{"guid": "a1", "title": "Dev", "companyName": "Acme"}])
    service = DiceService(dice_client=dice_client, match_service=_FakeMatchService())

    asyncio.run(service.search_multi(keywords=["python"], countries=[]))

    assert len(dice_client.search_calls) == 1
    keyword, filters = dice_client.search_calls[0]
    assert keyword == "python"
    assert "location" not in filters


def test_search_multi_dedupes_across_combinations():
    """Same job returned by every combo call collapses to one result via the
    existing stateful DedupFilter, which persists across search() calls."""
    dice_client = _FakeDiceClient([{"guid": "a1", "title": "Same Dev", "companyName": "Acme"}])
    service = DiceService(dice_client=dice_client, match_service=_FakeMatchService())

    new_jobs = asyncio.run(service.search_multi(keywords=["python", "java"], countries=["United States"]))

    assert len(new_jobs) == 1
    assert len(service.get_results()) == 1


def test_search_multi_forwards_shared_filters_to_every_combo():
    dice_client = _FakeDiceClient([])
    service = DiceService(dice_client=dice_client, match_service=_FakeMatchService())

    asyncio.run(service.search_multi(keywords=["python"], countries=["United States"], easy_apply=True))

    _, filters = dice_client.search_calls[0]
    assert filters == {"location": "United States", "easy_apply": True}


def test_search_multi_single_keyword_no_countries_uses_explicit_location_if_given():
    """When no countries are selected, an explicit `location` kwarg (e.g. a
    freeform city/state) should still be forwarded untouched."""
    dice_client = _FakeDiceClient([])
    service = DiceService(dice_client=dice_client, match_service=_FakeMatchService())

    asyncio.run(service.search_multi(keywords=["python"], countries=[], location="New York, NY"))

    _, filters = dice_client.search_calls[0]
    assert filters == {"location": "New York, NY"}


def test_search_multi_stream_yields_expected_events():
    dice_client = _FakeDiceClient([{"guid": "a1", "title": "Dev", "companyName": "Acme"}])
    service = DiceService(dice_client=dice_client, match_service=_FakeMatchService())

    async def collect():
        events = []
        async for ev in service.search_multi_stream(keywords=["python", "java"], countries=["United States"]):
            events.append(ev)
        return events

    events = asyncio.run(collect())
    event_types = [e["type"] for e in events]
    assert "start" in event_types
    assert "progress" in event_types
    assert "enriching" in event_types
    assert "complete" in event_types
    complete_event = [e for e in events if e["type"] == "complete"][0]
    assert complete_event["combos"] == 2
    assert complete_event["percent"] == 100
    assert len(complete_event["leads"]) == 1


def test_search_resolves_canadian_and_us_countries():
    canadian_job = {"guid": "ca1", "title": "Dev", "companyName": "Acme", "jobLocation": {"displayName": "Toronto, Ontario, Canada"}}
    remote_job = {"guid": "ca2", "title": "Lead", "companyName": "Beta", "jobLocation": None}
    us_job = {"guid": "us1", "title": "Architect", "companyName": "Gamma", "jobLocation": {"displayName": "Austin, Texas, USA"}}

    dice_client = _FakeDiceClient([canadian_job, remote_job, us_job])
    service = DiceService(dice_client=dice_client, match_service=_FakeMatchService())

    results = asyncio.run(service.search("python", location="Canada"))
    assert results[0].country == "CA"
    assert results[1].country == "CA"  # Remote job with Canada location filter maps to CA
    assert results[2].country == "US"  # Explicit USA displayName maps to US


def test_dice_service_send_email_notification(monkeypatch):
    from unittest.mock import AsyncMock
    dice_client = _FakeDiceClient([{"guid": "a1", "title": "Dev", "companyName": "Acme"}])
    service = DiceService(dice_client=dice_client, match_service=_FakeMatchService())
    asyncio.run(service.search("python"))

    assert service.is_email_sent() is False

    mock_send_report = AsyncMock(return_value=True)
    import app.notifications.graph_mail as gm
    monkeypatch.setattr(gm.GraphMailNotifier, "send_report", mock_send_report)

    sent = asyncio.run(service.send_email_notification(
        query="python",
        queries=["python"],
        countries=["US"],
        fromage="1",
        location_type="remote",
        status="completed",
    ))

    assert sent is True
    assert service.is_email_sent() is True
    assert mock_send_report.called
    kwargs = mock_send_report.call_args.kwargs
    assert kwargs.get("source") == "Dice"
    assert kwargs.get("query") == "python"

    # Verify clear_results resets is_email_sent
    service.clear_results()
    assert service.is_email_sent() is False


if __name__ == "__main__":
    print("Run with: python -m pytest tests/test_dice_service.py -v")


