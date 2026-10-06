"""
Cross-check the lead filter's verdict against the knowledge-base match.

The lead filter judges the *type* of engagement (outsourcing vs vacancy vs gig); the KB match judges whether
we can actually do the *work*. Each alone makes mistakes, so they correct each other:

  * A "lead" we cannot serve (KB match very low) is demoted to Needs Review instead of shown as High/Relevant.
  * A single in-house hire is normally rejected, but when its tech stack is a strong match for our service lines
    (LLM/RAG/agents, SharePoint, Power Platform, ...) it is kept as Needs Review so it can be pitched as a
    dedicated-developer / project offer instead of being lost.
"""

from __future__ import annotations

from app.utils.logger import logger

HIGH, RELEVANT, REVIEW, REJECTED = "High Priority", "Relevant", "Needs Review", "Rejected"

LOW_MATCH_FLOOR = 35        # accepted lead with a KB match below this -> Needs Review
HIGH_MATCH_FLOOR = 50       # High Priority needs at least this KB match, else Relevant
RESCUE_TECH_FIT = 70        # internal hire is only rescued when the stack matches this well ...
RESCUE_KB_MATCH = 50        # ... and the KB agrees


def rescue_candidate(job) -> bool:
    """A rejected single internal hire whose tech stack matches our services (worth a KB check)."""
    return (
        job.lead_class == REJECTED
        and (job.engagement_type or "") == "internal_hire"
        and (job.lead_tech_fit or 0) >= RESCUE_TECH_FIT
    )


def reconcile_lead_with_match(job) -> bool:
    """Adjust job.lead_class using job.match_score. Returns True if the class changed."""
    m = job.match_score
    if m is None:
        return False
    before = job.lead_class
    note = ""
    if job.lead_class in (HIGH, RELEVANT):
        if m < LOW_MATCH_FLOOR:
            job.lead_class = REVIEW
            note = f"KB match only {m}% - we may not be able to deliver this"
        elif job.lead_class == HIGH and m < HIGH_MATCH_FLOOR:
            job.lead_class = RELEVANT
            note = f"KB match {m}% is below High Priority level"
    elif rescue_candidate(job) and m >= RESCUE_KB_MATCH:
        job.lead_class = REVIEW
        job.lead_score = max(job.lead_score or 0, 40)
        job.reject_reason = ""
        note = (f"Single in-house hire, but its tech stack is a strong match for our services (KB {m}%) - "
                f"could be pitched as a dedicated-developer/project offer")
    if job.lead_class == before:
        return False
    job.lead_reason = f"[{note}] {job.lead_reason}".strip()  # note first: the dashboard truncates long reasons
    logger.info("Lead '{}' re-classified {} -> {}: {}", job.job_title, before, job.lead_class, note)
    return True


async def match_and_reconcile(job, match_service) -> None:
    """KB-match the job (unless it is a plain rejection) and reconcile its lead class with the score."""
    if job.lead_class == REJECTED and not rescue_candidate(job):
        return  # rejected for a reason a KB score cannot change: skip the cost
    if match_service is not None:
        await match_service.evaluate_job(job)
    reconcile_lead_with_match(job)
