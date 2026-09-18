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


def test_evaluate_keeps_raw_score_when_no_reconciliation_occurs():
    payload = json.dumps({
        "match_score": 60,
        "matched_skills": ["SharePoint"],
        "missing_skills": ["Dynamics 365"],
        "match_reason": "Partial overlap.",
    })
    fake_client = _FakeAzureOpenAIClient(payload)
    matcher = LLMMatcher(client=fake_client, enabled=True, deployment="test-deployment")

    # "Dynamics 365" does not appear in the retrieved KB context, so reconciliation
    # should not move it into matched_skills, and the LLM's raw score should stand.
    chunks = [RetrievedChunk(chunk_id="c1", parent_id="p1", title="SPFx Projects", chunk="Built SPFx web parts...", score=0.8)]
    result = asyncio.run(matcher.evaluate("Looking for a SharePoint + Dynamics 365 developer", chunks))

    assert result.match_score == 60
    assert "Dynamics 365" in result.missing_skills


def test_evaluate_bumps_score_when_reconciliation_moves_skills_to_matched():
    payload = json.dumps({
        "match_score": 40,
        "matched_skills": ["SharePoint"],
        "missing_skills": ["SPFx"],
        "match_reason": "Some overlap.",
    })
    fake_client = _FakeAzureOpenAIClient(payload)
    matcher = LLMMatcher(client=fake_client, enabled=True, deployment="test-deployment")

    # "SPFx" actually appears in the retrieved KB context, so reconciliation moves it
    # from missing_skills to matched_skills - the score must be corrected upward to
    # stay consistent with the final skills lists shown to the user.
    chunks = [RetrievedChunk(chunk_id="c1", parent_id="p1", title="SPFx Projects", chunk="Built SPFx web parts for SharePoint clients.", score=0.8)]
    result = asyncio.run(matcher.evaluate("Looking for a SharePoint + SPFx developer", chunks))

    assert "SPFx" in result.matched_skills
    assert "SPFx" not in result.missing_skills
    assert result.match_score == 100
    assert result.match_score >= 40


def test_evaluate_strips_matched_skills_not_grounded_in_job_text():
    """
    Regression test for a real production case: a "Supervisor III" job whose only
    Microsoft-365-related line was "Proficient in ... SharePoint, and Box" got
    matched_skills full of unrelated company-capability phrases the LLM pulled from
    the KB context (e.g. "Voice Interface", "Kanban boards") that the job never
    asked for - inflating an irrelevant role to a 100 match score. Skills with zero
    overlap with the job text itself must be dropped before scoring.
    """
    payload = json.dumps({
        "match_score": 55,
        "matched_skills": ["SharePoint", "Voice Interface", "Kanban boards", "Real-time voice interview"],
        "missing_skills": [],
        "match_reason": "Some overlap.",
    })
    fake_client = _FakeAzureOpenAIClient(payload)
    matcher = LLMMatcher(client=fake_client, enabled=True, deployment="test-deployment")

    chunks = [RetrievedChunk(
        chunk_id="c1", parent_id="p1", title="Product Features",
        chunk="Our platform offers Kanban boards, Gantt charts, a Voice Interface with real-time voice interview support, and SharePoint integration.",
        score=0.8,
    )]
    jd = "Supervisor III (Remote). Proficient in Microsoft Office 365 (Word, Excel, PowerPoint, Outlook, Teams, OneNote, One Drive), SharePoint, and Box."
    result = asyncio.run(matcher.evaluate(jd, chunks))

    assert "SharePoint" in result.matched_skills
    assert "Voice Interface" not in result.matched_skills
    assert "Kanban boards" not in result.matched_skills
    assert "Real-time voice interview" not in result.matched_skills


def test_evaluate_returns_disabled_default_when_not_configured():
    matcher = LLMMatcher(client=None, enabled=False, deployment="")
    result = asyncio.run(matcher.evaluate("some job description", []))
    assert result.match_score is None
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
    assert result.match_score is None
    assert "failed" in result.match_reason.lower() or "rate limited" in result.match_reason.lower()


if __name__ == "__main__":
    test_evaluate_parses_structured_json_response()
    test_evaluate_keeps_raw_score_when_no_reconciliation_occurs()
    test_evaluate_bumps_score_when_reconciliation_moves_skills_to_matched()
    test_evaluate_returns_disabled_default_when_not_configured()
    test_evaluate_swallows_client_errors()
    print("OK")
