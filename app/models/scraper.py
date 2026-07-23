"""
Scraper State Models
====================
Pydantic models for run configuration and live progress tracking.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, computed_field


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
        """Append log message."""
        timestamp = datetime.utcnow().strftime("%H:%M:%S")
        self.log_messages.append(f"[{timestamp}] {message}")
        if len(self.log_messages) > max_messages:
            self.log_messages = self.log_messages[-max_messages:]

    model_config = {"use_enum_values": True}


class RunConfig(BaseModel):
    """
    Configuration for a single user-initiated scraping run.
    Takes manual user inputs for country, search query, and max pages.
    """
    country: str = Field(default="US", description="Target country code or name")
    query: str = Field(default="AI Developer", description="Role or keyword to search")
    max_pages: int = Field(default=3, description="Number of pages to scrape")
    location_type: str = Field(default="all", description="Location filter type (all, remote, onsite, hybrid)")
    headless: Optional[bool] = Field(default=None, description="Run in background")
    parser_engine: str = Field(default="beautifulsoup", description="Parser engine to use (beautifulsoup, selectolax)")


class ScraperSession(BaseModel):
    """Metadata for a scraping session."""
    session_id: str = Field(description="Unique session ID")
    run_config: RunConfig = Field(default_factory=RunConfig)
    progress: ScraperProgress = Field(default_factory=ScraperProgress)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    total_scraped: int = Field(default=0)
    excel_path: str = Field(default="")
