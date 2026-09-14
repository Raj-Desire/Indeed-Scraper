"""
Scraper State Models
====================
Pydantic models for run configuration and live progress tracking.
"""

from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, PrivateAttr, computed_field, model_validator

from app.config.constants import IST


class ScraperStatus(str, Enum):
    """Operational status of the scraper."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    ERROR = "error"


class ScraperProgress(BaseModel):
    """Live progress snapshot broadcast to the interface."""
    status: ScraperStatus = Field(default=ScraperStatus.IDLE)
    current_country: str = Field(default="")
    current_keyword: str = Field(default="")
    current_page: int = Field(default=0)
    max_pages: int = Field(default=3)
    jobs_found: int = Field(default=0)
    started_at: Optional[datetime] = Field(default=None)
    elapsed_seconds: float = Field(default=0.0)
    log_messages: list[str] = Field(default_factory=list)
    last_error: str = Field(default="")

    _log_deque: deque = PrivateAttr(default_factory=lambda: deque(maxlen=50))

    @computed_field
    @property
    def progress_percent(self) -> float:
        """Granular percentage of requested pages processed."""
        if self.status == ScraperStatus.COMPLETED:
            return 100.0
        if self.max_pages <= 0:
            return 0.0
        if self.status in (ScraperStatus.IDLE, ScraperStatus.STOPPED, ScraperStatus.ERROR) and self.current_page == 0:
            return 0.0

        page_weight = 100.0 / self.max_pages
        completed_pages = max(0, self.current_page - 1)
        base_pct = completed_pages * page_weight

        active_page_ratio = 0.25
        if self.jobs_found > 0:
            jobs_on_page = self.jobs_found % 15
            if jobs_on_page == 0:
                jobs_on_page = 15
            active_page_ratio += min(0.65, (jobs_on_page / 15.0) * 0.65)

        total_pct = base_pct + (page_weight * active_page_ratio)
        return round(min(99.0, max(0.0, total_pct)), 1)

    def add_log(self, message: str, max_messages: int = 50) -> None:
        """Append log message using O(1) deque eviction."""
        timestamp = datetime.now(tz=IST).strftime("%I:%M:%S %p IST")
        if self._log_deque.maxlen != max_messages:
            self._log_deque = deque(self._log_deque, maxlen=max_messages)
        self._log_deque.append(f"[{timestamp}] {message}")
        self.log_messages = list(self._log_deque)

    model_config = {"use_enum_values": True}


CORE_DEFAULT_KEYWORDS: list[str] = [
    "SharePoint",
    "Power Apps",
    "Power Automate",
    "AI",
    ".NET",
    "React",
    "n8n",
]


class RunConfig(BaseModel):
    """
    Configuration for a single user-initiated scraping run.
    Takes manual user inputs for countries, search queries (SharePoint, Power Apps, Power Automate, AI, .NET, React, n8n), and max pages.
    """
    countries: list[str] = Field(default_factory=lambda: ["US"], description="Target country codes or names")
    queries: list[str] = Field(default_factory=lambda: list(CORE_DEFAULT_KEYWORDS), description="List of roles or keywords to search")
    query: str = Field(default="SharePoint", description="Primary role or keyword (backward compatibility)")
    max_pages: int = Field(default=1, description="Number of pages to scrape per keyword")
    max_leads: Optional[int] = Field(default=None, description="Max leads desired")
    location_type: str = Field(default="remote", description="Location filter type (all, remote, onsite)")
    fromage: str = Field(default="1", description="Date posted filter: 1 (24h), 3 (3 days), 7 (7 days), 14 (14 days), all")
    sort_by: str = Field(default="date", description="Sort method: date or relevance")
    headless: Optional[bool] = Field(default=None, description="Run in background")
    parser_engine: str = Field(default="selectolax", description="Parser engine to use (beautifulsoup, selectolax)")

    @model_validator(mode="before")
    @classmethod
    def populate_search_params(cls, data: dict) -> dict:
        if isinstance(data, dict):
            if "fromage" in data and data["fromage"] is not None:
                data["fromage"] = str(data["fromage"])

            # Country normalization
            if "countries" not in data or not data["countries"]:
                if "country" in data and data["country"]:
                    if isinstance(data["country"], list):
                        data["countries"] = data["country"]
                    elif isinstance(data["country"], str):
                        data["countries"] = [c.strip() for c in data["country"].split(",") if c.strip()]

            # Queries normalization
            if "queries" in data and data["queries"]:
                if isinstance(data["queries"], list):
                    clean_queries = [str(q).strip() for q in data["queries"] if str(q).strip()]
                    data["queries"] = clean_queries
                    if clean_queries and ("query" not in data or not data["query"]):
                        data["query"] = clean_queries[0]
                elif isinstance(data["queries"], str):
                    clean_queries = [q.strip() for q in data["queries"].split(",") if q.strip()]
                    data["queries"] = clean_queries
                    if clean_queries and ("query" not in data or not data["query"]):
                        data["query"] = clean_queries[0]
            elif "query" in data and data["query"]:
                if isinstance(data["query"], str):
                    parts = [q.strip() for q in data["query"].split(",") if q.strip()]
                    data["queries"] = parts if parts else [data["query"].strip()]
                    data["query"] = parts[0] if parts else data["query"].strip()
                elif isinstance(data["query"], list):
                    clean_queries = [str(q).strip() for q in data["query"] if str(q).strip()]
                    data["queries"] = clean_queries
                    data["query"] = clean_queries[0] if clean_queries else "SharePoint"
            elif "queries" not in data:
                data["queries"] = list(CORE_DEFAULT_KEYWORDS)
                data["query"] = CORE_DEFAULT_KEYWORDS[0]

        return data

    @property
    def country(self) -> str:
        """Backwards compatibility accessor for single country."""
        return self.countries[0] if self.countries else "US"


class ScraperSession(BaseModel):
    """Metadata for a scraping session."""
    session_id: str = Field(description="Unique session ID")
    run_config: RunConfig = Field(default_factory=RunConfig)
    progress: ScraperProgress = Field(default_factory=ScraperProgress)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    total_scraped: int = Field(default=0)
    excel_path: str = Field(default="")
