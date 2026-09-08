"""Unit tests for Azure AI Search KB retrieval (client is faked - no network calls)."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.knowledge_base.azure_search import AzureSearchKnowledgeBase
from app.knowledge_base.models import RetrievedChunk


class _FakeAsyncIterator:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


class _FakeSearchClient:
    """Stands in for azure.search.documents.aio.SearchClient."""

    def __init__(self, docs):
        self._docs = docs
        self.closed = False

    async def search(self, **kwargs):
        return _FakeAsyncIterator(self._docs)

    async def close(self):
        self.closed = True


def test_search_returns_retrieved_chunks_from_fake_client():
    docs = [
        {"chunk_id": "c1", "parent_id": "p1", "title": "SharePoint Migration", "chunk": "We led a SPFx migration...", "@search.score": 0.83},
        {"chunk_id": "c2", "parent_id": "p1", "title": "Power BI Dashboards", "chunk": "Built Power BI reporting...", "@search.score": 0.71},
    ]
    fake_client = _FakeSearchClient(docs)
    kb = AzureSearchKnowledgeBase(client=fake_client, enabled=True, top_k=5)

    results = asyncio.run(kb.search("Looking for a SharePoint SPFx developer"))

    assert len(results) == 2
    assert all(isinstance(r, RetrievedChunk) for r in results)
    assert results[0].chunk_id == "c1"
    assert results[0].title == "SharePoint Migration"
    assert results[0].score == 0.83


def test_search_returns_empty_list_when_not_configured():
    kb = AzureSearchKnowledgeBase(client=None, enabled=False, top_k=5)
    results = asyncio.run(kb.search("anything"))
    assert results == []


def test_search_swallows_client_errors():
    class _BoomClient:
        async def search(self, **kwargs):
            raise RuntimeError("service unavailable")

        async def close(self):
            pass

    kb = AzureSearchKnowledgeBase(client=_BoomClient(), enabled=True, top_k=5)
    results = asyncio.run(kb.search("anything"))
    assert results == []


if __name__ == "__main__":
    test_search_returns_retrieved_chunks_from_fake_client()
    test_search_returns_empty_list_when_not_configured()
    test_search_swallows_client_errors()
    print("OK")
