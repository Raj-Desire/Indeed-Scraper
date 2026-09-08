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
