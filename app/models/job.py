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
    experience: str = Field(default="Not specified", description="Experience criteria or requirements")
    job_description: str = Field(default="", description="Full job description snippet")
    has_full_description: bool = Field(default=False, description="True if full job description has been enriched")
    scraped_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc),
        description="Timestamp when scraped",
    )
    match_score: Optional[int] = Field(
        default=None, ge=0, le=100, description="LLM-judged company/job match score (0-100), set by the KB matching pipeline"
    )
    matched_skills: list[str] = Field(default_factory=list, description="Skills/technologies the company can demonstrate for this job")
    missing_skills: list[str] = Field(default_factory=list, description="Required skills the KB shows no evidence of")
    match_reason: str = Field(default="", description="Short LLM explanation of the match score")
    job_summary: str = Field(default="", description="Concise summary of the job description")
    outreach_email_subject: str = Field(default="", description="AI-generated outreach email subject line")
    outreach_email_body: str = Field(default="", description="AI-generated outreach email body")
    outreach_linkedin_variants: list[str] = Field(default_factory=list, description="AI-generated LinkedIn outreach message variants")
    outreach_linkedin_message: str = Field(default="", description="Currently selected/edited LinkedIn outreach message")

    @property
    def summary(self) -> str:
        """Returns LLM-produced job_summary if available, otherwise generates a clean excerpt from job_description."""
        if self.job_summary and self.job_summary.strip():
            return self.job_summary.strip()
        return self._generate_fallback_summary()

    def _generate_fallback_summary(self) -> str:
        if not self.job_description or not self.job_description.strip():
            return "No description available."

        import re
        text = re.sub(r"<[^>]+>", " ", self.job_description)
        text = re.sub(r"\s+", " ", text).strip()

        boilerplate_patterns = [
            r"^(?:About the job|Job Description|Role Overview|Position Summary|About Us|Summary)[:\s-]*",
            r"Equal Opportunity Employer.*$",
            r"We are an equal opportunity employer.*$",
            r"Indeed Prime.*$",
        ]
        for pat in boilerplate_patterns:
            text = re.sub(pat, "", text, flags=re.IGNORECASE).strip()

        if len(text) <= 220:
            return text

        truncated = text[:220]
        last_period = truncated.rfind(".")
        if last_period > 80:
            return truncated[:last_period + 1].strip()
        last_space = truncated.rfind(" ")
        if last_space > 80:
            return truncated[:last_space].strip() + "..."
        return truncated + "..."

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
