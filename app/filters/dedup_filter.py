"""
Deduplication Filter
====================
Prevents the same job from appearing multiple times in the results.
Uses a two-level strategy:
  1. Primary: Indeed Job ID (extracted from URL parameter `jk`)
  2. Secondary: MD5 fingerprint of (normalized title + normalized company)

The dedup filter maintains state across all runs within a session so that
a job found under multiple keyword clusters is only processed once.
"""

from app.models.job import JobPosting
from app.utils.helpers import generate_job_fingerprint
from app.utils.logger import logger


class DedupFilter:
    """
    Stateful deduplication filter.

    Create a single instance per scraper session and pass all jobs through it.
    The filter accumulates seen IDs in memory and does not persist to disk.
    """

    def __init__(self) -> None:
        self._seen_job_ids: set[str] = set()
        self._seen_fingerprints: set[str] = set()
        self._engagement_kind: dict[str, str] = {}  # fingerprint -> "contract" | "other" (rule I1)
        self._total_filtered = 0

    @staticmethod
    def _kind(job: JobPosting) -> str:
        """'contract' when the post states contract / C2C / 1099 / hourly / fixed-duration terms, else 'other'."""
        from app.filters.rulebook import _ENGAGEMENT_EVIDENCE
        return "contract" if _ENGAGEMENT_EVIDENCE.search(f"{job.job_title}\n{job.job_description}\n{job.salary_range}") else "other"

    def filter(self, jobs: list[JobPosting]) -> list[JobPosting]:
        """
        Remove duplicate jobs from the list.

        Args:
            jobs: List of jobs to deduplicate.

        Returns:
            List with duplicates removed.
        """
        unique: list[JobPosting] = []
        for job in jobs:
            if self._is_new(job):
                unique.append(job)
            else:
                self._total_filtered += 1

        if self._total_filtered > 0:
            logger.debug(
                "DedupFilter: {} total duplicates removed so far",
                self._total_filtered
            )
        return unique

    def _is_new(self, job: JobPosting) -> bool:
        """
        Check if this job is new (not seen before) and register it if so.

        Returns:
            True if the job has not been seen before.
        """
        # Primary: Indeed job ID
        if job.indeed_job_id and job.indeed_job_id in self._seen_job_ids:
            return False

        # Secondary: title + company fingerprint
        fingerprint = generate_job_fingerprint(job.job_title, job.company)
        if fingerprint in self._seen_fingerprints:
            # Rule I1: the same post is skipped, UNLESS its engagement terms changed (it now says Contract):
            # let it through once, flagged UPDATED, so the new terms get evaluated.
            if self._engagement_kind.get(fingerprint) != "contract" and self._kind(job) == "contract":
                self._engagement_kind[fingerprint] = "contract"
                job.lead_flag = "UPDATED"
                return True
            return False

        # Register as seen
        if job.indeed_job_id:
            self._seen_job_ids.add(job.indeed_job_id)
        self._seen_fingerprints.add(fingerprint)
        self._engagement_kind[fingerprint] = self._kind(job)
        return True

    def reset(self) -> None:
        """Reset the filter state for a new session."""
        self._seen_job_ids.clear()
        self._seen_fingerprints.clear()
        self._engagement_kind.clear()
        self._total_filtered = 0

    @property
    def duplicates_removed(self) -> int:
        """Total duplicate jobs removed across all calls."""
        return self._total_filtered
