"""
Structured LLM match-evaluation result.
"""

from pydantic import BaseModel, Field


class MatchResult(BaseModel):
    """Structured output of the LLM job-match evaluation."""

    match_score: int = Field(default=0, ge=0, le=100, description="LLM-judged match score, 0-100")
    matched_skills: list[str] = Field(default_factory=list, description="Skills/technologies the company can demonstrate for this job")
    missing_skills: list[str] = Field(default_factory=list, description="Skills/technologies the job requires but the KB shows no evidence of")
    match_reason: str = Field(default="", description="Short explanation of the score")
