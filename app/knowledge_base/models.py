"""
Knowledge-base retrieval result model.
"""

from pydantic import BaseModel, Field


class RetrievedChunk(BaseModel):
    """One company-knowledge chunk retrieved from Azure AI Search."""

    chunk_id: str = Field(default="", description="Azure AI Search document id (chunk_id field)")
    parent_id: str = Field(default="", description="Parent document id this chunk belongs to")
    title: str = Field(default="", description="Source document title")
    chunk: str = Field(default="", description="The retrieved text chunk")
    score: float = Field(
        default=0.0,
        description="Azure AI Search relevance score - informational only, never the final job match score",
    )
