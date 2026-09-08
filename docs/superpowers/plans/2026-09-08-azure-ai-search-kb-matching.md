# Azure AI Search Knowledge-Base Job Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing Azure AI Search knowledge-base index (`rag-1776073601315`) into the Indeed scraper so every scraped `JobPosting` is enriched with an LLM-produced `match_score`, `matched_skills`, `missing_skills`, and `match_reason`, without touching the scraping/parsing/UI/export code paths beyond the minimum required to carry the new fields.

**Architecture:** Two new, independent packages — `app/knowledge_base/` (Azure AI Search hybrid retrieval, reusing the index's existing Azure OpenAI vectorizer via `VectorizableTextQuery` so no separate embedding client is needed) and `app/matching/` (Azure OpenAI chat-completion LLM evaluator that turns a job description + retrieved chunks into a structured match verdict). A thin `MatchService` in `app/matching/match_service.py` composes the two and is called once per scraped job from `ScraperService._run_pipeline`, after the existing date/dedup filters and before results are appended — mirroring how SharePoint auto-sync already hooks into that same method. Both stages fail soft (log + safe defaults) so a missing/unavailable Azure Search or Azure OpenAI credential never crashes a scraping run.

**Tech Stack:** `azure-search-documents` (async `SearchClient`, `VectorizableTextQuery` for integrated vectorization), `openai` (`AsyncAzureOpenAI` chat completions with `response_format={"type": "json_object"}`), existing `pydantic` / `pydantic-settings` / `loguru` stack.

**Spec:** User request in conversation (2026-09-08) — see "Requirements" list embedded below; no separate spec file exists.

## Global Constraints

- No ChromaDB code exists anywhere in the current `Azure-AI-Endpoint` branch tree (verified: zero matches for `chroma|Chroma|CHROMA` in any `.py`, `requirements.txt`, `.env`, or `.env.example`). Requirement "remove ChromaDB" is a no-op beyond deleting the stale `app/knowledge_base/__pycache__/` directory (Task 8) — do not invent ChromaDB code to then remove.
- Do NOT create a new vector index, new vector DB, or local copy of the knowledge base. Only connect to the existing index `rag-1776073601315` via `AZURE_SEARCH_ENDPOINT` / `AZURE_SEARCH_INDEX`.
- Do NOT treat the Azure Search `@search.score` as the final match score — it is stored only as `RetrievedChunk.score` (informational) and is never copied into `JobPosting.match_score`. Only the LLM's structured output sets `match_score`.
- Retrieval (`app/knowledge_base/`) and LLM evaluation (`app/matching/`) must stay in separate modules/classes — `MatchService` composes them, neither imports the other.
- Every new external call (Azure Search, Azure OpenAI) must be wrapped so failures are logged via `app.utils.logger.logger` and degrade to safe defaults — never raise out of `MatchService.evaluate_job()`.
- No hardcoded credentials anywhere — all Azure config comes from `app/config/settings.py` (`Settings`, sourced from `.env`).
- Do not modify `app/scraper/indeed_scraper.py`, `app/parser/*`, `app/dashboard/*`, `templates/*`, `static/*`, or `app/filters/*` — none of them need to change for this feature.
- Existing tests (`tests/test_field_parity.py`) must still pass unmodified after all tasks.

---

## Requirements Traceability

| # | Requirement (paraphrased) | Task |
|---|---|---|
| 2 | Remove ChromaDB remnants | Task 8 |
| 4 | New `app/knowledge_base/azure_search.py` service | Task 2 |
| 5 | Connect to index `rag-1776073601315` | Task 1, 2 |
| 6 | Reuse existing vectorizer, no new vector DB | Task 2 |
| 7-8 | Retrieve chunks for a job description, return chunk/title/metadata | Task 2 |
| 9 | Hybrid (text + vector) retrieval | Task 2 |
| 10 | Search score != final match score | Task 2, 3 |
| 11-13 | LLM layer produces match_score/matched_skills/missing_skills/match_reason; add to `JobPosting` if missing | Task 3, 4, 5 |
| 14 | Retrieval and LLM evaluation kept separate | Task 2, 3, 4 |
| 15 | Graceful error handling, no crash | Task 2, 3, 4, 7 |
| 16 | Credentials via env vars only | Task 1 |
| 17 | Update `requirements.txt` | Task 1 |
| 18 | Update `.env.example` | Task 1 |
| 19 | Debug script, top-5 chunks | Task 9 |
| 20-21 | No new ingestion pipeline, no local KB copy | (design constraint, N/A task) |

---

### Task 1: Azure configuration (Settings, `.env.example`, `requirements.txt`)

**Files:**
- Modify: `app/config/settings.py:42-51` (insert new fields after the SharePoint block)
- Modify: `.env.example`
- Modify: `requirements.txt`
- Test: `tests/test_settings_azure_kb.py`

**Interfaces:**
- Produces: `Settings.azure_search_endpoint: str`, `Settings.azure_search_index: str`, `Settings.azure_search_api_key: str`, `Settings.azure_search_top_k: int`, `Settings.azure_openai_endpoint: str`, `Settings.azure_openai_api_key: str`, `Settings.azure_openai_api_version: str`, `Settings.azure_openai_chat_deployment: str`, `Settings.enable_kb_matching: bool` — all consumed by Tasks 2, 3, 4, 7.

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings_azure_kb.py`:

```python
"""Tests that new Azure Search / Azure OpenAI settings load with safe defaults."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import Settings


def test_azure_kb_settings_have_safe_defaults():
    s = Settings(_env_file=None)  # ignore local .env so defaults are exercised
    assert s.azure_search_endpoint == ""
    assert s.azure_search_index == ""
    assert s.azure_search_api_key == ""
    assert s.azure_search_top_k == 5
    assert s.azure_openai_endpoint == ""
    assert s.azure_openai_api_key == ""
    assert s.azure_openai_api_version == "2024-06-01"
    assert s.azure_openai_chat_deployment == ""
    assert s.enable_kb_matching is True


if __name__ == "__main__":
    test_azure_kb_settings_have_safe_defaults()
    print("OK")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_settings_azure_kb.py -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'azure_search_endpoint'`

- [ ] **Step 3: Add the new fields to `Settings`**

In `app/config/settings.py`, after line 51 (`sharepoint_auto_sync: bool = ...`) and before the `# Directories` comment (line 53), insert:

```python
    # Azure AI Search (existing company knowledge-base index)
    azure_search_endpoint: str = Field(default="", description="Azure AI Search service endpoint URL")
    azure_search_index: str = Field(default="", description="Azure AI Search index name (existing KB index)")
    azure_search_api_key: str = Field(default="", description="Azure AI Search admin/query API key")
    azure_search_top_k: int = Field(default=5, description="Number of KB chunks to retrieve per job")

    # Azure OpenAI (LLM job-match evaluation)
    azure_openai_endpoint: str = Field(default="", description="Azure OpenAI endpoint URL")
    azure_openai_api_key: str = Field(default="", description="Azure OpenAI API key")
    azure_openai_api_version: str = Field(default="2024-06-01", description="Azure OpenAI REST API version")
    azure_openai_chat_deployment: str = Field(default="", description="Azure OpenAI chat deployment name used for match evaluation")

    # Knowledge-base matching toggle
    enable_kb_matching: bool = Field(default=True, description="Enrich scraped jobs with Azure KB retrieval + LLM match scoring")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_settings_azure_kb.py -v`
Expected: PASS

- [ ] **Step 5: Update `.env.example`**

Append to the end of `.env.example` (after the `SHAREPOINT_AUTO_SYNC` line), matching the existing key-name style:

```
# Azure AI Search (existing company knowledge-base index — do not create a new index)
AZURE_SEARCH_ENDPOINT=https://your-search-service.search.windows.net
AZURE_SEARCH_INDEX=your-existing-index-name
AZURE_SEARCH_API_KEY=your-azure-search-api-key-here
AZURE_SEARCH_TOP_K=5

# Azure OpenAI (LLM job-match evaluation)
AZURE_OPENAI_ENDPOINT=https://your-openai-resource.openai.azure.com
AZURE_OPENAI_API_KEY=your-azure-openai-api-key-here
AZURE_OPENAI_API_VERSION=2024-06-01
AZURE_OPENAI_CHAT_DEPLOYMENT=your-chat-deployment-name

# Knowledge-base matching toggle
ENABLE_KB_MATCHING=true
```

- [ ] **Step 6: Update `requirements.txt`**

Add a new section after `# Configuration & validation` block (or any consistent spot) in `requirements.txt`:

```
# Azure AI Search & Azure OpenAI (knowledge-base job matching)
azure-search-documents>=11.5.1
openai>=1.30.0
```

- [ ] **Step 7: Install the new dependencies locally**

Run: `python -m pip install azure-search-documents>=11.5.1 openai>=1.30.0`
Expected: both packages install without error (needed for Tasks 2-4 imports to resolve).

- [ ] **Step 8: Commit**

```bash
git add app/config/settings.py .env.example requirements.txt tests/test_settings_azure_kb.py
git commit -m "feat: add Azure AI Search + Azure OpenAI configuration settings"
```

---

### Task 2: Knowledge-base retrieval service (`app/knowledge_base/`)

**Files:**
- Create: `app/knowledge_base/__init__.py`
- Create: `app/knowledge_base/models.py`
- Create: `app/knowledge_base/azure_search.py`
- Test: `tests/test_azure_search_kb.py`

**Interfaces:**
- Consumes: `Settings.azure_search_endpoint/index/api_key/top_k` (Task 1).
- Produces: `RetrievedChunk` (fields: `chunk_id: str`, `parent_id: str`, `title: str`, `chunk: str`, `score: float`), `AzureSearchKnowledgeBase(client=None)` with `async def search(self, query_text: str, top_k: int | None = None) -> list[RetrievedChunk]` and `async def close(self) -> None` — consumed by Task 4 (`MatchService`) and Task 9 (debug script).

- [ ] **Step 1: Write the failing test**

Create `tests/test_azure_search_kb.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_azure_search_kb.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.knowledge_base.azure_search'`

- [ ] **Step 3: Create `app/knowledge_base/__init__.py`**

```python
"""Azure AI Search knowledge-base retrieval package."""
```

- [ ] **Step 4: Create `app/knowledge_base/models.py`**

```python
"""
Knowledge-base retrieval result model.
"""

from pydantic import BaseModel, Field


class RetrievedChunk(BaseModel):
    """One company-knowledge chunk retrieved from Azure AI Search."""

    chunk_id: str = Field(default="", description="Azure AI Search document id (chunk_id field)")
    parent_id: str = Field(default="", description="Parent document id this chunk belongs to")
    title: str = Field(default="", description="Source document title")
    chunk: str = Field(default="", description="The retrieved text chunk")
    score: float = Field(
        default=0.0,
        description="Azure AI Search relevance score - informational only, never the final job match score",
    )
```

- [ ] **Step 5: Create `app/knowledge_base/azure_search.py`**

```python
"""
Azure AI Search Knowledge Base Retrieval
=========================================
Connects to the existing Azure AI Search index (AZURE_SEARCH_INDEX) to retrieve
company-knowledge chunks relevant to a cleaned Indeed job description.

Uses the index's existing Azure OpenAI vectorizer (text-embedding-3-small) via
VectorizableTextQuery, so this service never computes its own embeddings and
never creates a second vector store.
"""

from __future__ import annotations

from typing import Optional

from app.config.settings import get_settings
from app.knowledge_base.models import RetrievedChunk
from app.utils.logger import logger


class AzureSearchKnowledgeBase:
    """Hybrid (full-text + vector) retrieval against the existing Azure AI Search KB index."""

    def __init__(self, client=None, enabled: Optional[bool] = None, top_k: Optional[int] = None) -> None:
        """
        Args:
            client: Optional pre-built azure.search.documents.aio.SearchClient, for tests.
                    When omitted, a real client is built from Settings.
            enabled: Override for whether retrieval is active (tests only).
            top_k: Override for the default number of chunks to retrieve (tests only).
        """
        settings = get_settings()
        self._top_k = top_k if top_k is not None else settings.azure_search_top_k

        if client is not None:
            self._client = client
            self._enabled = True if enabled is None else enabled
            return

        self._enabled = bool(
            settings.azure_search_endpoint and settings.azure_search_api_key and settings.azure_search_index
        )
        self._client = None
        if not self._enabled:
            logger.warning(
                "Azure AI Search is not fully configured (endpoint/api key/index) - KB retrieval disabled."
            )
            return

        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents.aio import SearchClient

        self._client = SearchClient(
            endpoint=settings.azure_search_endpoint,
            index_name=settings.azure_search_index,
            credential=AzureKeyCredential(settings.azure_search_api_key),
        )

    async def search(self, query_text: str, top_k: Optional[int] = None) -> list[RetrievedChunk]:
        """Retrieve the most relevant company-knowledge chunks for a job description.

        Never raises: any Azure Search failure is logged and results in an empty list
        so scraping/matching can continue without the run crashing.
        """
        if not self._enabled or not self._client or not query_text.strip():
            return []

        k = top_k or self._top_k
        try:
            from azure.search.documents.models import VectorizableTextQuery

            vector_query = VectorizableTextQuery(text=query_text, k_nearest_neighbors=k, fields="text_vector")
            results = await self._client.search(
                search_text=query_text,
                vector_queries=[vector_query],
                select=["chunk_id", "parent_id", "title", "chunk"],
                top=k,
            )

            chunks: list[RetrievedChunk] = []
            async for result in results:
                chunks.append(
                    RetrievedChunk(
                        chunk_id=result.get("chunk_id", ""),
                        parent_id=result.get("parent_id", ""),
                        title=result.get("title", ""),
                        chunk=result.get("chunk", ""),
                        score=float(result.get("@search.score", 0.0) or 0.0),
                    )
                )
            return chunks
        except Exception as exc:
            logger.error("Azure AI Search retrieval failed: {}", exc)
            return []

    async def close(self) -> None:
        if self._client and hasattr(self._client, "close"):
            try:
                await self._client.close()
            except Exception as exc:
                logger.error("Error closing Azure Search client: {}", exc)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_azure_search_kb.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add app/knowledge_base/__init__.py app/knowledge_base/models.py app/knowledge_base/azure_search.py tests/test_azure_search_kb.py
git commit -m "feat: add Azure AI Search knowledge-base retrieval service"
```

---

### Task 3: LLM match evaluation service (`app/matching/`)

**Files:**
- Create: `app/matching/__init__.py`
- Create: `app/matching/models.py`
- Create: `app/matching/llm_matcher.py`
- Test: `tests/test_llm_matcher.py`

**Interfaces:**
- Consumes: `RetrievedChunk` (Task 2), `Settings.azure_openai_*` (Task 1).
- Produces: `MatchResult` (fields: `match_score: int`, `matched_skills: list[str]`, `missing_skills: list[str]`, `match_reason: str`), `LLMMatcher(client=None)` with `async def evaluate(self, job_description: str, kb_chunks: list[RetrievedChunk]) -> MatchResult` and `async def close(self) -> None` — consumed by Task 4.

- [ ] **Step 1: Write the failing test**

Create `tests/test_llm_matcher.py`:

```python
"""Unit tests for the LLM job-match evaluator (Azure OpenAI client is faked)."""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.knowledge_base.models import RetrievedChunk
from app.matching.llm_matcher import LLMMatcher
from app.matching.models import MatchResult


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeCompletionResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content):
        self._content = content

    async def create(self, **kwargs):
        return _FakeCompletionResponse(self._content)


class _FakeChat:
    def __init__(self, content):
        self.completions = _FakeCompletions(content)


class _FakeAzureOpenAIClient:
    def __init__(self, content):
        self.chat = _FakeChat(content)
        self.closed = False

    async def close(self):
        self.closed = True


def test_evaluate_parses_structured_json_response():
    payload = json.dumps({
        "match_score": 82,
        "matched_skills": ["SharePoint", "SPFx", "Power BI"],
        "missing_skills": ["Dynamics 365"],
        "match_reason": "Strong SharePoint/SPFx overlap, no Dynamics 365 experience found.",
    })
    fake_client = _FakeAzureOpenAIClient(payload)
    matcher = LLMMatcher(client=fake_client, enabled=True, deployment="test-deployment")

    chunks = [RetrievedChunk(chunk_id="c1", parent_id="p1", title="SPFx Projects", chunk="Built SPFx web parts...", score=0.8)]
    result = asyncio.run(matcher.evaluate("Looking for a SharePoint SPFx + Power BI developer", chunks))

    assert isinstance(result, MatchResult)
    assert result.match_score == 82
    assert "SPFx" in result.matched_skills
    assert "Dynamics 365" in result.missing_skills
    assert "SharePoint" in result.match_reason or "Power BI" in result.match_reason or result.match_reason


def test_evaluate_returns_disabled_default_when_not_configured():
    matcher = LLMMatcher(client=None, enabled=False, deployment="")
    result = asyncio.run(matcher.evaluate("some job description", []))
    assert result.match_score == 0
    assert result.matched_skills == []
    assert result.missing_skills == []
    assert result.match_reason


def test_evaluate_swallows_client_errors():
    class _BoomChat:
        class completions:
            @staticmethod
            async def create(**kwargs):
                raise RuntimeError("rate limited")

    class _BoomClient:
        chat = _BoomChat()

        async def close(self):
            pass

    matcher = LLMMatcher(client=_BoomClient(), enabled=True, deployment="test-deployment")
    result = asyncio.run(matcher.evaluate("some job description", []))
    assert result.match_score == 0
    assert "failed" in result.match_reason.lower() or "rate limited" in result.match_reason.lower()


if __name__ == "__main__":
    test_evaluate_parses_structured_json_response()
    test_evaluate_returns_disabled_default_when_not_configured()
    test_evaluate_swallows_client_errors()
    print("OK")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_llm_matcher.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.matching'`

- [ ] **Step 3: Create `app/matching/__init__.py`**

```python
"""LLM-based job-to-company match evaluation package."""
```

- [ ] **Step 4: Create `app/matching/models.py`**

```python
"""
Structured LLM match-evaluation result.
"""

from pydantic import BaseModel, Field


class MatchResult(BaseModel):
    """Structured output of the LLM job-match evaluation."""

    match_score: int = Field(default=0, ge=0, le=100, description="LLM-judged match score, 0-100")
    matched_skills: list[str] = Field(default_factory=list, description="Skills/technologies the company can demonstrate for this job")
    missing_skills: list[str] = Field(default_factory=list, description="Skills/technologies the job requires but the KB shows no evidence of")
    match_reason: str = Field(default="", description="Short explanation of the score")
```

- [ ] **Step 5: Create `app/matching/llm_matcher.py`**

```python
"""
LLM Job-Match Evaluation
========================
Takes a cleaned Indeed job description plus company-knowledge chunks retrieved
from Azure AI Search (app.knowledge_base.azure_search) and asks an Azure OpenAI
chat deployment to produce a structured match verdict.

The Azure AI Search relevance score is never used as the final match score -
only this LLM's structured judgement sets JobPosting.match_score.
"""

from __future__ import annotations

import json
from typing import Optional

from app.config.settings import get_settings
from app.knowledge_base.models import RetrievedChunk
from app.matching.models import MatchResult
from app.utils.logger import logger

_SYSTEM_PROMPT = (
    "You are a recruiting analyst. Given a job description and excerpts from the "
    "company's own capability/experience knowledge base, judge how well the company's "
    "demonstrated experience matches the job's required technologies and responsibilities "
    "(pay close attention to exact technology names such as SharePoint, SPFx, Power BI, "
    "Power Apps, Dynamics 365, Azure, RAG, Python). "
    "Respond ONLY with a JSON object with keys: "
    "match_score (integer 0-100), matched_skills (array of strings), "
    "missing_skills (array of strings), match_reason (short string)."
)


class LLMMatcher:
    """Evaluates job-to-company fit using an Azure OpenAI chat deployment."""

    def __init__(self, client=None, enabled: Optional[bool] = None, deployment: Optional[str] = None) -> None:
        """
        Args:
            client: Optional pre-built openai.AsyncAzureOpenAI client, for tests.
            enabled: Override for whether evaluation is active (tests only).
            deployment: Override for the chat deployment name (tests only).
        """
        settings = get_settings()
        self._deployment = deployment if deployment is not None else settings.azure_openai_chat_deployment

        if client is not None:
            self._client = client
            self._enabled = True if enabled is None else enabled
            return

        self._enabled = bool(
            settings.azure_openai_endpoint and settings.azure_openai_api_key and settings.azure_openai_chat_deployment
        )
        self._client = None
        if not self._enabled:
            logger.warning(
                "Azure OpenAI is not fully configured (endpoint/api key/deployment) - LLM matching disabled."
            )
            return

        from openai import AsyncAzureOpenAI

        self._client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )

    async def evaluate(self, job_description: str, kb_chunks: list[RetrievedChunk]) -> MatchResult:
        """Return a structured match result. Never raises - any failure yields a safe default."""
        if not self._enabled or not self._client:
            return MatchResult(match_score=0, matched_skills=[], missing_skills=[], match_reason="LLM matching not configured")

        context = "\n\n".join(f"[{c.title}] {c.chunk}" for c in kb_chunks) or "No company knowledge retrieved."
        user_prompt = f"JOB DESCRIPTION:\n{job_description}\n\nCOMPANY KNOWLEDGE BASE EXCERPTS:\n{context}"

        try:
            response = await self._client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            payload = json.loads(response.choices[0].message.content)
            return MatchResult(
                match_score=int(payload.get("match_score", 0)),
                matched_skills=[str(s) for s in payload.get("matched_skills", [])],
                missing_skills=[str(s) for s in payload.get("missing_skills", [])],
                match_reason=str(payload.get("match_reason", "")),
            )
        except Exception as exc:
            logger.error("LLM match evaluation failed: {}", exc)
            return MatchResult(match_score=0, matched_skills=[], missing_skills=[], match_reason=f"Evaluation failed: {exc}")

    async def close(self) -> None:
        if self._client and hasattr(self._client, "close"):
            try:
                await self._client.close()
            except Exception as exc:
                logger.error("Error closing Azure OpenAI client: {}", exc)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_llm_matcher.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add app/matching/__init__.py app/matching/models.py app/matching/llm_matcher.py tests/test_llm_matcher.py
git commit -m "feat: add Azure OpenAI LLM job-match evaluation service"
```

---

### Task 4: Match orchestrator (`MatchService`)

**Files:**
- Create: `app/matching/match_service.py`
- Test: `tests/test_match_service.py`

**Interfaces:**
- Consumes: `AzureSearchKnowledgeBase` (Task 2), `LLMMatcher` (Task 3), `JobPosting` (Task 5 fields).
- Produces: `MatchService(kb=None, matcher=None)` with `async def evaluate_job(self, job: JobPosting) -> JobPosting` and `async def close(self) -> None` — consumed by Task 7 (`ScraperService`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_match_service.py`:

```python
"""Unit tests for MatchService orchestration (KB + LLM are faked)."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.knowledge_base.models import RetrievedChunk
from app.matching.match_service import MatchService
from app.matching.models import MatchResult
from app.models.job import JobPosting


class _FakeKB:
    def __init__(self, chunks):
        self._chunks = chunks
        self.closed = False
        self.last_query = None

    async def search(self, query_text, top_k=None):
        self.last_query = query_text
        return self._chunks

    async def close(self):
        self.closed = True


class _FakeMatcher:
    def __init__(self, result):
        self._result = result
        self.closed = False
        self.last_chunks = None

    async def evaluate(self, job_description, kb_chunks):
        self.last_chunks = kb_chunks
        return self._result

    async def close(self):
        self.closed = True


def test_evaluate_job_populates_match_fields():
    chunks = [RetrievedChunk(chunk_id="c1", parent_id="p1", title="SPFx", chunk="SPFx work...", score=0.9)]
    result = MatchResult(match_score=77, matched_skills=["SPFx"], missing_skills=["Dynamics 365"], match_reason="Good overlap")
    service = MatchService(kb=_FakeKB(chunks), matcher=_FakeMatcher(result))

    job = JobPosting(job_title="SharePoint Developer", company="Acme Corp", job_description="Need SPFx + Dynamics 365 skills")
    updated = asyncio.run(service.evaluate_job(job))

    assert updated.match_score == 77
    assert updated.matched_skills == ["SPFx"]
    assert updated.missing_skills == ["Dynamics 365"]
    assert updated.match_reason == "Good overlap"


def test_evaluate_job_skips_empty_description():
    service = MatchService(kb=_FakeKB([]), matcher=_FakeMatcher(MatchResult(match_score=99)))
    job = JobPosting(job_title="Empty Desc", company="Acme Corp", job_description="   ")
    updated = asyncio.run(service.evaluate_job(job))
    assert updated.match_score is None  # untouched default, matcher never called


def test_evaluate_job_never_raises_on_kb_or_llm_failure():
    class _BoomKB:
        async def search(self, query_text, top_k=None):
            raise RuntimeError("search down")

        async def close(self):
            pass

    service = MatchService(kb=_BoomKB(), matcher=_FakeMatcher(MatchResult(match_score=50)))
    job = JobPosting(job_title="X", company="Y", job_description="Some real description text")
    updated = asyncio.run(service.evaluate_job(job))
    assert updated.match_score is None  # left at default because the pipeline caught the exception


if __name__ == "__main__":
    test_evaluate_job_populates_match_fields()
    test_evaluate_job_skips_empty_description()
    test_evaluate_job_never_raises_on_kb_or_llm_failure()
    print("OK")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_match_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.matching.match_service'` (and `JobPosting` will also reject unknown attributes until Task 5 — run Task 5 before this if your test runner processes files alphabetically; either order is fine since each task's tests are independent files).

- [ ] **Step 3: Create `app/matching/match_service.py`**

```python
"""
Job-to-Company Match Orchestrator
==================================
Coordinates Azure AI Search retrieval (app.knowledge_base.azure_search) and LLM
evaluation (app.matching.llm_matcher) and writes the result onto a JobPosting.
Retrieval and evaluation remain separate services - this module only wires them
together in one direction: Job description -> KB chunks -> LLM verdict -> JobPosting.
"""

from __future__ import annotations

from typing import Optional

from app.knowledge_base.azure_search import AzureSearchKnowledgeBase
from app.matching.llm_matcher import LLMMatcher
from app.models.job import JobPosting
from app.utils.logger import logger


class MatchService:
    """Enriches a JobPosting with an Azure-KB-grounded LLM match evaluation."""

    def __init__(self, kb: Optional[AzureSearchKnowledgeBase] = None, matcher: Optional[LLMMatcher] = None) -> None:
        self._kb = kb if kb is not None else AzureSearchKnowledgeBase()
        self._matcher = matcher if matcher is not None else LLMMatcher()

    async def evaluate_job(self, job: JobPosting) -> JobPosting:
        """Enrich `job` with match_score/matched_skills/missing_skills/match_reason.

        Never raises: any Azure Search or LLM failure just leaves the job's
        existing (default) match fields untouched so scraping never crashes.
        """
        if not job.job_description or not job.job_description.strip():
            return job

        try:
            chunks = await self._kb.search(job.job_description)
            result = await self._matcher.evaluate(job.job_description, chunks)
            job.match_score = result.match_score
            job.matched_skills = result.matched_skills
            job.missing_skills = result.missing_skills
            job.match_reason = result.match_reason
        except Exception as exc:
            logger.error("Job matching pipeline failed for '{}' at '{}': {}", job.job_title, job.company, exc)
        return job

    async def close(self) -> None:
        await self._kb.close()
        await self._matcher.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_match_service.py -v`
Expected: PASS (3 tests) — requires Task 5 to be done first so `JobPosting` has the new fields; if run before Task 5, do Task 5 now and re-run.

- [ ] **Step 5: Commit**

```bash
git add app/matching/match_service.py tests/test_match_service.py
git commit -m "feat: add MatchService to orchestrate KB retrieval + LLM evaluation"
```

---

### Task 5: Add match fields to `JobPosting`

**Files:**
- Modify: `app/models/job.py:24-40`
- Test: `tests/test_job_posting_match_fields.py`

**Interfaces:**
- Produces: `JobPosting.match_score: Optional[int]` (default `None`), `JobPosting.matched_skills: list[str]` (default `[]`), `JobPosting.missing_skills: list[str]` (default `[]`), `JobPosting.match_reason: str` (default `""`) — consumed by Task 4, Task 6.

- [ ] **Step 1: Write the failing test**

Create `tests/test_job_posting_match_fields.py`:

```python
"""Confirms JobPosting carries KB-match fields without breaking existing fields."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.job import JobPosting


def test_job_posting_has_match_fields_with_safe_defaults():
    job = JobPosting(job_title="SharePoint Developer", company="Acme Corp")
    assert job.match_score is None
    assert job.matched_skills == []
    assert job.missing_skills == []
    assert job.match_reason == ""


def test_job_posting_existing_fields_still_work():
    job = JobPosting(job_title="Data Engineer", company="Beta LLC", location="Remote")
    assert job.job_title == "Data Engineer"
    assert job.company == "Beta LLC"
    assert job.location_remote_type  # existing property still computed


def test_job_posting_match_fields_are_settable():
    job = JobPosting(job_title="X", company="Y")
    job.match_score = 85
    job.matched_skills = ["Python", "Azure"]
    job.missing_skills = ["Dynamics 365"]
    job.match_reason = "Strong overlap on Python/Azure"
    dumped = job.model_dump()
    assert dumped["match_score"] == 85
    assert dumped["matched_skills"] == ["Python", "Azure"]


if __name__ == "__main__":
    test_job_posting_has_match_fields_with_safe_defaults()
    test_job_posting_existing_fields_still_work()
    test_job_posting_match_fields_are_settable()
    print("OK")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_job_posting_match_fields.py -v`
Expected: FAIL with `AttributeError: 'JobPosting' object has no attribute 'match_score'`

- [ ] **Step 3: Add the fields to `JobPosting`**

In `app/models/job.py`, after the `scraped_at` field (line 38, right before the closing of the field block / before the `location_remote_type` property), insert:

```python
    match_score: Optional[int] = Field(
        default=None, ge=0, le=100, description="LLM-judged company/job match score (0-100), set by the KB matching pipeline"
    )
    matched_skills: list[str] = Field(default_factory=list, description="Skills/technologies the company can demonstrate for this job")
    missing_skills: list[str] = Field(default_factory=list, description="Required skills the KB shows no evidence of")
    match_reason: str = Field(default="", description="Short LLM explanation of the match score")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_job_posting_match_fields.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the existing parser parity test to confirm nothing broke**

Run: `python -m pytest tests/test_field_parity.py -v` (or `python tests/test_field_parity.py` if it's meant to run as a script)
Expected: still PASS — `JobPosting` gained only optional/defaulted fields, so parser construction code is unaffected.

- [ ] **Step 6: Commit**

```bash
git add app/models/job.py tests/test_job_posting_match_fields.py
git commit -m "feat: add match_score/matched_skills/missing_skills/match_reason to JobPosting"
```

---

### Task 6: Excel export of match fields

**Files:**
- Modify: `app/excel/exporter.py:43-54` (headers), `:79-91` (row values), `:98` (hyperlink column index)
- Test: `tests/test_excel_exporter_match_columns.py`

**Interfaces:**
- Consumes: `JobPosting.match_score/matched_skills/missing_skills/match_reason` (Task 5).

- [ ] **Step 1: Write the failing test**

Create `tests/test_excel_exporter_match_columns.py`:

```python
"""Confirms the Excel export includes the new match columns and keeps the Job URL hyperlink working."""
import shutil
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl

from app.excel.exporter import ExcelExporter
from app.models.job import JobPosting

_OUT_DIR = Path(__file__).resolve().parent / "_tmp_excel_out"


def test_export_includes_match_columns_and_url_hyperlink():
    if _OUT_DIR.exists():
        shutil.rmtree(_OUT_DIR)

    job = JobPosting(
        job_title="SharePoint Developer",
        company="Acme Corp",
        job_description="Need SPFx skills",
        job_url="https://www.indeed.com/viewjob?jk=abc123",
    )
    job.match_score = 88
    job.matched_skills = ["SharePoint", "SPFx"]
    job.missing_skills = ["Dynamics 365"]
    job.match_reason = "Strong SPFx overlap"

    path = ExcelExporter().export([job], output_dir=str(_OUT_DIR))
    wb = openpyxl.load_workbook(path)
    ws = wb.active

    headers = [cell.value for cell in ws[1]]
    assert "Match Score" in headers
    assert "Matched Skills" in headers
    assert "Missing Skills" in headers
    assert "Match Reason" in headers
    assert "Job URL" in headers

    url_col = headers.index("Job URL") + 1
    url_cell = ws.cell(row=2, column=url_col)
    assert url_cell.hyperlink == "https://www.indeed.com/viewjob?jk=abc123"
    assert url_cell.value == "View on Indeed"

    match_score_col = headers.index("Match Score") + 1
    assert ws.cell(row=2, column=match_score_col).value == 88

    shutil.rmtree(_OUT_DIR)


if __name__ == "__main__":
    test_export_includes_match_columns_and_url_hyperlink()
    print("OK")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_excel_exporter_match_columns.py -v`
Expected: FAIL with `assert "Match Score" in headers` (AssertionError)

- [ ] **Step 3: Add the new headers**

In `app/excel/exporter.py`, replace the `headers` list (lines 43-54):

```python
        headers = [
            "Job Title",
            "Company",
            "Country",
            "Location/Remote Type",
            "Experience Criteria",
            "Salary Range",
            "Industry",
            "Company Size",
            "Job Description",
            "Match Score",
            "Matched Skills",
            "Missing Skills",
            "Match Reason",
            "Job URL",
        ]
```

- [ ] **Step 4: Add the new row values and fix the hyperlink column index**

Replace the `row_values` list (lines 79-91):

```python
            row_values = [
                job.job_title,
                job.company,
                job.country,
                job.location_remote_type,
                job.experience,
                job.salary_range,
                job.industry,
                job.company_size,
                job.job_description,
                job.match_score if job.match_score is not None else "",
                ", ".join(job.matched_skills),
                ", ".join(job.missing_skills),
                job.match_reason,
                job.job_url,
            ]
```

Replace line 98's hyperlink column check (`if col_idx == 10 ...`) with:

```python
                if col_idx == 14 and str(val).startswith("http"):  # Job URL hyperlink
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_excel_exporter_match_columns.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/excel/exporter.py tests/test_excel_exporter_match_columns.py
git commit -m "feat: export KB match fields as new Excel columns"
```

---

### Task 7: Wire `MatchService` into `ScraperService`

**Files:**
- Modify: `app/services/scraper_service.py:1-166`
- Test: `tests/test_scraper_service_matching.py`

**Interfaces:**
- Consumes: `MatchService` (Task 4), `Settings.enable_kb_matching` (Task 1).

- [ ] **Step 1: Write the failing test**

Create `tests/test_scraper_service_matching.py`:

```python
"""Confirms ScraperService calls MatchService per job when KB matching is enabled,
and never lets a matching failure abort the pipeline."""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.job import JobPosting
from app.services.scraper_service import ScraperService


class _FakeScraper:
    def __init__(self, jobs, progress_callback=None):
        self._jobs = jobs
        self.progress = type("P", (), {"jobs_found": 0})()

    async def scrape(self, config):
        for job in self._jobs:
            yield job


class _FakeMatchService:
    def __init__(self):
        self.calls = []

    async def evaluate_job(self, job):
        self.calls.append(job.job_title)
        job.match_score = 42
        return job

    async def close(self):
        pass


def test_run_pipeline_calls_match_service_for_each_surviving_job(monkeypatch, tmp_path):
    service = ScraperService()
    service._settings.output_dir = str(tmp_path)
    service._match_service = _FakeMatchService()

    job1 = JobPosting(job_title="Job A", company="Acme", job_description="desc a", posted_date=datetime.now(tz=timezone.utc))
    job2 = JobPosting(job_title="Job B", company="Beta", job_description="desc b", posted_date=datetime.now(tz=timezone.utc))

    service._scraper = _FakeScraper([job1, job2])
    service._date_filter.filter = lambda jobs: jobs
    service._dedup_filter.filter = lambda jobs: jobs

    from app.models.scraper import RunConfig
    asyncio.run(service._run_pipeline(RunConfig()))

    assert service._match_service.calls == ["Job A", "Job B"]
    assert all(j.match_score == 42 for j in service._results)


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_run_pipeline_calls_match_service_for_each_surviving_job(None, Path(d))
    print("OK")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scraper_service_matching.py -v`
Expected: FAIL with `AttributeError: 'ScraperService' object has no attribute '_match_service'`

- [ ] **Step 3: Wire `MatchService` into `ScraperService`**

In `app/services/scraper_service.py`, add the import (after line 19, alongside the other `app.*` imports):

```python
from app.matching.match_service import MatchService
```

In `__init__` (after line 36, `self._exporter = ExcelExporter()`), add:

```python
        self._match_service = MatchService() if self._settings.enable_kb_matching else None
```

In `_run_pipeline`, replace lines 96-108:

```python
            async for job in self._scraper.scrape(config):
                filtered = self._date_filter.filter([job])
                if not filtered:
                    continue

                deduped = self._dedup_filter.filter(filtered)
                if not deduped:
                    continue

                self._results.extend(deduped)
                # Sync progress.jobs_found with active unique results count
                self._scraper.progress.jobs_found = len(self._results)
                self._on_progress_update(self._scraper.progress)
```

with:

```python
            async for job in self._scraper.scrape(config):
                filtered = self._date_filter.filter([job])
                if not filtered:
                    continue

                deduped = self._dedup_filter.filter(filtered)
                if not deduped:
                    continue

                if self._match_service is not None:
                    for matched_job in deduped:
                        try:
                            await self._match_service.evaluate_job(matched_job)
                        except Exception as match_err:
                            logger.error("KB matching error for '{}': {}", matched_job.job_title, match_err)

                self._results.extend(deduped)
                # Sync progress.jobs_found with active unique results count
                self._scraper.progress.jobs_found = len(self._results)
                self._on_progress_update(self._scraper.progress)
```

Finally, add cleanup of the match service's HTTP clients. Replace the `except Exception as exc:` block ending at line 137 so a `finally` closes the match service (insert a `finally` clause after the existing `except` block, still inside `_run_pipeline`):

```python
        except Exception as exc:
            logger.error("Pipeline error: {}", exc)
            if self._scraper:
                progress = self._scraper.progress
                progress.status = ScraperStatus.ERROR
                progress.last_error = str(exc)
                self._broadcast_progress(progress)
        finally:
            if self._match_service is not None:
                try:
                    await self._match_service.close()
                except Exception as close_err:
                    logger.error("Error closing match service: {}", close_err)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_scraper_service_matching.py -v`
Expected: PASS

- [ ] **Step 5: Run the full existing test suite to confirm no regressions**

Run: `python -m pytest tests/ -v`
Expected: all tests pass, including `test_field_parity.py`, `test_settings_azure_kb.py`, `test_azure_search_kb.py`, `test_llm_matcher.py`, `test_match_service.py`, `test_job_posting_match_fields.py`, `test_excel_exporter_match_columns.py`, `test_scraper_service_matching.py`.

- [ ] **Step 6: Commit**

```bash
git add app/services/scraper_service.py tests/test_scraper_service_matching.py
git commit -m "feat: enrich scraped jobs with Azure KB + LLM match scoring in the scraper pipeline"
```

---

### Task 8: Remove stale ChromaDB/knowledge-base pycache and confirm no ChromaDB remnants

**Files:**
- Delete: `app/knowledge_base/__pycache__/` (stale bytecode from a prior, never-committed ChromaDB-based design; the corresponding `.py` files never existed in this branch)

- [ ] **Step 1: Remove the stale bytecode directory**

Run: `Remove-Item -Recurse -Force "app/knowledge_base/__pycache__"` (PowerShell) or `rm -rf app/knowledge_base/__pycache__` (bash) — safe because `__pycache__/` is already gitignored and untracked, and no corresponding source files exist in the working tree.

- [ ] **Step 2: Confirm no ChromaDB references remain anywhere in the tree**

Run: `git grep -il "chroma"` (bash) from the repo root.
Expected: no matches inside `app/`, `requirements.txt`, `.env`, `.env.example`, `tests/` (matches, if any, would only be inside `.superpowers/sdd/2026-09-08-knowledge-base-phase1/*.md` planning docs, which are historical notes, not code, and don't need to be deleted).

- [ ] **Step 3: Commit**

```bash
git add -A app/knowledge_base
git status
```

If `git status` shows only the removal of `__pycache__` entries (which should already be ignored and thus show nothing to commit), no commit is needed. If anything unexpected shows up, stop and report it instead of committing.

---

### Task 9: Debug/test script for manual Azure AI Search verification

**Files:**
- Create: `scripts/test_azure_search.py`

**Interfaces:**
- Consumes: `AzureSearchKnowledgeBase` (Task 2).

- [ ] **Step 1: Create the `scripts/` directory and debug script**

Create `scripts/test_azure_search.py`:

```python
"""
Manual debug script: sends a sample Indeed job description to the existing
Azure AI Search knowledge-base index and prints the top 5 retrieved chunks.

Usage:
    python scripts/test_azure_search.py
    python scripts/test_azure_search.py "Looking for a Power BI + Dynamics 365 consultant"

Requires AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_INDEX, and AZURE_SEARCH_API_KEY to be
set in .env (see .env.example). If they are missing, this script reports that
clearly instead of crashing.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.knowledge_base.azure_search import AzureSearchKnowledgeBase

_SAMPLE_JOB_DESCRIPTION = (
    "We are hiring a Senior SharePoint Developer with strong SPFx experience, "
    "Power BI dashboard development, Power Apps model-driven apps, Dynamics 365 "
    "customization, and hands-on Azure cloud deployment skills. Python and RAG "
    "pipeline experience is a plus."
)


async def main() -> None:
    query = " ".join(sys.argv[1:]) or _SAMPLE_JOB_DESCRIPTION
    print(f"Query:\n{query}\n")

    kb = AzureSearchKnowledgeBase()
    try:
        chunks = await kb.search(query, top_k=5)
    finally:
        await kb.close()

    if not chunks:
        print(
            "No chunks retrieved. Either Azure AI Search is not configured "
            "(check AZURE_SEARCH_ENDPOINT / AZURE_SEARCH_INDEX / AZURE_SEARCH_API_KEY "
            "in .env) or the index returned zero matches."
        )
        return

    print(f"Top {len(chunks)} retrieved chunks:\n")
    for i, chunk in enumerate(chunks, start=1):
        print(f"--- Result {i} (score={chunk.score:.4f}) ---")
        print(f"Title: {chunk.title}")
        print(f"Chunk ID: {chunk.chunk_id}  Parent ID: {chunk.parent_id}")
        print(f"Content: {chunk.chunk[:400]}{'...' if len(chunk.chunk) > 400 else ''}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run the script manually (requires real Azure credentials in `.env`)**

Run: `python scripts/test_azure_search.py`
Expected: either prints up to 5 retrieved chunks with title/score/content, or a clear "not configured" / "zero matches" message — never a stack trace, given `AzureSearchKnowledgeBase.search()` already swallows all exceptions (Task 2).

- [ ] **Step 3: Commit**

```bash
git add scripts/test_azure_search.py
git commit -m "test: add manual debug script for Azure AI Search KB retrieval"
```

---

## Final Verification

- [ ] Run the entire test suite once more: `python -m pytest tests/ -v` — all green.
- [ ] Run `python -c "import app.main" ` style smoke import, or simply start the app (`python main.py`) and confirm it boots without import errors even if `AZURE_SEARCH_API_KEY` / `AZURE_OPENAI_API_KEY` are left blank in `.env` (both services must degrade gracefully per Global Constraints).
- [ ] Confirm `git grep -il chroma` shows no hits under `app/`, `requirements.txt`, `.env`, `.env.example`, or `tests/`.
- [ ] Confirm `.env` (not committed to git) is updated locally with `AZURE_SEARCH_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_CHAT_DEPLOYMENT` before relying on real matching in a live run.
