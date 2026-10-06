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

    @property
    def enabled(self) -> bool:
        return bool(self._enabled and self._client)

    async def search(
        self, query_text: str, top_k: Optional[int] = None, raise_on_error: bool = False
    ) -> list[RetrievedChunk]:
        """Retrieve the most relevant company-knowledge chunks for a query.

        By default never raises: any Azure Search failure is logged and results in an
        empty list so scraping/matching can continue. Callers that must tell "no
        relevant knowledge" apart from "retrieval broke" pass raise_on_error=True.
        """
        if not self._enabled or not self._client or not query_text.strip():
            return []

        settings = get_settings()
        k = top_k or self._top_k
        search_query = query_text.strip()[:1500]
        try:
            from azure.search.documents.models import VectorizableTextQuery

            vector_query = VectorizableTextQuery(text=search_query, k_nearest_neighbors=k, fields="text_vector")
            kwargs = {}
            semantic_config = getattr(settings, "azure_search_semantic_config", "")
            if semantic_config:
                kwargs["query_type"] = "semantic"
                kwargs["semantic_configuration_name"] = semantic_config
            results = await self._client.search(
                search_text=search_query,
                vector_queries=[vector_query],
                select=["chunk_id", "parent_id", "title", "chunk"],
                top=k,
                **kwargs,
            )

            min_score = float(getattr(settings, "azure_search_min_score", 0.0) or 0.0)
            chunks: list[RetrievedChunk] = []
            async for result in results:
                # Semantic reranker score (0-4) is more comparable than the hybrid RRF score
                score = float(result.get("@search.reranker_score") or result.get("@search.score", 0.0) or 0.0)
                if min_score and score < min_score:
                    continue
                chunks.append(
                    RetrievedChunk(
                        chunk_id=str(result.get("chunk_id") or ""),
                        parent_id=str(result.get("parent_id") or ""),
                        title=str(result.get("title") or ""),
                        chunk=str(result.get("chunk") or ""),
                        score=score,
                    )
                )
            return chunks
        except Exception as exc:
            logger.error("Azure AI Search retrieval failed: {}", exc)
            if raise_on_error:
                raise
            return []

    async def close(self) -> None:
        if self._client and hasattr(self._client, "close"):
            try:
                await self._client.close()
            except Exception as exc:
                logger.error("Error closing Azure Search client: {}", exc)


_knowledge_base: Optional["AzureSearchKnowledgeBase"] = None


def get_knowledge_base() -> "AzureSearchKnowledgeBase":
    """Shared AzureSearchKnowledgeBase instance, so repeated retrievals reuse the
    same warm SearchClient instead of paying a fresh connection cold-start on
    every request."""
    global _knowledge_base
    if _knowledge_base is None:
        _knowledge_base = AzureSearchKnowledgeBase()
    return _knowledge_base
