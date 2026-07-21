"""
Date Filter
===========
Filters job postings to keep postings within the configured max age window.
"""

from app.models.job import JobPosting
from app.utils.helpers import is_within_age_limit, parse_indeed_relative_date
from app.utils.logger import logger


class DateFilter:
    """Filters JobPosting objects by posting date age."""

    def __init__(self, max_age_hours: int = 720) -> None:
        self._max_age_hours = max_age_hours

    def filter(self, jobs: list[JobPosting]) -> list[JobPosting]:
        """Filter list of jobs by age window (default 30 days)."""
        passed: list[JobPosting] = []

        for job in jobs:
            if job.posted_date:
                if is_within_age_limit(job.posted_date, self._max_age_hours):
                    passed.append(job)
            elif job.posted_date_raw:
                parsed, is_ambiguous = parse_indeed_relative_date(job.posted_date_raw)
                if is_ambiguous or parsed is None or is_within_age_limit(parsed, self._max_age_hours):
                    if parsed:
                        job.posted_date = parsed
                    passed.append(job)
            else:
                passed.append(job)

        return passed
