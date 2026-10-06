"""
Dice Search Orchestration Service
===================================
Wires DiceMCPClient -> job-detail enrichment -> Dedup -> KB/LLM matching ->
SharePoint export. Deliberately simpler than ScraperService: a Dice search is
one bounded request/response cycle, not a long-running cancellable crawl, so
there is no pause/resume/progress-broadcast machinery here.
"""

from __future__ import annotations

import asyncio

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
        self._rejected: list[JobPosting] = []  # rejected by the lead filter (hidden by default)
        self._last_search_params: dict = {}
        self._sharepoint_exporter = None  # lazily constructed in export_sharepoint
        self._email_sent: bool = False

    async def search(self, keyword: str, **filters) -> list[JobPosting]:
        """Run a Dice search: fetch results, enrich with full descriptions,
        dedupe, score via MatchService, and store for later export."""
        try:
            raw_results = await self._dice_client.search_jobs(keyword=keyword, **filters)
        except DiceMCPError as exc:
            logger.error("Dice search failed for keyword '{}': {}", keyword, exc)
            raise

        target_country = filters.get("location")
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
            mapped.append(map_to_job_posting(raw, details, search_query=keyword, target_country=target_country))

        deduped = self._dedup_filter.filter(mapped)

        if self._match_service is None and self._settings.enable_kb_matching:
            self._match_service = MatchService()

        lead_on = bool(getattr(self._settings, "enable_lead_filter", False))
        elig_on = bool(getattr(self._settings, "enable_eligibility_filter", False))
        if self._match_service is not None or lead_on or elig_on:
            sem = asyncio.Semaphore(3)

            async def _score(job: JobPosting) -> None:
                async with sem:
                    try:
                        if elig_on:
                            from app.filters.eligibility_filter import apply_eligibility
                            apply_eligibility(job)  # mandatory citizenship/visa/clearance/residency -> Rejected, no LLM
                        if lead_on and job.lead_class != "Rejected":
                            from app.matching.lead_classifier import get_lead_classifier
                            await get_lead_classifier().apply(job)
                        from app.matching.lead_reconcile import match_and_reconcile
                        await match_and_reconcile(job, self._match_service)  # skips plain rejections; reconciles the rest
                    except Exception as match_err:
                        logger.error("Dice job matching error for '{}': {}", job.job_title, match_err)

            await asyncio.gather(*(_score(j) for j in deduped))

        accepted = [j for j in deduped if j.lead_class != "Rejected"]
        self._rejected.extend(j for j in deduped if j.lead_class == "Rejected")
        self._results.extend(accepted)
        logger.info(
            "Dice search '{}' added {} job(s), {} rejected by lead filter (total: {})",
            keyword, len(accepted), len(deduped) - len(accepted), len(self._results),
        )
        return accepted

    async def search_multi(
        self, keywords: list[str], countries: Optional[list[str]] = None, **filters
    ) -> list[JobPosting]:
        """Run one `search()` per (keyword, country) combination and return every
        newly-added job across all combinations. Country names are passed through
        as Dice's `location` filter, one search per country, since Dice's API takes
        a single location string per call rather than a list. If `countries` is
        empty, each keyword is searched once using whatever `location` was passed
        in `filters` (e.g. a freeform city/state), or no location filter at all.
        Cross-combination duplicates collapse to one result via the existing
        stateful DedupFilter that `search()` already shares across calls.
        """
        self._last_search_params = {
            "keywords": list(keywords),
            "countries": list(countries) if countries else [],
            **filters,
        }
        new_jobs: list[JobPosting] = []
        location_values = countries if countries else [filters.pop("location", None)]

        for keyword in keywords:
            for location in location_values:
                combo_filters = dict(filters)
                if location is not None:
                    combo_filters["location"] = location
                new_jobs.extend(await self.search(keyword, **combo_filters))

        return new_jobs

    async def search_multi_stream(
        self, keywords: list[str], countries: Optional[list[str]] = None, **filters
    ):
        """Run search_multi step-by-step and yield progress events as an async generator."""
        self._last_search_params = {
            "keywords": list(keywords),
            "countries": list(countries) if countries else [],
            **filters,
        }
        location_values = countries if countries else [filters.pop("location", None)]
        combos = [(kw, loc) for kw in keywords for loc in location_values]
        total_combos = len(combos)

        yield {
            "type": "start",
            "total_combos": total_combos,
            "jobs_found": len(self._results),
            "percent": 0,
            "message": f"Starting Dice search across {total_combos} combinations...",
        }

        new_jobs: list[JobPosting] = []
        for idx, (keyword, location) in enumerate(combos, start=1):
            loc_label = location or "Any Location"
            pct = int(((idx - 1) / total_combos) * 85)
            yield {
                "type": "progress",
                "combo_index": idx,
                "total_combos": total_combos,
                "remaining": total_combos - idx + 1,
                "keyword": keyword,
                "location": loc_label,
                "jobs_found": len(self._results),
                "new_jobs": len(new_jobs),
                "percent": pct,
                "message": f"Searching '{keyword}' in {loc_label} (Step {idx} of {total_combos})...",
            }

            combo_filters = dict(filters)
            if location is not None:
                combo_filters["location"] = location

            added_jobs = await self.search(keyword, **combo_filters)
            new_jobs.extend(added_jobs)

            step_pct = int((idx / total_combos) * 85)
            yield {
                "type": "progress",
                "combo_index": idx,
                "total_combos": total_combos,
                "remaining": total_combos - idx,
                "keyword": keyword,
                "location": loc_label,
                "jobs_found": len(self._results),
                "new_jobs": len(new_jobs),
                "percent": step_pct,
                "message": f"Retrieved '{keyword}' in {loc_label} ({idx}/{total_combos} done, {len(added_jobs)} new).",
            }

        yield {
            "type": "enriching",
            "total_combos": total_combos,
            "jobs_found": len(self._results),
            "new_jobs": len(new_jobs),
            "percent": 95,
            "message": f"Finalizing AI evaluations for {len(self._results)} total job lead(s)...",
        }

        leads = self.get_results()
        leads.sort(key=lambda j: (j.match_score is not None, j.match_score or 0), reverse=True)
        yield {
            "type": "complete",
            "total": len(leads),
            "new_count": len(new_jobs),
            "combos": total_combos,
            "percent": 100,
            "leads": leads,
            "message": f"Dice search complete! Found {len(new_jobs)} new job(s) across {total_combos} searches.",
        }

    def get_results(self) -> list[JobPosting]:
        return list(self._results)

    def get_rejected_results(self) -> list[JobPosting]:
        return list(self._rejected)

    def get_exportable(self, selected_ids=None) -> list[JobPosting]:
        """Explicit selection is honoured exactly (even rejected leads); otherwise only useful leads."""
        if selected_ids:
            ids = {str(i) for i in selected_ids}
            return [j for j in self._results + self._rejected if str(j.id) in ids]
        return self.get_visible_results()

    def find_rejected(self, lead_id: str):
        for j in self._rejected:
            if str(j.id) == str(lead_id):
                return j
        return None

    def admit_promoted(self, job: JobPosting) -> None:
        self._rejected = [j for j in self._rejected if j is not job]
        if not any(j is job for j in self._results):
            self._results.insert(0, job)

    def export_useful_for_email(self) -> Optional[str]:
        """Workbook with ALL useful Dice leads for the email attachment (own filename; never rejected leads)."""
        if not self.get_visible_results():
            return None
        return str(self.export_excel(selected_ids=None, filename_prefix="Dice_Useful_Leads_Email"))

    def get_visible_results(self) -> list[JobPosting]:
        """Everything except jobs the lead filter rejected."""
        return [j for j in self._results if getattr(j, "lead_class", "") != "Rejected"]

    def clear_results(self) -> None:
        self._results.clear()
        self._rejected.clear()
        self._last_search_params.clear()
        self._dedup_filter.reset()
        self._email_sent = False

    async def send_email_notification(
        self,
        excel_path: Optional[str] = None,
        query: str = "",
        queries: Optional[list[str]] = None,
        countries: Optional[list[str]] = None,
        fromage: str = "all",
        location_type: str = "remote",
        status: str = "completed",
        error_note: Optional[str] = None,
    ) -> bool:
        """Send daily Dice email report with Excel attachment via Microsoft Graph API."""
        from app.notifications.graph_mail import GraphMailNotifier
        notifier = GraphMailNotifier()
        sent = await notifier.send_report(
            jobs=self.get_visible_results(),  # the email only ever carries useful leads
            excel_path=excel_path,
            query=query,
            queries=queries,
            countries=countries,
            fromage=fromage,
            location_type=location_type,
            status=status,
            error_note=error_note,
            source="Dice",
        )
        if sent:
            self._email_sent = True
        return sent

    def is_email_sent(self) -> bool:
        """Return whether an email has already been dispatched for the current Dice search session."""
        return self._email_sent

    def mark_email_sent(self, sent: bool = True) -> None:
        """Set the email sent status."""
        self._email_sent = sent

    def export_excel(
        self,
        selected_ids: Optional[list[str]] = None,
        output_dir: Optional[str] = None,
        filename_prefix: str = "Dice_Job_Leads",
    ):
        """Export current (or selected) Dice results to a clean, styled Excel workbook."""
        from pathlib import Path
        from app.excel.exporter import ExcelExporter

        leads_to_export = self.get_exportable(selected_ids)

        if not leads_to_export:
            raise ValueError("No Dice job leads to export.")

        keywords = self._last_search_params.get("keywords", [])
        countries = self._last_search_params.get("countries", [])
        posted_date = self._last_search_params.get("posted_date", "all")
        workplace_types = self._last_search_params.get("workplace_types", ["Remote"])
        location_type = "remote" if "Remote" in workplace_types else "all"
        query_str = ", ".join(keywords) if keywords else ""

        exporter = ExcelExporter()
        return exporter.export(
            jobs=leads_to_export,
            output_dir=output_dir or self._settings.output_dir,
            query=query_str,
            countries=countries,
            fromage=posted_date or "all",
            location_type=location_type,
            source="Dice",
            filename_prefix=filename_prefix,
        )

    async def export_sharepoint(self, selected_ids: Optional[list[str]] = None, owner: Optional[str] = None) -> int:
        """Export current (or selected) Dice results to SharePoint via Graph API."""
        if self._sharepoint_exporter is None:
            from app.sharepoint.graph_exporter import GraphSharePointExporter
            self._sharepoint_exporter = GraphSharePointExporter()

        leads_to_export = self.get_exportable(selected_ids)

        return await self._sharepoint_exporter.export_jobs(leads_to_export, owner=owner)


_dice_service: Optional[DiceService] = None


def get_dice_service() -> DiceService:
    global _dice_service
    if _dice_service is None:
        _dice_service = DiceService()
    return _dice_service
