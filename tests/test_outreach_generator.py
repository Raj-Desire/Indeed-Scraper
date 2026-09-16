"""Unit tests for the outreach email/LinkedIn draft generator (LLM client is faked)."""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.constants import OUTREACH_ENGAGEMENT_MODELS, OUTREACH_TEAM_SIZE
from app.matching.llm_matcher import LLMMatcher
from app.matching.outreach_generator import generate_outreach


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


def test_generate_outreach_builds_structured_email_from_template():
    payload = json.dumps({
        "email_subject": "Application for Senior SharePoint Developer",
        "opening_line": "I came across your requirement for a Senior SharePoint Developer and wanted to reach out.",
        "alignment_paragraph": "This experience aligns well with your requirements around SharePoint and SPFx.",
        "linkedin_variants": ["Hi there, ...", "Hello, ...", "Hey, ...", "Greetings, ..."],
    })
    fake_client = _FakeAzureOpenAIClient(payload)
    matcher = LLMMatcher(client=fake_client, enabled=True, deployment="test-deployment")

    result = asyncio.run(generate_outreach(
        job_title="Senior SharePoint Developer",
        company="Fujitsu",
        job_description="Looking for a SharePoint + SPFx developer",
        matched_skills=["SharePoint", "SPFx"],
        missing_skills=["Power BI"],
        kb_context="- Company has SharePoint and SPFx expertise",
        contact_name="Miroslav",
        matcher=matcher,
    ))

    assert result["email_subject"] == "Application for Senior SharePoint Developer"
    body = result["email_body"]
    # Structured, not a single paragraph blob: real greeting, bulleted skills,
    # the LLM's connective sentences, and the fixed engagement-model bullets.
    assert body.startswith("Hi Miroslav,")
    assert "• SharePoint" in body
    assert "• SPFx" in body
    assert "I came across your requirement" in body
    assert "This experience aligns well with your requirements" in body
    assert f"team of {OUTREACH_TEAM_SIZE} skilled developers" in body
    for model in OUTREACH_ENGAGEMENT_MODELS:
        assert f"• {model}" in body
    assert "[Rate]" in body
    assert len(result["linkedin_variants"]) == 4


def test_generate_outreach_defaults_greeting_without_contact_name():
    payload = json.dumps({
        "email_subject": "Subject",
        "opening_line": "Opening.",
        "alignment_paragraph": "Alignment.",
        "linkedin_variants": ["v1"],
    })
    fake_client = _FakeAzureOpenAIClient(payload)
    matcher = LLMMatcher(client=fake_client, enabled=True, deployment="test-deployment")

    result = asyncio.run(generate_outreach(
        job_title="Role",
        company="Co",
        job_description="Description",
        matcher=matcher,
    ))

    assert result["email_body"].startswith("Hi there,")


def test_generate_outreach_returns_empty_when_llm_disabled():
    matcher = LLMMatcher(client=None, enabled=False, deployment="")

    result = asyncio.run(generate_outreach(
        job_title="Some Role",
        company="Some Co",
        job_description="Some description",
        matcher=matcher,
    ))

    assert result == {"email_subject": "", "email_body": "", "linkedin_variants": []}


def test_generate_outreach_swallows_client_errors():
    class _BoomChat:
        class completions:
            @staticmethod
            async def create(**kwargs):
                raise RuntimeError("rate limited")

    class _BoomClient:
        chat = _BoomChat()

    matcher = LLMMatcher(client=_BoomClient(), enabled=True, deployment="test-deployment")

    result = asyncio.run(generate_outreach(
        job_title="Some Role",
        company="Some Co",
        job_description="Some description",
        matcher=matcher,
    ))

    assert result == {"email_subject": "", "email_body": "", "linkedin_variants": []}


def test_generate_outreach_caps_linkedin_variants_to_configured_count():
    from app.config.constants import OUTREACH_LINKEDIN_VARIANT_COUNT

    payload = json.dumps({
        "email_subject": "Subject",
        "opening_line": "Opening.",
        "alignment_paragraph": "Alignment.",
        "linkedin_variants": ["v1", "v2", "v3", "v4", "v5", "v6"],
    })
    fake_client = _FakeAzureOpenAIClient(payload)
    matcher = LLMMatcher(client=fake_client, enabled=True, deployment="test-deployment")

    result = asyncio.run(generate_outreach(
        job_title="Role",
        company="Co",
        job_description="Description",
        matcher=matcher,
    ))

    assert len(result["linkedin_variants"]) == OUTREACH_LINKEDIN_VARIANT_COUNT


if __name__ == "__main__":
    test_generate_outreach_builds_structured_email_from_template()
    test_generate_outreach_defaults_greeting_without_contact_name()
    test_generate_outreach_returns_empty_when_llm_disabled()
    test_generate_outreach_swallows_client_errors()
    test_generate_outreach_caps_linkedin_variants_to_configured_count()
    print("OK")
