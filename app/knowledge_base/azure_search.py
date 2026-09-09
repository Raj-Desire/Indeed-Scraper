"""
Azure AI Search Knowledge Base Retrieval
=========================================
Connects to the existing Azure AI Search index (AZURE_SEARCH_INDEX) to retrieve
company-knowledge chunks relevant to a cleaned Indeed job description.

Uses the index's existing Azure OpenAI vectorizer (text-embedding-3-small) via
VectorizableTextQuery, so this service never computes its own embeddings and
never creates a second vector store.
"""

from __future__ import annotations

from typing import Optional

from app.config.settings import get_settings
from app.knowledge_base.models import RetrievedChunk
from app.utils.logger import logger


class AzureSearchKnowledgeBase:
    """Hybrid (full-text + vector) retrieval against the existing Azure AI Search KB index."""

    def __init__(self, client=None, enabled: Optional[bool] = None, top_k: Optional[int] = None) -> None:
        """
        Args:
            client: Optional pre-built azure.search.documents.aio.SearchClient, for tests.
                    When omitted, a real client is built from Settings.
            enabled: Override for whether retrieval is active (tests only).
            top_k: Override for the default number of chunks to retrieve (tests only).
        """
        settings = get_settings()
        self._top_k = top_k if top_k is not None else settings.azure_search_top_k

        if enabled is False:
            self._enabled = False
            self._client = None
            return

        if client is not None:
            self._client = client
            self._enabled = True if enabled is None else enabled
            return

        self._enabled = bool(
            settings.azure_search_endpoint and settings.azure_search_api_key and settings.azure_search_index
        )
        self._client = None
        if not self._enabled:
            logger.warning(
                "Azure AI Search is not fully configured (endpoint/api key/index) - KB retrieval disabled."
            )
            return

        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents.aio import SearchClient

        self._client = SearchClient(
            endpoint=settings.azure_search_endpoint,
            index_name=settings.azure_search_index,
            credential=AzureKeyCredential(settings.azure_search_api_key),
        )

    async def search(self, query_text: str, top_k: Optional[int] = None) -> list[RetrievedChunk]:
        """Retrieve the most relevant company-knowledge chunks for a job description.

        Never raises: any Azure Search failure is logged and results in an empty list
        so scraping/matching can continue without the run crashing.
        """
        if not self._enabled or not self._client or not query_text.strip():
            return []

        k = top_k or self._top_k
        # Optimize query for vectorizer (first 1500 chars of core technical requirements)
        search_query = query_text.strip()[:1500]
        try:
            from azure.search.documents.models import VectorizableTextQuery

            vector_query = VectorizableTextQuery(text=search_query, k_nearest_neighbors=k, fields="text_vector")
            results = await self._client.search(
                search_text=search_query,
                vector_queries=[vector_query],
                select=["chunk_id", "parent_id", "title", "chunk"],
                top=k,
            )

            chunks: list[RetrievedChunk] = []
            async for result in results:
                chunks.append(
                    RetrievedChunk(
                        chunk_id=str(result.get("chunk_id") or ""),
                        parent_id=str(result.get("parent_id") or ""),
                        title=str(result.get("title") or ""),
                        chunk=str(result.get("chunk") or ""),
                        score=float(result.get("@search.score", 0.0) or 0.0),
                    )
                )
            return chunks
        except Exception as exc:
            logger.error("Azure AI Search retrieval failed: {}", exc)
            return []

    async def close(self) -> None:
        if self._client and hasattr(self._client, "close"):
            try:
                await self._client.close()
            except Exception as exc:
                logger.error("Error closing Azure Search client: {}", exc)
