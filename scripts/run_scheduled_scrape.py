"""
Scheduled Headless Scraping Runner with Centralized Timetable Support
=====================================================================
Runs the Indeed scraping pipeline according to:
1. Centralized daily timetable in config/schedule.json (matched to current hour), OR
2. Explicit CLI arguments (--query, --countries, --slot, etc.).

Features:
- Scrapes target jobs for specified roles & countries.
- Enriches full multi-paragraph job descriptions.
- Evaluates AI Knowledge Base matching scores & extracted skills.
- Generates a clean, formatted Excel workbook in outputs/.
- Auto-syncs leads to SharePoint List (if SHAREPOINT_AUTO_SYNC=true).
- Silent background dispatch of executive report with Excel attachment.

Usage:
    # Timetable auto-match (looks up current hour in config/schedule.json):
    python scripts/run_scheduled_scrape.py --timetable

    # Run specific timetable slot:
    python scripts/run_scheduled_scrape.py --slot "13:00"

    # Run all timetable slots sequentially:
    python scripts/run_scheduled_scrape.py --all-slots

    # Manual one-off override:
    python scripts/run_scheduled_scrape.py --query "Applied AI Engineer" --countries US,GB --max-leads 30
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import get_settings
from app.models.scraper import RunConfig, ScraperStatus
from app.scheduler.timetable import TimetableManager
from app.services.scraper_service import get_scraper_service
from app.utils.logger import logger, setup_logging


async def run_scheduled(
    query: str,
    countries: list[str],
    max_leads: int,
    fromage: int,
    sort_by: str,
    headless: bool,
) -> int:
    settings = get_settings()
    setup_logging(log_dir=settings.log_dir, level="INFO")

    logger.info("=" * 65)
    logger.info("🚀 Starting Scheduled Indeed Job Scraper")
    logger.info("Query:       '{}'", query)
    logger.info("Countries:   {}", countries)
    logger.info("Max Leads:   {}", max_leads)
    logger.info("Freshness:   Last {} day(s)", fromage)
    logger.info("Sort By:     {}", sort_by)
    logger.info("Headless:    {}", headless)
    logger.info("SharePoint:  {}", "ENABLED" if settings.sharepoint_auto_sync else "DISABLED")
    logger.info("=" * 65)

    # Compute max_pages needed based on max_leads (approx 15 jobs per page)
    max_pages = max(1, (max_leads + 14) // 15)
    config = RunConfig(
        query=query,
        countries=countries,
        max_pages=max_pages,
        max_leads=max_leads,
        fromage=str(fromage),
        sort_by=sort_by,
        headless=headless,
    )

    service = get_scraper_service()
    session_id = await service.start(config)

    # Monitor progress in console until finished
    last_status = None
    last_count = -1
    while service._is_running():
        await asyncio.sleep(2.0)
        prog = service.get_progress()

        if prog.jobs_found != last_count or prog.status != last_status:
            last_count = prog.jobs_found
            last_status = prog.status
            status_name = prog.status.value if hasattr(prog.status, "value") else str(prog.status)
            logger.info(
                "[{}] Country: {} | Page: {} | Leads Found: {}",
                status_name.upper(),
                prog.current_country or "-",
                prog.current_page,
                prog.jobs_found,
            )

        if max_leads and prog.jobs_found >= max_leads:
            logger.info("Reached target limit of {} leads; completing run.", max_leads)
            service.stop()
            break

    # Wait for pipeline to finish export, SharePoint sync, and silent dispatch
    if service._current_task:
        try:
            await service._current_task
        except Exception:
            pass

    prog = service.get_progress()
    session = service.get_session()
    leads = service.get_results()

    logger.info("=" * 65)
    status_str = (prog.status.value if hasattr(prog.status, "value") else str(prog.status)).lower()
    if status_str == "error":
        logger.error("Scraping finished with error: {}", prog.last_error)
        return 1

    logger.info("🎉 Scraping successfully completed! Total leads captured: {}", len(leads))
    if session and session.excel_path:
        logger.info("📁 Excel file saved to: {}", session.excel_path)
    logger.info("=" * 65)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Scheduled Indeed Job Scraper & Exporter with Timetable Support")
    parser.add_argument("--query", "-q", default=None, help="Job title or role search query")
    parser.add_argument("--countries", "-c", default=None, help="Comma-separated country codes (e.g. US,GB,IN)")
    parser.add_argument("--max-leads", "-m", type=int, default=None, help="Maximum number of leads to scrape")
    parser.add_argument("--fromage", "-f", type=int, default=None, help="Max age in days (1 = last 24 hours)")
    parser.add_argument("--sort-by", "-s", default="date", choices=["date", "relevance"], help="Sorting method")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser window (default is headless)")
    parser.add_argument("--timetable", "-t", action="store_true", help="Run in timetable mode matching the current time in config/schedule.json")
    parser.add_argument("--slot", default=None, help="Execute a specific time slot from timetable (e.g. '13:00' or '14:00')")
    parser.add_argument("--all-slots", action="store_true", help="Execute all configured timetable slots sequentially")
    parser.add_argument("--schedule-file", default="config/schedule.json", help="Path to timetable schedule JSON file")

    args = parser.parse_args()
    headless = not args.headed
    settings = get_settings()
    setup_logging(log_dir=settings.log_dir, level="INFO")

    manager = TimetableManager(args.schedule_file)

    # 1. Execute all timetable slots sequentially
    if args.all_slots:
        logger.info("=" * 65)
        logger.info("📋 Running All Configured Timetable Slots Sequentially")
        logger.info("=" * 65)
        overall_status = 0
        for slot_key, slot_cfg in manager.timetable.items():
            if not slot_cfg.get("enabled", True):
                logger.info("Skipping disabled slot: [{}]", slot_key)
                continue
            logger.info(">>> Processing Slot: [{}] -> Query: '{}'", slot_key, slot_cfg["query"])
            res = asyncio.run(
                run_scheduled(
                    query=slot_cfg["query"],
                    countries=slot_cfg["countries"],
                    max_leads=slot_cfg["max_leads"],
                    fromage=slot_cfg["fromage"],
                    sort_by=slot_cfg["sort_by"],
                    headless=headless,
                )
            )
            if res != 0:
                overall_status = res
        sys.exit(overall_status)

    # 2. Force run a specific timetable slot (e.g. --slot 13:00)
    if args.slot:
        slot_cfg = manager.get_slot(args.slot)
        if not slot_cfg:
            logger.error("Slot '{}' not found in timetable {}! Available slots: {}", args.slot, args.schedule_file, list(manager.timetable.keys()))
            sys.exit(1)
        logger.info("🎯 Executing specific timetable slot: [{}] -> Query: '{}'", args.slot, slot_cfg["query"])
        exit_code = asyncio.run(
            run_scheduled(
                query=slot_cfg["query"],
                countries=slot_cfg["countries"],
                max_leads=slot_cfg["max_leads"],
                fromage=slot_cfg["fromage"],
                sort_by=slot_cfg["sort_by"],
                headless=headless,
            )
        )
        sys.exit(exit_code)

    # 3. Explicit query passed on CLI -> runs directly
    if args.query:
        country_list = [c.strip().upper() for c in args.countries.split(",")] if args.countries else ["US"]
        max_leads = args.max_leads if args.max_leads is not None else 25
        fromage = args.fromage if args.fromage is not None else 1
        exit_code = asyncio.run(
            run_scheduled(
                query=args.query,
                countries=country_list,
                max_leads=max_leads,
                fromage=fromage,
                sort_by=args.sort_by,
                headless=headless,
            )
        )
        sys.exit(exit_code)

    # 4. Timetable mode (default when no explicit query is provided)
    active_slot = manager.get_current_slot()
    if active_slot:
        slot_key, slot_cfg = active_slot
        logger.info("=" * 65)
        logger.info("📅 Active Timetable Slot Matched: [{}]", slot_key)
        logger.info("Query: '{}' | Countries: {} | Leads: {}", slot_cfg["query"], slot_cfg["countries"], slot_cfg["max_leads"])
        logger.info("=" * 65)
        exit_code = asyncio.run(
            run_scheduled(
                query=slot_cfg["query"],
                countries=slot_cfg["countries"],
                max_leads=slot_cfg["max_leads"],
                fromage=slot_cfg["fromage"],
                sort_by=slot_cfg["sort_by"],
                headless=headless,
            )
        )
        sys.exit(exit_code)
    else:
        now_str = datetime.now().strftime("%H:%M")
        logger.info("=" * 65)
        logger.info("⏰ Timetable Check at {}: No active job slot scheduled.", now_str)
        logger.info("Configured slots in {}: {}", args.schedule_file, list(manager.timetable.keys()))
        logger.info("Tip: Edit config/schedule.json to configure slots, or run --slot <time> manually.")
        logger.info("=" * 65)
        sys.exit(0)


if __name__ == "__main__":
    main()
