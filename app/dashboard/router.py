"""
FastAPI Router — Simple Scraper Application
=============================================
Serves the single-page HTML application and JSON API endpoints.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config.constants import COMMON_COUNTRIES
from app.config.settings import get_settings
from app.dashboard.websocket import ws_manager
from app.models.scraper import RunConfig
from app.services.scraper_service import get_scraper_service
from app.utils.logger import logger

router = APIRouter()
templates = Jinja2Templates(directory="templates")
settings = get_settings()


@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Silence browser default 404 favicon request."""
    return HTMLResponse(content="", status_code=204)


@router.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """Serve the single-page application interface."""
    countries = [{"name": c.name, "code": c.code} for c in COMMON_COUNTRIES]
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "countries": countries},
    )


@router.post("/api/scraper/start")
async def api_start_scraper(request: Request):
    """Start scraping run with user-entered parameters."""
    service = get_scraper_service()
    try:
        body = await request.json()
        run_config = RunConfig(
            country=body.get("country", "US"),
            query=body.get("query", "AI Developer"),
            max_pages=int(body.get("max_pages", 3)),
            location_type=body.get("location_type", "all"),
            parser_engine=body.get("parser_engine", settings.scraper_parser_engine),
        )

        session_id = await service.start(run_config)
        return {"status": "started", "session_id": session_id}

    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        logger.error("Failed to start scraper: {}", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/scraper/stop")
async def api_stop_scraper():
    """Stop running scraper."""
    get_scraper_service().stop()
    return {"status": "stopping"}


@router.get("/api/leads")
async def api_get_leads(
    search: str = Query(default=""),
    page_size: int = Query(default=1000, ge=1, le=5000),
):
    """Return scraped job leads for direct rendering."""
    service = get_scraper_service()
    leads = service.get_results()

    if search:
        sq = search.lower()
        leads = [
            j for j in leads
            if sq in j.job_title.lower() or sq in j.company.lower() or sq in j.location.lower()
        ]

    def serialize(j):
        return {
            "id": str(j.id),
            "job_title": j.job_title,
            "company": j.company,
            "location_remote_type": j.location_remote_type,
            "location": j.location,
            "country": j.country,
            "role": j.search_query,
            "salary": j.salary_range,
            "industry": j.industry,
            "company_size": j.company_size,
            "remote_type": j.remote_type,
            "posted_date": j.posted_date.isoformat() if j.posted_date else j.posted_date_raw,
            "job_url": j.job_url,
        }

    return {
        "total": len(leads),
        "leads": [serialize(j) for j in leads],
    }


@router.get("/api/export/excel")
async def api_export_excel():
    """Download clean Excel workbook."""
    from app.excel.exporter import ExcelExporter

    service = get_scraper_service()
    leads = service.get_results()

    if not leads:
        raise HTTPException(status_code=400, detail="No job leads to export. Run a search first.")

    exporter = ExcelExporter()
    output_path = exporter.export(leads, output_dir=settings.output_dir)

    return FileResponse(
        path=str(output_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=output_path.name,
    )


@router.post("/api/export/sharepoint")
async def api_export_sharepoint():
    """Upload scraped job leads directly to SharePoint List via Graph API."""
    service = get_scraper_service()
    leads = service.get_results()

    if not leads:
        raise HTTPException(status_code=400, detail="No job leads to export. Run a search first.")

    try:
        inserted_count = await service.export_sharepoint()
        return {
            "status": "success",
            "message": f"Successfully exported {inserted_count} jobs to SharePoint List via Microsoft Graph API!",
            "count": inserted_count,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"SharePoint Export Error: {str(exc)}")


@router.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket):
    """WebSocket endpoint for real-time progress bar updates."""
    await ws_manager.connect(websocket)
    service = get_scraper_service()

    async def broadcast_progress(progress):
        await ws_manager.send_progress(progress)

    service.add_progress_callback(
        lambda p: asyncio.create_task(broadcast_progress(p))
    )

    try:
        await ws_manager.send_progress(service.get_progress())
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
