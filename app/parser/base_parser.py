"""
Base Job Parser
===============
Abstract Base Class defining the interface for all HTML parsers.
"""

from abc import ABC, abstractmethod
from app.models.job import JobPosting


class BaseJobParser(ABC):
    """
    Abstract interface for parsing Indeed search results and job details.
    """

    @abstractmethod
    def parse_search_results(
        self,
        html: str,
        country: str = "US",
        search_query: str = "",
    ) -> list[JobPosting]:
        """
        Parse all job cards from an Indeed search results page.
        """
        pass

    @abstractmethod
    def enrich_with_description(
        self, job: JobPosting, description_html: str
    ) -> JobPosting:
        """
        Enrich an existing JobPosting with a full job description.
        """
        pass
