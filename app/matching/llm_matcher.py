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
