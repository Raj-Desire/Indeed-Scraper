"""
Direct Job Description Match Service
=====================================
Processes raw job descriptions on-demand (without scraping) against:
1. Azure AI Search Knowledge Base retrieval
2. Azure OpenAI / LLM scoring & skill breakdown
3. Microsoft Graph API SharePoint exporter (optional auto-save)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field

from app.matching.match_service import MatchService
from app.models.job import JobPosting
from app.sharepoint.graph_exporter import GraphSharePointExporter
from app.utils.logger import logger


class DirectMatchRequest(BaseModel):
    job_title: str = Field(default="Direct Opportunity", description="Title of the job")
    company: str = Field(default="Custom / Direct Lead", description="Company name")
    country: str = Field(default="US", description="Target country code")
    location_remote_type: str = Field(default="Remote", description="Location or remote indicator")
    job_url: str = Field(default="", description="Original job URL if available")
    job_description: str = Field(..., min_length=10, description="Raw job description text")
    auto_sharepoint_save: bool = Field(default=False, description="Whether to auto-export to SharePoint")


class DirectMatchResponse(BaseModel):
    job_title: str
    company: str
    country: str
    location_remote_type: str
    match_score: Optional[int] = None
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    match_reason: Optional[str] = None
    job_summary: Optional[str] = None
    sharepoint_saved: bool = False
    sharepoint_error: Optional[str] = None


class DirectMatchOrchestrator:
    """Orchestrates direct on-demand JD matching and SharePoint syncing."""

    def __init__(
        self,
        match_service: Optional[MatchService] = None,
        sp_exporter: Optional[GraphSharePointExporter] = None,
    ) -> None:
        self._match_service = match_service if match_service is not None else MatchService()
        self._sp_exporter = sp_exporter if sp_exporter is not None else GraphSharePointExporter()

    async def evaluate_direct_jd(self, req: DirectMatchRequest) -> DirectMatchResponse:
        """Run direct matching for a single user-pasted job description."""
        job = JobPosting(
            job_title=req.job_title.strip() or "Direct Opportunity",
            company=req.company.strip() or "Custom / Direct Lead",
            country=req.country.strip() or "US",
            location_remote_type=req.location_remote_type.strip() or "Remote",
            job_url=req.job_url.strip(),
            job_description=req.job_description.strip(),
            posted_date=datetime.now(tz=timezone.utc),
        )

        logger.info("Evaluating direct JD match for: '{}' at '{}'...", job.job_title, job.company)
        evaluated_job = await self._match_service.evaluate_job(job)

        sp_saved = False
        sp_error = None

        if req.auto_sharepoint_save:
            try:
                count = await self._sp_exporter.export_jobs([evaluated_job])
                sp_saved = count > 0
                logger.info("Direct match exported to SharePoint successfully.")
            except Exception as exc:
                sp_error = str(exc)
                logger.error("Failed to auto-export direct match to SharePoint: {}", exc)

        return DirectMatchResponse(
            job_title=evaluated_job.job_title,
            company=evaluated_job.company,
            country=evaluated_job.country,
            location_remote_type=evaluated_job.location_remote_type,
            match_score=evaluated_job.match_score,
            matched_skills=evaluated_job.matched_skills or [],
            missing_skills=evaluated_job.missing_skills or [],
            match_reason=evaluated_job.match_reason,
            job_summary=getattr(evaluated_job, "job_summary", None),
            sharepoint_saved=sp_saved,
            sharepoint_error=sp_error,
        )


# Global singleton instance
_direct_match_orchestrator: Optional[DirectMatchOrchestrator] = None


def get_direct_match_orchestrator() -> DirectMatchOrchestrator:
    global _direct_match_orchestrator
    if _direct_match_orchestrator is None:
        _direct_match_orchestrator = DirectMatchOrchestrator()
    return _direct_match_orchestrator
