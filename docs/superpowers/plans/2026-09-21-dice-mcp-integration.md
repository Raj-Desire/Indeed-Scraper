# Dice.com MCP Lead Source Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Dice.com as a third job-lead source in the dashboard, sourced via Dice's official public MCP server (no scraping), feeding the existing Azure AI Search KB matching → Azure OpenAI LLM scoring → SharePoint export pipeline.

**Architecture:** A new `DiceMCPClient` speaks JSON-RPC 2.0 over HTTP to `https://mcp.dice.com/mcp` (no auth) calling its `search_jobs` and `get_job_details` tools. Results map into the existing `JobPosting` model (which gains a new `lead_source` field). A new `DiceService` — simpler than `ScraperService` since a Dice search is one bounded request, not a long-running crawl — runs dedup + `MatchService` scoring on results and reuses `GraphSharePointExporter` for export unchanged (after a one-line fix so it stops hardcoding `"LeadSource": "Indeed"`). Three new API routes and a third dashboard tab reuse the existing job-card rendering.

**Tech Stack:** Python 3.14, FastAPI, httpx (async HTTP, already a dependency), Pydantic, pytest. No new dependencies.

**Spec:** [docs/superpowers/specs/2026-09-21-dice-mcp-integration-design.md](../specs/2026-09-21-dice-mcp-integration-design.md)

## Global Constraints

- No new third-party dependency for the MCP client — hand-roll JSON-RPC over `httpx` (project already uses `httpx` in `app/sharepoint/graph_exporter.py`).
- Dice MCP server endpoint: `https://mcp.dice.com/mcp`, no authentication.
- Every Dice search result is automatically scored via `MatchService` (confirmed decision — no per-job opt-in).
- Dice search is manual-trigger only (a search form + button) — no scheduler wiring in this phase.
- Any UI showing Dice results must display the AI-search disclosure line Dice's tool spec requires: "These job listings were found using AI-powered search. Please review all job details carefully and verify information directly with employers before applying."
- Follow existing code patterns: async service classes with a `get_x_service()` singleton accessor (see `app/services/scraper_service.py`), route handlers under `app/dashboard/router.py`, tests under `tests/` using plain `pytest` + `asyncio.run(...)` (see `tests/test_match_service.py`).

---

### Task 1: `JobPosting.lead_source` field + `graph_exporter` fix

**Files:**
- Modify: `app/models/job.py` (add field)
- Modify: `app/sharepoint/graph_exporter.py:551` (stop hardcoding)
- Test: `tests/test_lead_source_field.py` (new)

**Interfaces:**
- Produces: `JobPosting.lead_source: str` (default `"Indeed"`), read by `GraphSharePointExporter.export_jobs` and by later Dice mapping code.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_lead_source_field.py
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


if __name__ == "__main__":
    test_job_posting_lead_source_defaults_to_indeed()
    test_job_posting_lead_source_can_be_set_to_dice()
    print("OK")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_lead_source_field.py -v`
Expected: FAIL — `lead_source` is not a valid field on `JobPosting` (pydantic will raise or ignore depending on config; with `extra` not set to `"ignore"` at the model level for `JobPosting`, this raises `ValidationError` — confirm by reading the error, either way the assertion `job.lead_source == "Indeed"` fails with `AttributeError` if extra is silently dropped).

- [ ] **Step 3: Add the field to `JobPosting`**

In `app/models/job.py`, add alongside the other simple string fields (near `search_query`):

```python
    lead_source: str = Field(default="Indeed", description="Origin of this lead: Indeed, Dice, etc.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_lead_source_field.py -v`
Expected: PASS

- [ ] **Step 5: Fix `graph_exporter.py` to stop hardcoding `LeadSource`**

In `app/sharepoint/graph_exporter.py`, find the `job_dict` construction inside `export_jobs` (around line 551):

```python
                    "LeadSource": "Indeed",
```

Replace with:

```python
                    "LeadSource": job.lead_source or "Indeed",
```

- [ ] **Step 6: Add a regression test for the export mapping**

Append to `tests/test_lead_source_field.py`:

```python
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
```

- [ ] **Step 7: Run all tests in this file to verify they pass**

Run: `python -m pytest tests/test_lead_source_field.py -v`
Expected: PASS (3 passed)

- [ ] **Step 8: Commit**

```bash
git add app/models/job.py app/sharepoint/graph_exporter.py tests/test_lead_source_field.py
git commit -m "feat: add JobPosting.lead_source field, stop hardcoding LeadSource=Indeed in SharePoint export"
```

---

### Task 2: `DiceMCPClient` — JSON-RPC transport + `search_jobs`

**Files:**
- Create: `app/scraper/dice_mcp_client.py`
- Test: `tests/test_dice_mcp_client.py`

**Interfaces:**
- Consumes: `httpx.AsyncClient` (mocked in tests).
- Produces:
  - `class DiceMCPClient` with `__init__(self, base_url: str = "https://mcp.dice.com/mcp", timeout: float = 30.0)`
  - `async def search_jobs(self, keyword: str, **filters) -> list[dict]` — returns the raw list of job dicts from the tool's `data` field.
  - `async def get_job_details(self, job_id: str) -> dict` — returns `{"description": str, "skills": list[dict]}`.
  - `async def close(self) -> None`
  - Raises `DiceMCPError(Exception)` (defined in this module) on network failure, non-200 response, or a JSON-RPC `error` field in the response.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dice_mcp_client.py
"""Unit tests for DiceMCPClient (HTTP layer mocked)."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import pytest

from app.scraper.dice_mcp_client import DiceMCPClient, DiceMCPError


def _sse_body(payload: dict) -> str:
    """Format a JSON-RPC payload as the SSE body the Dice MCP server returns."""
    import json
    return f"event: message\ndata: {json.dumps(payload)}\n\n"


class _FakeResponse:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text

    def json(self):
        import json
        return json.loads(self.text)


class _FakeAsyncClient:
    """Records requests and returns pre-programmed responses in call order."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None, **kw):
        self.requests.append((url, headers, json))
        return self._responses.pop(0)

    async def aclose(self):
        pass


def _install_fake_client(monkeypatch, responses):
    fake = _FakeAsyncClient(responses)

    def _factory(*a, **kw):
        return fake

    monkeypatch.setattr("app.scraper.dice_mcp_client.httpx.AsyncClient", _factory)
    return fake


def test_search_jobs_returns_parsed_job_list(monkeypatch):
    init_resp = _FakeResponse(200, _sse_body({
        "jsonrpc": "2.0", "id": 1,
        "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "Job Search MCP Server"}},
    }))
    search_resp = _FakeResponse(200, _sse_body({
        "jsonrpc": "2.0", "id": 2,
        "result": {"content": [{"type": "text", "text": "{}"}],
                   "structuredContent": {"data": [{"guid": "abc123", "title": "Python Developer", "companyName": "Acme"}],
                                          "metadata": {"page": 1, "pageSize": 5, "total": 1}}},
    }))
    _install_fake_client(monkeypatch, [init_resp, search_resp])

    client = DiceMCPClient()
    results = asyncio.run(client.search_jobs(keyword="python"))

    assert results == [{"guid": "abc123", "title": "Python Developer", "companyName": "Acme"}]


def test_search_jobs_requires_keyword():
    client = DiceMCPClient()
    with pytest.raises(TypeError):
        asyncio.run(client.search_jobs())  # keyword is required, positional/keyword-only


def test_get_job_details_returns_description_and_skills(monkeypatch):
    init_resp = _FakeResponse(200, _sse_body({
        "jsonrpc": "2.0", "id": 1,
        "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "Job Search MCP Server"}},
    }))
    details_resp = _FakeResponse(200, _sse_body({
        "jsonrpc": "2.0", "id": 2,
        "result": {"content": [{"type": "text", "text": "{}"}],
                   "structuredContent": {"description": "Full JD text", "skills": [{"name": "Python"}, {"name": "AWS"}]}},
    }))
    _install_fake_client(monkeypatch, [init_resp, details_resp])

    client = DiceMCPClient()
    details = asyncio.run(client.get_job_details("abc123"))

    assert details["description"] == "Full JD text"
    assert details["skills"] == [{"name": "Python"}, {"name": "AWS"}]


def test_raises_dice_mcp_error_on_non_200(monkeypatch):
    init_resp = _FakeResponse(200, _sse_body({
        "jsonrpc": "2.0", "id": 1,
        "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "Job Search MCP Server"}},
    }))
    error_resp = _FakeResponse(500, "Internal Server Error")
    _install_fake_client(monkeypatch, [init_resp, error_resp])

    client = DiceMCPClient()
    with pytest.raises(DiceMCPError):
        asyncio.run(client.search_jobs(keyword="python"))


def test_raises_dice_mcp_error_on_jsonrpc_error_field(monkeypatch):
    init_resp = _FakeResponse(200, _sse_body({
        "jsonrpc": "2.0", "id": 1,
        "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "Job Search MCP Server"}},
    }))
    rpc_error_resp = _FakeResponse(200, _sse_body({
        "jsonrpc": "2.0", "id": 2,
        "error": {"code": -32602, "message": "Invalid params"},
    }))
    _install_fake_client(monkeypatch, [init_resp, rpc_error_resp])

    client = DiceMCPClient()
    with pytest.raises(DiceMCPError):
        asyncio.run(client.search_jobs(keyword="python"))


if __name__ == "__main__":
    print("Run with: python -m pytest tests/test_dice_mcp_client.py -v")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dice_mcp_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.scraper.dice_mcp_client'`

- [ ] **Step 3: Implement `DiceMCPClient`**

```python
# app/scraper/dice_mcp_client.py
"""
Dice.com MCP Client
====================
Minimal JSON-RPC 2.0 client for Dice's official public Model Context Protocol
server (https://mcp.dice.com/mcp). No authentication is required. The server
uses the "streamable HTTP" MCP transport: each POST returns a single
Server-Sent-Events chunk containing one JSON-RPC response.

This hand-rolls the two calls this project needs (initialize handshake +
tools/call) instead of taking a dependency on a general-purpose MCP SDK,
since the protocol surface used here is small and static.
"""

from __future__ import annotations

import itertools
import json
from typing import Any, Optional

import httpx

from app.utils.logger import logger

DICE_MCP_URL = "https://mcp.dice.com/mcp"


class DiceMCPError(Exception):
    """Raised when the Dice MCP server is unreachable or returns an error."""


class DiceMCPClient:
    """Thin async client for Dice's public MCP server."""

    def __init__(self, base_url: str = DICE_MCP_URL, timeout: float = 30.0) -> None:
        self._base_url = base_url
        self._timeout = timeout
        self._id_counter = itertools.count(1)
        self._initialized = False

    async def _post(self, payload: dict) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._base_url, headers=headers, json=payload)

        if resp.status_code != 200:
            raise DiceMCPError(f"Dice MCP server returned HTTP {resp.status_code}: {resp.text[:300]}")

        return self._parse_sse(resp.text)

    @staticmethod
    def _parse_sse(text: str) -> dict:
        """Extract the JSON-RPC payload from an SSE-formatted response body."""
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                raw = line[len("data:"):].strip()
                try:
                    return json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise DiceMCPError(f"Malformed JSON-RPC payload from Dice MCP server: {exc}") from exc
        raise DiceMCPError("No 'data:' line found in Dice MCP server response")

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        payload = {
            "jsonrpc": "2.0",
            "id": next(self._id_counter),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "indeed-scraper-dashboard", "version": "1.0"},
            },
        }
        response = await self._post(payload)
        if "error" in response:
            raise DiceMCPError(f"Dice MCP initialize failed: {response['error']}")
        self._initialized = True

    async def _call_tool(self, tool_name: str, arguments: dict) -> dict:
        await self._ensure_initialized()
        payload = {
            "jsonrpc": "2.0",
            "id": next(self._id_counter),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        response = await self._post(payload)
        if "error" in response:
            raise DiceMCPError(f"Dice MCP tool '{tool_name}' failed: {response['error']}")

        result = response.get("result", {})
        structured = result.get("structuredContent")
        if structured is None:
            raise DiceMCPError(f"Dice MCP tool '{tool_name}' returned no structuredContent")
        return structured

    async def search_jobs(self, *, keyword: str, **filters: Any) -> list[dict]:
        """Call the `search_jobs` tool. `filters` may include location, radius,
        radius_unit, jobs_per_page, page_number, sort, posted_date,
        workplace_types, employment_types, employer_types, willing_to_sponsor,
        easy_apply, company_name, fields, facets - any unset ones are omitted."""
        arguments = {"keyword": keyword, **{k: v for k, v in filters.items() if v is not None}}
        try:
            structured = await self._call_tool("search_jobs", arguments)
        except DiceMCPError:
            raise
        except Exception as exc:
            logger.error("Dice search_jobs failed for keyword '{}': {}", keyword, exc)
            raise DiceMCPError(str(exc)) from exc
        return structured.get("data") or []

    async def get_job_details(self, job_id: str) -> dict:
        """Call the `get_job_details` tool. Returns {"description": str, "skills": [...]}"""
        try:
            structured = await self._call_tool("get_job_details", {"job_id": job_id})
        except DiceMCPError:
            raise
        except Exception as exc:
            logger.error("Dice get_job_details failed for job_id '{}': {}", job_id, exc)
            raise DiceMCPError(str(exc)) from exc
        return {
            "description": structured.get("description") or "",
            "skills": structured.get("skills") or [],
        }

    async def close(self) -> None:
        """No persistent connection is held (a fresh httpx.AsyncClient is used per
        call), so this is a no-op kept for interface symmetry with other clients
        in this codebase (e.g. AzureSearchKnowledgeBase.close())."""
        return None
```

Note: `search_jobs` uses keyword-only `keyword` (`*, keyword: str`) so calling it with no arguments raises `TypeError`, matching the test in Step 1.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dice_mcp_client.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add app/scraper/dice_mcp_client.py tests/test_dice_mcp_client.py
git commit -m "feat: add DiceMCPClient for Dice's official public MCP server"
```

---

### Task 3: Map Dice results into `JobPosting`

**Files:**
- Modify: `app/scraper/dice_mcp_client.py` (add mapping function)
- Test: `tests/test_dice_mapping.py`

**Interfaces:**
- Consumes: `JobPosting` (Task 1, now has `lead_source`), raw dicts shaped like `DiceMCPClient.search_jobs()`/`get_job_details()` output.
- Produces: `map_to_job_posting(raw: dict, details: Optional[dict], search_query: str) -> JobPosting`, used by `DiceService` in Task 4.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dice_mapping.py
"""Unit tests for mapping raw Dice MCP job dicts into JobPosting."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.job import RemoteType
from app.scraper.dice_mcp_client import map_to_job_posting

RAW_JOB = {
    "guid": "abc-123",
    "title": "Senior Python Developer",
    "companyName": "Acme Tech",
    "jobLocation": {"displayName": "Remote"},
    "salary": "$120,000 - $150,000",
    "detailsPageUrl": "https://www.dice.com/job-detail/abc-123",
    "companyPageUrl": "https://www.dice.com/company/acme-tech",
    "postedDate": "2026-09-15T00:00:00Z",
    "workplaceTypes": ["Remote"],
    "isRemote": True,
    "employmentType": "FULLTIME",
}

DETAILS = {
    "description": "We need a Python developer with AWS experience.",
    "skills": [{"name": "Python"}, {"name": "AWS"}],
}


def test_maps_core_fields():
    job = map_to_job_posting(RAW_JOB, DETAILS, search_query="python developer")

    assert job.job_title == "Senior Python Developer"
    assert job.company == "Acme Tech"
    assert job.location == "Remote"
    assert job.salary_range == "$120,000 - $150,000"
    assert job.job_url == "https://www.dice.com/job-detail/abc-123"
    assert job.apply_url == "https://www.dice.com/job-detail/abc-123"
    assert job.job_description == "We need a Python developer with AWS experience."
    assert job.search_query == "python developer"
    assert job.lead_source == "Dice"


def test_maps_remote_type_from_workplace_types():
    job = map_to_job_posting(RAW_JOB, DETAILS, search_query="python developer")
    assert job.remote_type == RemoteType.FULLY_REMOTE


def test_maps_hybrid_workplace_type():
    raw = dict(RAW_JOB, workplaceTypes=["Hybrid"], isRemote=False)
    job = map_to_job_posting(raw, DETAILS, search_query="python developer")
    assert job.remote_type == RemoteType.HYBRID


def test_maps_onsite_workplace_type():
    raw = dict(RAW_JOB, workplaceTypes=["On-Site"], isRemote=False)
    job = map_to_job_posting(raw, DETAILS, search_query="python developer")
    assert job.remote_type == RemoteType.ON_SITE


def test_missing_workplace_types_defaults_to_unknown():
    raw = dict(RAW_JOB, workplaceTypes=None, isRemote=None)
    job = map_to_job_posting(raw, DETAILS, search_query="python developer")
    assert job.remote_type == RemoteType.UNKNOWN


def test_handles_missing_details_gracefully():
    """get_job_details can fail for an individual result; mapping must still
    succeed using only the search_jobs summary fields."""
    job = map_to_job_posting(RAW_JOB, None, search_query="python developer")
    assert job.job_description == ""
    assert job.job_title == "Senior Python Developer"


def test_handles_missing_optional_raw_fields():
    minimal_raw = {"guid": "x", "title": "Dev", "companyName": "Co"}
    job = map_to_job_posting(minimal_raw, None, search_query="dev")
    assert job.job_title == "Dev"
    assert job.company == "Co"
    assert job.location == ""
    assert job.salary_range == "Not listed"


if __name__ == "__main__":
    print("Run with: python -m pytest tests/test_dice_mapping.py -v")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dice_mapping.py -v`
Expected: FAIL with `ImportError: cannot import name 'map_to_job_posting'`

- [ ] **Step 3: Implement `map_to_job_posting`**

Append to `app/scraper/dice_mcp_client.py`:

```python
from app.models.job import JobPosting, RemoteType
from datetime import datetime


def _parse_workplace_type(raw: dict) -> RemoteType:
    workplace_types = raw.get("workplaceTypes") or []
    lowered = [str(w).lower() for w in workplace_types]
    if any("remote" in w for w in lowered) or raw.get("isRemote") is True:
        return RemoteType.FULLY_REMOTE
    if any("hybrid" in w for w in lowered):
        return RemoteType.HYBRID
    if any("site" in w for w in lowered):
        return RemoteType.ON_SITE
    return RemoteType.UNKNOWN


def _parse_posted_date(raw_value: Optional[str]) -> Optional[datetime]:
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def map_to_job_posting(raw: dict, details: Optional[dict], search_query: str) -> JobPosting:
    """Map a raw Dice `search_jobs` result (+ optional `get_job_details` result)
    into a JobPosting tagged lead_source="Dice"."""
    location = ((raw.get("jobLocation") or {}).get("displayName")) or ""
    details = details or {}
    posted_raw = raw.get("postedDate") or ""

    return JobPosting(
        job_title=raw.get("title") or "Untitled Role",
        company=raw.get("companyName") or "",
        location=location,
        search_query=search_query,
        remote_type=_parse_workplace_type(raw),
        salary_range=raw.get("salary") or "Not listed",
        posted_date_raw=posted_raw,
        posted_date=_parse_posted_date(posted_raw),
        job_url=raw.get("detailsPageUrl") or "",
        apply_url=raw.get("detailsPageUrl") or "",
        job_description=details.get("description") or "",
        has_full_description=bool(details.get("description")),
        lead_source="Dice",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dice_mapping.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add app/scraper/dice_mcp_client.py tests/test_dice_mapping.py
git commit -m "feat: map Dice MCP search results into JobPosting"
```

---

### Task 4: `DiceService` — search orchestration + scoring + SharePoint export

**Files:**
- Create: `app/services/dice_service.py`
- Test: `tests/test_dice_service.py`

**Interfaces:**
- Consumes: `DiceMCPClient` (Task 2), `map_to_job_posting` (Task 3), `DedupFilter` (existing, `app/filters/dedup_filter.py`), `MatchService` (existing, `app/matching/match_service.py`), `GraphSharePointExporter` (existing, `app/sharepoint/graph_exporter.py`).
- Produces:
  - `class DiceService` with:
    - `async def search(self, keyword: str, **filters) -> list[JobPosting]`
    - `def get_results(self) -> list[JobPosting]`
    - `def clear_results(self) -> None`
    - `async def export_sharepoint(self, selected_ids: Optional[list[str]] = None, owner: Optional[str] = None) -> int`
  - `def get_dice_service() -> DiceService` (module-level singleton accessor, same pattern as `get_scraper_service()`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dice_service.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dice_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.dice_service'`

- [ ] **Step 3: Implement `DiceService`**

```python
# app/services/dice_service.py
"""
Dice Search Orchestration Service
===================================
Wires DiceMCPClient -> job-detail enrichment -> Dedup -> KB/LLM matching ->
SharePoint export. Deliberately simpler than ScraperService: a Dice search is
one bounded request/response cycle, not a long-running cancellable crawl, so
there is no pause/resume/progress-broadcast machinery here.
"""

from __future__ import annotations

from typing import Optional

from app.filters.dedup_filter import DedupFilter
from app.matching.match_service import MatchService
from app.models.job import JobPosting
from app.scraper.dice_mcp_client import DiceMCPClient, DiceMCPError, map_to_job_posting
from app.utils.logger import logger


class DiceService:
    """Orchestrates Dice MCP search, matching, and SharePoint export."""

    def __init__(
        self,
        dice_client: Optional[DiceMCPClient] = None,
        match_service: Optional[MatchService] = None,
    ) -> None:
        self._dice_client = dice_client if dice_client is not None else DiceMCPClient()
        self._match_service = match_service if match_service is not None else MatchService()
        self._dedup_filter = DedupFilter()
        self._results: list[JobPosting] = []
        self._sharepoint_exporter = None  # lazily constructed in export_sharepoint

    async def search(self, keyword: str, **filters) -> list[JobPosting]:
        """Run a Dice search: fetch results, enrich with full descriptions,
        dedupe, score via MatchService, and store for later export."""
        try:
            raw_results = await self._dice_client.search_jobs(keyword=keyword, **filters)
        except DiceMCPError as exc:
            logger.error("Dice search failed for keyword '{}': {}", keyword, exc)
            raise

        mapped: list[JobPosting] = []
        for raw in raw_results:
            guid = raw.get("guid")
            details = None
            if guid:
                try:
                    details = await self._dice_client.get_job_details(guid)
                except DiceMCPError as exc:
                    logger.warning(
                        "Dice get_job_details failed for '{}' (continuing with summary only): {}",
                        guid, exc,
                    )
            mapped.append(map_to_job_posting(raw, details, search_query=keyword))

        deduped = self._dedup_filter.filter(mapped)

        for job in deduped:
            try:
                await self._match_service.evaluate_job(job)
            except Exception as match_err:
                logger.error("Dice job matching error for '{}': {}", job.job_title, match_err)

        self._results.extend(deduped)
        logger.info("Dice search '{}' added {} job(s) (total: {})", keyword, len(deduped), len(self._results))
        return deduped

    def get_results(self) -> list[JobPosting]:
        return list(self._results)

    def clear_results(self) -> None:
        self._results.clear()
        self._dedup_filter.reset()

    async def export_sharepoint(self, selected_ids: Optional[list[str]] = None, owner: Optional[str] = None) -> int:
        """Export current (or selected) Dice results to SharePoint via Graph API."""
        if self._sharepoint_exporter is None:
            from app.sharepoint.graph_exporter import GraphSharePointExporter
            self._sharepoint_exporter = GraphSharePointExporter()

        leads_to_export = self._results
        if selected_ids is not None:
            id_set = {str(i) for i in selected_ids}
            leads_to_export = [j for j in self._results if str(j.id) in id_set]

        return await self._sharepoint_exporter.export_jobs(leads_to_export, owner=owner)


_dice_service: Optional[DiceService] = None


def get_dice_service() -> DiceService:
    global _dice_service
    if _dice_service is None:
        _dice_service = DiceService()
    return _dice_service
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dice_service.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/dice_service.py tests/test_dice_service.py
git commit -m "feat: add DiceService orchestrating Dice MCP search, matching, and SharePoint export"
```

---

### Task 5: API routes for Dice search

**Files:**
- Modify: `app/dashboard/router.py` (add routes; reuse `_serialize_job`)
- Test: `tests/test_dice_routes.py`

**Interfaces:**
- Consumes: `get_dice_service()` (Task 4), `_serialize_job()` (existing, `app/dashboard/router.py:99`).
- Produces: `POST /api/dice/search`, `GET /api/dice/results`, `POST /api/dice/export/sharepoint`, `POST /api/dice/clear`.

- [ ] **Step 1: Add `lead_source` to `_serialize_job`**

In `app/dashboard/router.py`, in `_serialize_job` (around line 99-126), add one line to the returned dict (any position, e.g. right after `"role"`):

```python
        "lead_source": getattr(j, "lead_source", "Indeed"),
```

- [ ] **Step 2: Write the failing route tests**

```python
# tests/test_dice_routes.py
"""Integration tests for the /api/dice/* routes (DiceService mocked)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.models.job import JobPosting


def _make_client(fake_service):
    import app.dashboard.router as router_mod
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router_mod.router)
    router_mod.get_dice_service = lambda: fake_service
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


def test_post_dice_search_returns_serialized_jobs():
    fake_service = _FakeDiceService()
    client = _make_client(fake_service)

    resp = client.post("/api/dice/search", json={"keyword": "python", "location": "Remote"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["leads"][0]["job_title"] == "Python Dev"
    assert body["leads"][0]["lead_source"] == "Dice"
    assert fake_service.search_args == ("python", {"location": "Remote"})


def test_post_dice_search_requires_keyword():
    fake_service = _FakeDiceService()
    client = _make_client(fake_service)

    resp = client.post("/api/dice/search", json={"location": "Remote"})

    assert resp.status_code == 422


def test_get_dice_results():
    fake_service = _FakeDiceService()
    fake_service.results = [JobPosting(job_title="X", company="Y", lead_source="Dice")]
    client = _make_client(fake_service)

    resp = client.get("/api/dice/results")

    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_post_dice_clear():
    fake_service = _FakeDiceService()
    fake_service.results = [JobPosting(job_title="X", company="Y", lead_source="Dice")]
    client = _make_client(fake_service)

    resp = client.post("/api/dice/clear")

    assert resp.status_code == 200
    assert fake_service.cleared is True


def test_post_dice_export_sharepoint():
    fake_service = _FakeDiceService()
    fake_service.results = [JobPosting(job_title="X", company="Y", lead_source="Dice")]
    client = _make_client(fake_service)

    resp = client.post("/api/dice/export/sharepoint", json={"owner": "Meet"})

    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    assert fake_service.exported_with == (None, "Meet")


def test_post_dice_export_sharepoint_no_results_returns_400():
    fake_service = _FakeDiceService()
    client = _make_client(fake_service)

    resp = client.post("/api/dice/export/sharepoint", json={})

    assert resp.status_code == 400
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_dice_routes.py -v`
Expected: FAIL — `404` on all routes (not yet defined) / `ImportError` if `get_dice_service` doesn't exist in `router.py`'s namespace yet.

- [ ] **Step 4: Implement the routes**

In `app/dashboard/router.py`, add the import near the top (with the other service imports):

```python
from app.services.dice_service import get_dice_service
```

Add the route handlers near the end of the file, just before the `@router.websocket("/ws/progress")` handler:

```python
@router.post("/api/dice/search")
async def api_dice_search(request: Request):
    """Search Dice.com via its official MCP server, score results via the KB/LLM
    matching pipeline, and return them for display."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    keyword = (body.get("keyword") or "").strip()
    if not keyword:
        raise HTTPException(status_code=422, detail="keyword is required")

    filters = {
        k: v for k, v in {
            "location": body.get("location"),
            "radius": body.get("radius"),
            "radius_unit": body.get("radius_unit"),
            "workplace_types": body.get("workplace_types"),
            "employment_types": body.get("employment_types"),
            "posted_date": body.get("posted_date"),
            "easy_apply": body.get("easy_apply"),
            "willing_to_sponsor": body.get("willing_to_sponsor"),
            "jobs_per_page": body.get("jobs_per_page"),
        }.items() if v is not None
    }

    service = get_dice_service()
    try:
        await service.search(keyword, **filters)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Dice search failed: {exc}")

    leads = service.get_results()
    leads.sort(key=lambda j: (j.match_score is not None, j.match_score or 0), reverse=True)
    return {"total": len(leads), "leads": [_serialize_job(j) for j in leads]}


@router.get("/api/dice/results")
async def api_dice_results():
    """Return current Dice search results."""
    service = get_dice_service()
    leads = service.get_results()
    leads.sort(key=lambda j: (j.match_score is not None, j.match_score or 0), reverse=True)
    return {"total": len(leads), "leads": [_serialize_job(j) for j in leads]}


@router.post("/api/dice/clear")
async def api_dice_clear():
    """Clear all Dice search results from the dashboard."""
    service = get_dice_service()
    service.clear_results()
    return {"status": "cleared", "total": 0}


@router.post("/api/dice/export/sharepoint")
async def api_dice_export_sharepoint(request: Request):
    """Upload Dice job leads to SharePoint List via Graph API. Supports filtering
    by selected_ids."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    service = get_dice_service()
    leads = service.get_results()

    if not leads:
        raise HTTPException(status_code=400, detail="No Dice job leads to export. Run a search first.")

    selected_ids = body.get("selected_ids") if isinstance(body, dict) else None
    owner = body.get("owner") if isinstance(body, dict) else None

    try:
        inserted_count = await service.export_sharepoint(selected_ids=selected_ids, owner=owner)
        return {
            "status": "success",
            "message": f"Successfully exported {inserted_count} Dice jobs to SharePoint List via Microsoft Graph API!",
            "count": inserted_count,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"SharePoint Export Error: {str(exc)}")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_dice_routes.py -v`
Expected: PASS (6 passed)

Note: `test_post_dice_search_requires_keyword` expects FastAPI's own validation
via the route reading `body.get("keyword")` and manually raising 422 — confirm
the manual `raise HTTPException(status_code=422, ...)` in Step 4 covers this
(it does, since `keyword` is read from the raw JSON body, not a Pydantic
model field).

- [ ] **Step 6: Commit**

```bash
git add app/dashboard/router.py tests/test_dice_routes.py
git commit -m "feat: add /api/dice/* routes for search, results, clear, and SharePoint export"
```

---

### Task 6: Dashboard UI — Dice search tab

**Files:**
- Modify: `templates/index.html`

**Interfaces:**
- Consumes: `/api/dice/search`, `/api/dice/results`, `/api/dice/clear`, `/api/dice/export/sharepoint` (Task 5), and the existing job-card rendering JS already used for `panel-scraper`/`panel-manual` results.

- [ ] **Step 1: Read the existing tab structure to find the exact insertion points**

Before editing, open `templates/index.html` and locate:
1. The tab button bar (around lines 20-30, `tab-btn-scraper` / `tab-btn-manual`).
2. The `switchMode(mode)` JS function definition (search the file for `function switchMode`).
3. The `panel-manual` div (~line 226) to copy its structural pattern (form container, hidden by default via `class="... hidden"`).
4. The job-results rendering function (search for where `panel-scraper` or `panel-manual` results get rendered into DOM — likely a function like `renderLeads(leads)` or similar, shared across modes). Confirm whether it's already source-agnostic (keyed off `job.id`/`job.job_title` etc., not hardcoded to Indeed) — the design assumes it is generalizable; if it hardcodes Indeed-specific copy, note the exact lines that need a source-conditional (e.g. a `Dice` badge) rather than a full rewrite.

- [ ] **Step 2: Add the tab button**

Add a third button next to the existing two (same pattern as `tab-btn-manual`):

```html
<button id="tab-btn-dice" type="button" onclick="switchMode('dice')"
        class="tab-btn ...">
    Dice Search
</button>
```

(Match the exact class list used by `tab-btn-manual` for visual consistency — read it from the file rather than guessing, since Tailwind utility classes are specific to this project's design.)

- [ ] **Step 3: Add the `panel-dice` panel**

Add a new `<div id="panel-dice" class="space-y-5 hidden">` following the structural pattern of `panel-manual`, containing:
- A form with: `dice-keyword` (text input, required), `dice-location` (text input), workplace-type checkboxes (`Remote`/`On-Site`/`Hybrid`), employment-type select, posted-date select (`ONE`/`THREE`/`SEVEN`/any), `dice-easy-apply` checkbox, `dice-willing-to-sponsor` checkbox, and a "Search Dice" submit button.
- A one-line disclosure banner above the results area:
  `<p class="text-xs text-slate-500">These job listings were found using AI-powered search. Please review all job details carefully and verify information directly with employers before applying.</p>`
- A results container (`id="dice-results"`) that the JS below populates using the same rendering function used by the other panels.

- [ ] **Step 4: Extend `switchMode()` to handle `'dice'`**

Update the `switchMode(mode)` function to show/hide `panel-dice` alongside the existing panels and toggle `tab-btn-dice`'s active styling, following the exact same conditional pattern already used for `'manual'`.

- [ ] **Step 5: Add the search handler JS**

```javascript
async function searchDice(event) {
    event.preventDefault();
    const keyword = document.getElementById('dice-keyword').value.trim();
    if (!keyword) return;

    const payload = {
        keyword,
        location: document.getElementById('dice-location').value.trim() || null,
        workplace_types: getCheckedValues('dice-workplace-types'),  // returns [] if none checked
        easy_apply: document.getElementById('dice-easy-apply').checked || null,
        willing_to_sponsor: document.getElementById('dice-willing-to-sponsor').checked || null,
    };

    const resp = await fetch('/api/dice/search', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
    });

    if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        showError(err.detail || 'Dice search failed.');  // reuse existing error-toast helper
        return;
    }

    const data = await resp.json();
    renderLeads(data.leads, 'dice-results');  // reuse the existing shared render function
}
```

Wire `searchDice` to the form's `onsubmit` in the `panel-dice` markup added in Step 3. Adapt `getCheckedValues`/`showError`/`renderLeads` calls to whatever the existing shared helper function names actually are in this file (found during Step 1) rather than inventing new ones.

- [ ] **Step 6: Manual verification**

Run: `python main.py` (or however the project's dev server is normally started — check `README.md`/`DEVELOPER_GUIDE.md` if `python main.py` isn't it), then in a browser:
1. Open the dashboard, click "Dice Search" tab — confirm `panel-dice` shows and the other two panels hide.
2. Enter a keyword (e.g. "python developer"), click Search — confirm results render with match scores and the AI-disclosure line is visible.
3. Click "Save to SharePoint" on a result (or the batch export action) — confirm the SharePoint list receives the row with `LeadSource = Dice` (check via the SharePoint site or Graph Explorer).
4. Switch back to the Indeed tab, run a scrape, confirm those results still export with `LeadSource = Indeed` (regression check for Task 1's change).

- [ ] **Step 7: Commit**

```bash
git add templates/index.html
git commit -m "feat: add Dice Search dashboard tab reusing existing job-card rendering"
```

---

### Task 7: Full test suite regression check

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass, including every test added in Tasks 1-5 and all pre-existing tests (confirms the `graph_exporter.py` and `router.py` changes didn't break the Indeed/manual flows).

- [ ] **Step 2: If anything fails, fix and re-run**

Common risk points to check first if a pre-existing test fails:
- `graph_exporter.py` tests (`tests/test_sharepoint_opportunity_tracker.py`) — confirm they don't assert the literal string `"Indeed"` for `LeadSource` in a way that's now broken by reading `job.lead_source` (they shouldn't, since `lead_source` defaults to `"Indeed"`, but verify).
- `router.py` tests, if any exist for `_serialize_job`, adjusted for the new `lead_source` key in the response dict.

- [ ] **Step 3: Commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: address regressions found in full test suite run"
```

(Skip this commit if Step 1 passed clean.)

---

## Post-Implementation Roadmap (beyond this plan)

Captured from the design's "Out of scope" section, for future phases:

1. **Scheduled Dice searches** — reuse `config/schedule.json` + the existing scheduler (`app/scheduler/`) to run a fixed list of Dice keyword searches automatically, mirroring the Indeed automated flow. Natural follow-up once the manual flow is validated in production.
2. **Cost-aware scoring** — if Azure OpenAI cost becomes a concern at higher Dice search volume, add the "user selects which results to score" mode considered and deferred during brainstorming.
3. **Company enrichment** — wire up Dice's `get_company` tool (already covered by `DiceMCPClient`'s design, just not implemented in Task 2 since it wasn't needed for scoring/export) to enrich outreach-generation context.
4. **Excel export for Dice results** — `ExcelExporter` already works on any `list[JobPosting]`; a `GET /api/dice/export/excel` route mirroring the existing Indeed one is a small addition if requested.
5. **Unified "all sources" view** — once Dice is live, consider a combined leads view across Indeed + Dice + manual, sortable/filterable by `lead_source`, instead of three separate result panels.
