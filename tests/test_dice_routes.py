"""Integration tests for the /api/dice/* routes (DiceService mocked)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.models.job import JobPosting


def _make_client(fake_service, monkeypatch):
    import app.dashboard.router as router_mod
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router_mod.router)
    monkeypatch.setattr(router_mod, "get_dice_service", lambda: fake_service)
    return TestClient(app)


class _FakeDiceService:
    def __init__(self):
        self.results = []
        self.search_args = None
        self.cleared = False
        self.exported_with = None

    async def search(self, keyword, **filters):
        self.search_args = (keyword, filters)
        job = JobPosting(job_title="Python Dev", company="Acme", lead_source="Dice", match_score=90)
        self.results = [job]
        return self.results

    def get_results(self):
        return self.results

    def clear_results(self):
        self.cleared = True
        self.results = []

    async def export_sharepoint(self, selected_ids=None, owner=None):
        self.exported_with = (selected_ids, owner)
        return len(self.results)


def test_post_dice_search_returns_serialized_jobs(monkeypatch):
    fake_service = _FakeDiceService()
    client = _make_client(fake_service, monkeypatch)

    resp = client.post("/api/dice/search", json={"keyword": "python", "location": "Remote"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["leads"][0]["job_title"] == "Python Dev"
    assert body["leads"][0]["lead_source"] == "Dice"
    assert fake_service.search_args == ("python", {"location": "Remote"})


def test_post_dice_search_requires_keyword(monkeypatch):
    fake_service = _FakeDiceService()
    client = _make_client(fake_service, monkeypatch)

    resp = client.post("/api/dice/search", json={"location": "Remote"})

    assert resp.status_code == 422


def test_get_dice_results(monkeypatch):
    fake_service = _FakeDiceService()
    fake_service.results = [JobPosting(job_title="X", company="Y", lead_source="Dice")]
    client = _make_client(fake_service, monkeypatch)

    resp = client.get("/api/dice/results")

    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_post_dice_clear(monkeypatch):
    fake_service = _FakeDiceService()
    fake_service.results = [JobPosting(job_title="X", company="Y", lead_source="Dice")]
    client = _make_client(fake_service, monkeypatch)

    resp = client.post("/api/dice/clear")

    assert resp.status_code == 200
    assert fake_service.cleared is True


def test_post_dice_export_sharepoint(monkeypatch):
    fake_service = _FakeDiceService()
    fake_service.results = [JobPosting(job_title="X", company="Y", lead_source="Dice")]
    client = _make_client(fake_service, monkeypatch)

    resp = client.post("/api/dice/export/sharepoint", json={"owner": "Meet"})

    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    assert fake_service.exported_with == (None, "Meet")


def test_post_dice_export_sharepoint_no_results_returns_400(monkeypatch):
    fake_service = _FakeDiceService()
    client = _make_client(fake_service, monkeypatch)

    resp = client.post("/api/dice/export/sharepoint", json={})

    assert resp.status_code == 400
