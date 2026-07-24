"""
Job Data Models
===============
Pydantic models representing scraped job lead information.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class RemoteType(str, Enum):
    """Remote status of a job posting."""
    FULLY_REMOTE = "Fully Remote"
    HYBRID = "Hybrid"
    ON_SITE = "On-Site"
    UNKNOWN = "Unknown"


class JobPosting(BaseModel):
    """
    Clean structured job lead data extracted from Indeed.
    """
    id: UUID = Field(default_factory=uuid4, description="Internal unique ID")
    indeed_job_id: str = Field(default="", description="Indeed job ID")
    job_title: str = Field(description="Job title")
    company: str = Field(description="Company name")
    location: str = Field(default="", description="Location string")
    country: str = Field(default="US", description="Country code or name")
    search_query: str = Field(default="", description="Role or keyword searched")
    remote_type: RemoteType = Field(default=RemoteType.UNKNOWN)
    salary_range: str = Field(default="Not listed", description="Salary string")
    industry: str = Field(default="Not listed", description="Industry or business sector")
    company_size: str = Field(default="Not listed", description="Company workforce size")
    posted_date_raw: str = Field(default="", description="Raw date string")
    posted_date: Optional[datetime] = Field(default=None, description="Parsed posting date")
    job_url: str = Field(default="", description="Full Indeed job URL")
    apply_url: str = Field(default="", description="Direct apply URL if available")
    job_description: str = Field(default="", description="Full job description snippet")
    scraped_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc),
        description="Timestamp when scraped",
    )

    @property
    def location_remote_type(self) -> str:
        loc = self.location.strip() if self.location else ""
        rem = self.remote_type.value if hasattr(self.remote_type, "value") else str(self.remote_type or "")
        
        if loc and rem and rem != "Unknown":
            if loc.lower() == rem.lower() or (loc.lower() == "remote" and "remote" in rem.lower()):
                return f"Remote ({rem})"
            return f"{loc} ({rem})"
        elif loc:
            return loc
        elif rem and rem != "Unknown":
            return rem
        return "Not listed"

    model_config = {"use_enum_values": True}
