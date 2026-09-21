"""
Dice Search Orchestration Service
===================================
Wires DiceMCPClient -> job-detail enrichment -> Dedup -> KB/LLM matching ->
SharePoint export. Deliberately simpler than ScraperService: a Dice search is
one bounded request/response cycle, not a long-running cancellable crawl, so
there is no pause/resume/progress-broadcast machinery here.
"""

from __future__ import annotations

from typing import Optional

from app.config.settings import get_settings
from app.filters.dedup_filter import DedupFilter
from app.matching.match_service import MatchService
from app.models.job import JobPosting
from app.scraper.dice_mcp_client import DiceMCPClient, DiceMCPError, map_to_job_posting
from app.utils.logger import logger


class DiceService:
    """Orchestrates Dice MCP search, matching, and SharePoint export."""

    def __init__(
        self,
        dice_client: Optional[DiceMCPClient] = None,
        match_service: Optional[MatchService] = None,
    ) -> None:
        self._settings = get_settings()
        self._dice_client = dice_client if dice_client is not None else DiceMCPClient()
        self._match_service = match_service  # lazily constructed in search() unless injected
        self._dedup_filter = DedupFilter()
        self._results: list[JobPosting] = []
        self._sharepoint_exporter = None  # lazily constructed in export_sharepoint

    async def search(self, keyword: str, **filters) -> list[JobPosting]:
        """Run a Dice search: fetch results, enrich with full descriptions,
        dedupe, score via MatchService, and store for later export."""
        try:
            raw_results = await self._dice_client.search_jobs(keyword=keyword, **filters)
        except DiceMCPError as exc:
            logger.error("Dice search failed for keyword '{}': {}", keyword, exc)
            raise

        mapped: list[JobPosting] = []
        for raw in raw_results:
            guid = raw.get("guid")
            details = None
            if guid:
                try:
                    details = await self._dice_client.get_job_details(guid)
                except DiceMCPError as exc:
                    logger.warning(
                        "Dice get_job_details failed for '{}' (continuing with summary only): {}",
                        guid, exc,
                    )
            mapped.append(map_to_job_posting(raw, details, search_query=keyword))

        deduped = self._dedup_filter.filter(mapped)

        if self._match_service is None and self._settings.enable_kb_matching:
            self._match_service = MatchService()

        if self._match_service is not None:
            for job in deduped:
                try:
                    await self._match_service.evaluate_job(job)
                except Exception as match_err:
                    logger.error("Dice job matching error for '{}': {}", job.job_title, match_err)

        self._results.extend(deduped)
        logger.info("Dice search '{}' added {} job(s) (total: {})", keyword, len(deduped), len(self._results))
        return deduped

    def get_results(self) -> list[JobPosting]:
        return list(self._results)

    def clear_results(self) -> None:
        self._results.clear()
        self._dedup_filter.reset()

    async def export_sharepoint(self, selected_ids: Optional[list[str]] = None, owner: Optional[str] = None) -> int:
        """Export current (or selected) Dice results to SharePoint via Graph API."""
        if self._sharepoint_exporter is None:
            from app.sharepoint.graph_exporter import GraphSharePointExporter
            self._sharepoint_exporter = GraphSharePointExporter()

        leads_to_export = self._results
        if selected_ids is not None:
            id_set = {str(i) for i in selected_ids}
            leads_to_export = [j for j in self._results if str(j.id) in id_set]

        return await self._sharepoint_exporter.export_jobs(leads_to_export, owner=owner)


_dice_service: Optional[DiceService] = None


def get_dice_service() -> DiceService:
    global _dice_service
    if _dice_service is None:
        _dice_service = DiceService()
    return _dice_service
