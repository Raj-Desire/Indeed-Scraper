"""
Manual promotion of a lead-filter rejection.

When the user decides a rejected posting is worth pursuing, it is scored against the knowledge base
(the same engine as every other lead) and re-classified from that score so it lands in the useful
list with a real number, instead of keeping the filter's "Rejected" label.
"""

from __future__ import annotations

from app.config.constants import SCORE_PRIORITY_HIGH_THRESHOLD, SCORE_PRIORITY_MEDIUM_THRESHOLD
from app.models.job import JobPosting
from app.utils.logger import logger

HIGH, RELEVANT, REVIEW = "High Priority", "Relevant", "Needs Review"


def class_for_match_score(score) -> str:
    """KB match score -> lead class, using the same 70 / 40 cut-offs as the rest of the app."""
    if score is None:
        return REVIEW
    if score >= SCORE_PRIORITY_HIGH_THRESHOLD:
        return HIGH
    if score >= SCORE_PRIORITY_MEDIUM_THRESHOLD:
        return RELEVANT
    return REVIEW


async def promote_job(job: JobPosting, match_service=None) -> JobPosting:
    """Score `job` against the KB and re-classify it as a useful lead. Never raises."""
    previous = job.lead_reason or "rejected by the lead filter"
    if (job.job_description or "").strip():
        try:
            if match_service is None:
                from app.knowledge_base.azure_search import get_knowledge_base
                from app.matching.llm_matcher import get_llm_matcher
                from app.matching.match_service import MatchService

                match_service = MatchService(kb=get_knowledge_base(), matcher=get_llm_matcher())
            await match_service.evaluate_job(job)
        except Exception as exc:
            logger.error("Promotion scoring failed for '{}': {}", job.job_title, exc)

    job.reject_reason = ""  # no longer rejected
    job.lead_class = class_for_match_score(job.match_score)
    job.lead_score = job.match_score if job.match_score is not None else max(job.lead_score or 0, 35)
    job.lead_reason = f"Added manually from Rejected (original verdict: {previous})"
    if job.match_score is None:
        job.lead_reason += " - KB score unavailable, please review"
    return job
