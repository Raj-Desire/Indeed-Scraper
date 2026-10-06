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


async def promote_job(job: JobPosting, match_service=None, rescore: bool = False) -> JobPosting:
    """Move a rejected lead into the useful leads. Never raises and never needs the LLM/KB.

    By default nothing is re-scored: the lead keeps whatever scores it already has (lead score, and the KB match
    score if one exists) and is shown with them. Pass `rescore=True` (and a match service) to score it against
    the KB first."""
    previous = job.lead_reason or "rejected by the lead filter"
    if rescore and match_service is not None and (job.job_description or "").strip():
        try:
            await match_service.evaluate_job(job)
        except Exception as exc:
            logger.error("Promotion scoring failed for '{}': {}", job.job_title, exc)

    job.reject_reason = ""  # no longer rejected
    job.lead_class = class_for_match_score(job.match_score)  # no KB score -> "Needs Review"
    if job.match_score is not None:
        job.lead_score = job.match_score
    job.lead_reason = f"Added manually from Rejected (original verdict: {previous})"
    return job
