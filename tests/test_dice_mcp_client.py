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
