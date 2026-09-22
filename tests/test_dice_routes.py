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
        self.search_multi_args = None
        self.cleared = False
        self.exported_with = None
        self._email_sent = False
        self._last_search_params = {}

    async def search_multi(self, keywords, countries, **filters):
        self.search_multi_args = (keywords, countries, filters)
        job = JobPosting(job_title="Python Dev", company="Acme", lead_source="Dice", match_score=90)
        self.results = [job]
        return self.results

    async def search_multi_stream(self, keywords, countries, **filters):
        self.search_multi_args = (keywords, countries, filters)
        job = JobPosting(job_title="Python Dev", company="Acme", lead_source="Dice", match_score=90)
        self.results = [job]
        yield {"type": "start", "total_combos": len(keywords) * max(len(countries), 1), "percent": 0, "message": "Starting..."}
        yield {"type": "progress", "combo_index": 1, "total_combos": 1, "remaining": 0, "keyword": keywords[0], "location": "Remote", "jobs_found": 1, "new_jobs": 1, "percent": 50, "message": "Searching..."}
        yield {"type": "complete", "total": 1, "new_count": 1, "combos": 1, "percent": 100, "leads": self.results, "message": "Done"}

    def get_results(self):
        return self.results

    def clear_results(self):
        self.cleared = True
        self.results = []
        self._email_sent = False

    def is_email_sent(self):
        return self._email_sent

    def mark_email_sent(self, sent=True):
        self._email_sent = sent

    async def send_email_notification(self, **kwargs):
        self._email_sent = True
        return True

    def export_excel(self, selected_ids=None):
        from pathlib import Path
        return Path("outputs/test_dice.xlsx")

    async def export_sharepoint(self, selected_ids=None, owner=None):
        self.exported_with = (selected_ids, owner)
        return len(self.results)


def test_post_dice_search_returns_serialized_jobs(monkeypatch):
    fake_service = _FakeDiceService()
    client = _make_client(fake_service, monkeypatch)

    resp = client.post("/api/dice/search", json={"keywords": ["python"], "location": "Remote"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["leads"][0]["job_title"] == "Python Dev"
    assert body["leads"][0]["lead_source"] == "Dice"
    assert fake_service.search_multi_args == (["python"], [], {"location": "Remote"})


def test_post_dice_search_accepts_singular_keyword_for_backward_compat(monkeypatch):
    fake_service = _FakeDiceService()
    client = _make_client(fake_service, monkeypatch)

    resp = client.post("/api/dice/search", json={"keyword": "python"})

    assert resp.status_code == 200
    assert fake_service.search_multi_args[0] == ["python"]


def test_post_dice_search_requires_keyword(monkeypatch):
    fake_service = _FakeDiceService()
    client = _make_client(fake_service, monkeypatch)

    resp = client.post("/api/dice/search", json={"location": "Remote"})

    assert resp.status_code == 422


def test_post_dice_search_runs_multiple_keywords_and_countries(monkeypatch):
    fake_service = _FakeDiceService()
    client = _make_client(fake_service, monkeypatch)

    resp = client.post("/api/dice/search", json={
        "keywords": ["python", "java"],
        "countries": ["United States", "Canada"],
    })

    assert resp.status_code == 200
    assert resp.json()["combos"] == 4
    assert fake_service.search_multi_args == (["python", "java"], ["United States", "Canada"], {})


def test_post_dice_search_rejects_too_many_combinations(monkeypatch):
    fake_service = _FakeDiceService()
    client = _make_client(fake_service, monkeypatch)

    resp = client.post("/api/dice/search", json={
        "keywords": ["a", "b", "c", "d"],
        "countries": ["US", "CA", "GB", "AU"],  # 4 x 4 = 16 > 15 cap
    })

    assert resp.status_code == 422
    assert fake_service.search_multi_args is None


def test_post_dice_search_returns_new_count_distinct_from_cumulative_total(monkeypatch):
    """The status note in the frontend needs the per-call count, not the cumulative
    total across all searches this process lifetime — new_count must reflect just
    what this call's search() returned."""
    fake_service = _FakeDiceService()
    # Simulate a service that already has accumulated results from a prior search.
    fake_service.results = [JobPosting(job_title="Old", company="Prev", lead_source="Dice")]
    client = _make_client(fake_service, monkeypatch)

    resp = client.post("/api/dice/search", json={"keyword": "python"})

    assert resp.status_code == 200
    body = resp.json()
    # fake_service.search_multi() replaces .results with a single new job and returns it
    assert body["new_count"] == 1
    assert body["total"] == 1


def test_post_dice_search_clamps_jobs_per_page_within_range(monkeypatch):
    fake_service = _FakeDiceService()
    client = _make_client(fake_service, monkeypatch)

    resp = client.post("/api/dice/search", json={"keyword": "python", "jobs_per_page": 500})

    assert resp.status_code == 200
    assert fake_service.search_multi_args == (["python"], [], {"jobs_per_page": 50})


def test_post_dice_search_clamps_jobs_per_page_minimum(monkeypatch):
    fake_service = _FakeDiceService()
    client = _make_client(fake_service, monkeypatch)

    resp = client.post("/api/dice/search", json={"keyword": "python", "jobs_per_page": -5})

    assert resp.status_code == 200
    assert fake_service.search_multi_args == (["python"], [], {"jobs_per_page": 1})


def test_post_dice_search_ignores_non_numeric_jobs_per_page(monkeypatch):
    fake_service = _FakeDiceService()
    client = _make_client(fake_service, monkeypatch)

    resp = client.post("/api/dice/search", json={"keyword": "python", "jobs_per_page": "not-a-number"})

    assert resp.status_code == 200
    assert "jobs_per_page" not in fake_service.search_multi_args[2]


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


def test_post_dice_search_stream_returns_sse_events(monkeypatch):
    fake_service = _FakeDiceService()
    client = _make_client(fake_service, monkeypatch)

    resp = client.post("/api/dice/search-stream", json={"keywords": ["python"], "location": "Remote"})

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    text = resp.text
    assert "data:" in text
    assert '"type": "start"' in text
    assert '"type": "complete"' in text

