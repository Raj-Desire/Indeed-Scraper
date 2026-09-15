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


@router.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    """Health check endpoint for cloud deployment platforms (Render, Heroku, etc.)."""
    return {"status": "ok"}


@router.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def home_page(request: Request):
    """Serve the single-page application interface."""
    countries = [{"name": c.name, "code": c.code} for c in COMMON_COUNTRIES]
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"countries": countries},
    )


@router.post("/api/scraper/start")
async def api_start_scraper(request: Request):
    """Start scraping run with user-entered parameters."""
    service = get_scraper_service()
    try:
        body = await request.json()
        countries_raw = body.get("countries")
        if not countries_raw:
            c_single = body.get("country", "US")
            countries_raw = [c_single] if isinstance(c_single, str) else c_single

        queries_raw = body.get("queries")
        if not queries_raw:
            q_single = body.get("query", "SharePoint")
            queries_raw = [q.strip() for q in q_single.split(",") if q.strip()] if isinstance(q_single, str) else q_single

        run_config = RunConfig(
            countries=countries_raw,
            queries=queries_raw,
            max_pages=int(body.get("max_pages", 1)),
            location_type=body.get("location_type", "all"),
            fromage=str(body.get("fromage", "all")),
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
    await get_scraper_service().stop()
    return {"status": "stopped"}


def _serialize_job(j):
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
        "experience": j.experience or "Not specified",
        "job_description": j.job_description or "",
        "remote_type": j.remote_type.value if hasattr(j.remote_type, "value") else str(j.remote_type or "Unknown"),
        "posted_date": j.posted_date.isoformat() if j.posted_date else j.posted_date_raw,
        "job_url": j.job_url,
        "match_score": j.match_score,
        "matched_skills": j.matched_skills or [],
        "missing_skills": j.missing_skills or [],
        "match_reason": j.match_reason or "",
        "job_summary": j.summary,
        "summary": j.summary,
    }


@router.post("/api/jobs/manual-evaluate")
async def api_manual_evaluate(request: Request):
    """Manually evaluate a job description using LLM Knowledge Base matching."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    job_description = (body.get("job_description") or "").strip()
    if not job_description:
        raise HTTPException(status_code=422, detail="Job description is required")

    from app.matching.jd_parser import parse_job_description_with_ai

    service = get_scraper_service()
    kb_chunks = []
    if service._match_service and getattr(service._match_service, "_kb", None):
        try:
            kb_chunks = await service._match_service._kb.retrieve(job_description, top_k=3)
        except Exception:
            pass

    parsed = await parse_job_description_with_ai(job_description, kb_chunks=kb_chunks)

    job_title = (body.get("job_title") or "").strip()
    if not job_title or job_title in ["Untitled Role", "Untitled Opportunity"]:
        job_title = parsed.get("job_title") or parsed.get("title") or "Untitled Opportunity"

    country = (body.get("country") or "").strip()
    if not country or country == "US":
        country = parsed.get("country") or "US"

    job_url = (body.get("job_url") or "").strip() or parsed.get("job_url", "") or parsed.get("website", "")
    salary_range = (body.get("salary_range") or "").strip()
    if not salary_range or salary_range == "Not listed":
        salary_range = parsed.get("salary_range") or ""

    experience = (body.get("experience") or "").strip()
    if not experience or experience == "Not specified":
        experience = parsed.get("experience") or ""

    company = (body.get("company") or "").strip()
    location = (body.get("location") or "").strip() or (parsed.get("country") or "Remote")
    remote_type_str = (body.get("remote_type") or "").strip() or location

    try:
        job = await service.evaluate_manual_job(
            job_title=job_title,
            company=company,
            job_description=job_description,
            location=location,
            country=country,
            job_url=job_url,
            salary_range=salary_range or "Not listed",
            experience=experience or "Not specified",
            remote_type_str=remote_type_str,
        )

        # If the AI extractor calculated richer skill matches & score, enrich the job
        if parsed.get("matched_skills") and not job.matched_skills:
            job.matched_skills = parsed.get("matched_skills")
        if parsed.get("missing_skills") and not job.missing_skills:
            job.missing_skills = parsed.get("missing_skills")
        if parsed.get("match_score") is not None and (job.match_score is None or job.match_score == 0):
            job.match_score = parsed.get("match_score")
        if parsed.get("match_reason") and not job.match_reason:
            job.match_reason = parsed.get("match_reason")

        return {
            "status": "success",
            "lead": _serialize_job(job),
            "parsed_fields": {
                "job_title": job.job_title,
                "country": country,
                "job_url": job.job_url,
                "salary_range": salary_range,
                "estimated_value": parsed.get("estimated_value") if parsed.get("estimated_value") is not None else "",
                "currency_code": parsed.get("currency_code") or "USD",
                "experience": experience,
                "owner": parsed.get("owner") or "Meet",
                "lead_source": parsed.get("lead_source") or "Indeed",
                "industry": parsed.get("industry") or "IT",
                "priority": parsed.get("priority") or "Medium",
                "status": parsed.get("status") or "New",
                "email": parsed.get("email", ""),
                "phone": parsed.get("phone", ""),
                "contact_name": parsed.get("contact_name", ""),
                "technologies": parsed.get("technologies") or parsed.get("technology", []),
                "extra_parameters": parsed.get("extra_parameters", []),
                "notes": parsed.get("notes", ""),
                "match_score": job.match_score,
                "matched_skills": job.matched_skills or [],
                "missing_skills": job.missing_skills or [],
                "match_reason": job.match_reason or "",
            },
        }
    except Exception as exc:
        logger.error("Manual job evaluation failed: {}", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/jobs/clear")
async def api_clear_jobs():
    """Clear all scraped or manually entered job leads from dashboard."""
    service = get_scraper_service()
    service.clear_results()
    return {"status": "cleared", "total": 0}


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

    # Sort leads by match_score descending (highest score on top, unranked at bottom)
    leads.sort(key=lambda j: (j.match_score is not None, j.match_score or 0), reverse=True)

    return {
        "total": len(leads),
        "leads": [_serialize_job(j) for j in leads],
    }


@router.get("/api/export/excel")
async def api_export_excel():
    """Download clean Excel workbook. Also ensures email is dispatched to sender/recipients if not sent yet."""
    from app.excel.exporter import ExcelExporter

    service = get_scraper_service()
    leads = service.get_results()

    if not leads:
        raise HTTPException(status_code=400, detail="No job leads to export. Run a search first.")

    session = service.get_session()
    cfg = session.run_config if session else None

    exporter = ExcelExporter()
    output_path = exporter.export(
        leads,
        output_dir=settings.output_dir,
        query=cfg.query if cfg else "",
        countries=cfg.countries if cfg else [],
        fromage=cfg.fromage if cfg else "all",
        location_type=cfg.location_type if cfg else "all",
    )

    # Check if email notification was already sent for this batch; if not, dispatch now
    if not service.is_email_sent():
        logger.info("Download Excel clicked: Email has not been sent yet. Dispatching email report to sender and recipients...")
        try:
            sent = await service.send_email_notification(
                excel_path=str(output_path),
                query=cfg.query if cfg else "",
                queries=getattr(cfg, "queries", None) if cfg else None,
                countries=cfg.countries if cfg else [],
                fromage=cfg.fromage if cfg else "1",
                location_type=cfg.location_type if cfg else "remote",
                status="completed",
            )
            if sent:
                logger.info("Download Excel: Email successfully dispatched to sender and recipients.")
            else:
                logger.warning("Download Excel: Email notification returned False (disabled or failed).")
        except Exception as mail_err:
            logger.error("Download Excel: Error dispatching email notification: {}", mail_err)
    else:
        logger.info("Download Excel clicked: Email was already sent for this run.")

    return FileResponse(
        path=str(output_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=output_path.name,
    )


@router.post("/api/sharepoint/add-opportunity")
async def api_sharepoint_add_opportunity(request: Request):
    """Add a reviewed Opportunity directly to SharePoint List using the Opportunity Tracker schema."""
    from app.models.opportunity import OpportunityPayload
    from app.sharepoint.graph_exporter import GraphSharePointExporter
    try:
        body = await request.json()
        payload = OpportunityPayload(**body)
        exporter = GraphSharePointExporter()
        res = await exporter.export_opportunity(payload.model_dump())

        # Update in-memory scraper results so Excel export and leads endpoint match the newly edited opportunity
        service = get_scraper_service()
        results = service.get_results()
        if results:
            top_job = results[0]
            if top_job.search_query == "Manual Entry" or len(results) == 1:
                if payload.title:
                    top_job.job_title = payload.title
                if payload.country:
                    top_job.country = payload.country
                    top_job.location = payload.country
                if payload.website:
                    top_job.job_url = payload.website
                if payload.salary_range:
                    top_job.salary_range = payload.salary_range
                if payload.experience_criteria:
                    top_job.experience = payload.experience_criteria
                if payload.industry:
                    top_job.industry = payload.industry
                if payload.matching_skills:
                    if isinstance(payload.matching_skills, list):
                        top_job.matched_skills = payload.matching_skills
                    elif isinstance(payload.matching_skills, str) and payload.matching_skills.strip():
                        top_job.matched_skills = [s.strip() for s in payload.matching_skills.split(",") if s.strip()]
                if payload.notes:
                    top_job.job_summary = payload.notes
                if payload.job_requirement:
                    top_job.job_description = payload.job_requirement

        return {
            "status": "success",
            "message": "Opportunity successfully created in SharePoint list.",
            "data": res,
        }
    except Exception as exc:
        logger.error("Failed to add opportunity to SharePoint: {}", exc)
        raise HTTPException(status_code=500, detail=str(exc))


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
