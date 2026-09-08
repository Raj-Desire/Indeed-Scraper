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
