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
        self._total_filtered = 0

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
            return False

        # Register as seen
        if job.indeed_job_id:
            self._seen_job_ids.add(job.indeed_job_id)
        self._seen_fingerprints.add(fingerprint)
        return True

    def reset(self) -> None:
        """Reset the filter state for a new session."""
        self._seen_job_ids.clear()
        self._seen_fingerprints.clear()
        self._total_filtered = 0

    @property
    def duplicates_removed(self) -> int:
        """Total duplicate jobs removed across all calls."""
        return self._total_filtered
