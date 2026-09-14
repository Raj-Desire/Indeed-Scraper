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
            if result.match_score is not None:
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
