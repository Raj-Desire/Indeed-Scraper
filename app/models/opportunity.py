"""
Opportunity Model
=================
Schema model strictly matching Microsoft SharePoint 'Opportunity Tracker' list (30 columns).
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class OpportunityPayload(BaseModel):
    """Complete schema model matching SharePoint Opportunity Tracker."""
    title: str = Field(..., description="Job Title / Opportunity Title")
    company: Optional[str] = Field(default="", description="Prospect / Company Name")
    contact_name: Optional[str] = Field(default="", description="Contact Name")
    email: Optional[str] = Field(default="", description="Contact Email")
    phone: Optional[str] = Field(default="", description="Contact Phone")
    website: Optional[str] = Field(default="", description="Website / Job URL")
    country: Optional[str] = Field(default="US", description="Country choice (US, South Africa, UK, etc.)")
    industry: Optional[str] = Field(default="IT", description="Industry choice (IT, Construction, Legal, Healthcare, Logistics)")
    lead_source: Optional[str] = Field(default="Indeed", description="Lead Source choice")
    owner: Optional[str] = Field(default="Meet", description="Owner choice (Sizan, Meet, Chetan)")
    priority: Optional[str] = Field(default="Medium", description="Priority choice (High, Medium, Low)")
    date_added: Optional[str] = Field(default=None, description="Date Added (YYYY-MM-DD)")
    status: Optional[str] = Field(default="New", description="Status choice")
    next_follow_up_date: Optional[str] = Field(default=None, description="Next Follow-up Date (YYYY-MM-DD)")
    last_activity_date: Optional[str] = Field(default=None, description="Last Activity Date (YYYY-MM-DD)")
    notes: Optional[str] = Field(default="", description="General notes or JD summary")
    technology: list[str] = Field(default_factory=list, description="MultiChoice technologies (AI, SharePoint, Power Platform, .NET, Dynamics, Power BI, Admin)")
    estimated_value: Optional[float] = Field(default=None, description="Estimated Value amount")
    currency_code: Optional[str] = Field(default="USD", description="Currency Code choice (INR, USD, CAD, GBP, EUR)")
    due_date: Optional[str] = Field(default=None, description="Due Date (YYYY-MM-DD)")
    vp_approval_status: Optional[str] = Field(default="Not Required", description="VP Approval Status")
    outcome_reason: Optional[str] = Field(default="", description="Outcome Reason")
    checklist: list[str] = Field(default_factory=list, description="Checklist multi-choice items")
    job_requirement: Optional[str] = Field(default="", description="Job Requirement / Description")
    matching_score: Optional[int] = Field(default=None, description="Matching Score (0-100)")
    matching_skills: Optional[Any] = Field(default="", description="Matching Skills (string or list)")
    matching_reason: Optional[str] = Field(default="", description="Matching Reason justification")
    missing_skills: Optional[Any] = Field(default="", description="Missing Skills (string or list)")
    experience_criteria: Optional[str] = Field(default="", description="Experience Criteria")
    salary_range: Optional[str] = Field(default="", description="Salary Range")
    lead_id: Optional[str] = Field(default=None, description="Optional internal lead UUID for synchronization")

    model_config = {"extra": "ignore"}
