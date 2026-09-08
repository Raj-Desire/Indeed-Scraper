"""
Manual debug script: sends a sample Indeed job description to the existing
Azure AI Search knowledge-base index and prints the top 5 retrieved chunks.

Usage:
    python scripts/test_azure_search.py
    python scripts/test_azure_search.py "Looking for a Power BI + Dynamics 365 consultant"

Requires AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_INDEX, and AZURE_SEARCH_API_KEY to be
set in .env (see .env.example). If they are missing, this script reports that
clearly instead of crashing.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.knowledge_base.azure_search import AzureSearchKnowledgeBase

_SAMPLE_JOB_DESCRIPTION = (
    "We are hiring a Senior SharePoint Developer with strong SPFx experience, "
    "Power BI dashboard development, Power Apps model-driven apps, Dynamics 365 "
    "customization, and hands-on Azure cloud deployment skills. Python and RAG "
    "pipeline experience is a plus."
)


async def main() -> None:
    query = " ".join(sys.argv[1:]) or _SAMPLE_JOB_DESCRIPTION
    print(f"Query:\n{query}\n")

    kb = AzureSearchKnowledgeBase()
    try:
        chunks = await kb.search(query, top_k=5)
    finally:
        await kb.close()

    if not chunks:
        print(
            "No chunks retrieved. Either Azure AI Search is not configured "
            "(check AZURE_SEARCH_ENDPOINT / AZURE_SEARCH_INDEX / AZURE_SEARCH_API_KEY "
            "in .env) or the index returned zero matches."
        )
        return

    print(f"Top {len(chunks)} retrieved chunks:\n")
    for i, chunk in enumerate(chunks, start=1):
        print(f"--- Result {i} (score={chunk.score:.4f}) ---")
        print(f"Title: {chunk.title}")
        print(f"Chunk ID: {chunk.chunk_id}  Parent ID: {chunk.parent_id}")
        print(f"Content: {chunk.chunk[:400]}{'...' if len(chunk.chunk) > 400 else ''}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
