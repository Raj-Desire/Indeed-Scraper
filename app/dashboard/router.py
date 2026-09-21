"""
FastAPI Router — Simple Scraper Application
=============================================
Serves the single-page HTML application and JSON API endpoints.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config.constants import COMMON_COUNTRIES
from app.config.settings import get_settings
from app.dashboard.websocket import ws_manager
from app.models.scraper import RunConfig
from app.services.dice_service import get_dice_service
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


@router.get("/api/scraper/progress")
async def api_get_scraper_progress():
    """Return live progress snapshot for REST polling fallback."""
    service = get_scraper_service()
    return service.get_progress().model_dump()


def _serialize_job(j):
    return {
        "id": str(j.id),
        "job_title": j.job_title,
        "company": j.company,
        "location_remote_type": j.location_remote_type,
        "location": j.location,
        "country": j.country,
        "role": j.search_query,
        "lead_source": getattr(j, "lead_source", "Indeed"),
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
        "outreach_email_subject": j.outreach_email_subject,
        "outreach_email_body": j.outreach_email_body,
        "outreach_linkedin_variants": j.outreach_linkedin_variants or [],
        "outreach_linkedin_message": j.outreach_linkedin_message,
    }


@router.post("/api/jobs/manual-evaluate")
async def api_manual_evaluate(request: Request):
    """
    Manually evaluate a job description: field extraction+scoring and outreach
    drafting are independent of each other (both only need the job description +
    KB context), so they run as two CONCURRENT LLM calls via asyncio.gather()
    instead of 3 sequential calls. Measured: the Azure deployment genuinely
    processes concurrent requests in parallel (wall time ~= max(call1, call2),
    not their sum), so this cuts latency roughly in half versus running them
    one after another, without the extra generation time a single giant
    "extract everything in one JSON" call would need.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    job_description = (body.get("job_description") or "").strip()
    if not job_description:
        raise HTTPException(status_code=422, detail="Job description is required")

    import asyncio

    from app.knowledge_base.azure_search import get_knowledge_base
    from app.matching.jd_parser import parse_job_description_with_ai
    from app.matching.llm_matcher import build_kb_context, get_llm_matcher, reconcile_skills_and_score
    from app.matching.outreach_generator import build_email_body, generate_outreach

    service = get_scraper_service()

    # Single KB retrieval, shared by both concurrent LLM calls below and by the
    # post-hoc skill reconciliation (previously fetched a second time, redundantly,
    # inside the now-removed separate MatchService call).
    kb_chunks = []
    try:
        kb_chunks = await get_knowledge_base().search(job_description, top_k=3)
    except Exception as kb_err:
        logger.warning("KB retrieval failed for manual evaluate, continuing without context: {}", kb_err)
    kb_context = build_kb_context(kb_chunks)

    # These two calls are independent (neither needs the other's output) and use
    # the same shared LLM client, so they run concurrently rather than sequentially.
    parsed, outreach = await asyncio.gather(
        parse_job_description_with_ai(job_description, kb_chunks=kb_chunks),
        generate_outreach(
            job_title=(body.get("job_title") or "").strip(),
            company=(body.get("company") or "").strip(),
            job_description=job_description,
            kb_context=kb_context,
            matcher=get_llm_matcher(),
        ),
    )

    reconciled_matched, reconciled_missing, reconciled_score, reconciled_reason = reconcile_skills_and_score(
        parsed.get("matched_skills") or [],
        parsed.get("missing_skills") or [],
        parsed.get("match_score"),
        kb_context,
        job_description[:2000],
        parsed.get("match_reason") or "",
    )

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

    company = (body.get("company") or "").strip() or (parsed.get("company") or "")
    location = (body.get("location") or "").strip() or (parsed.get("country") or "Remote")
    remote_type_str = (body.get("remote_type") or "").strip() or location

    try:
        # skip_match=True: match_score/matched_skills/missing_skills/match_reason are
        # already computed above (reconciled from the single consolidated LLM call),
        # so this must NOT trigger its own separate KB search + LLM scoring call.
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
            skip_match=True,
        )

        job.matched_skills = reconciled_matched
        job.missing_skills = reconciled_missing
        job.match_score = reconciled_score
        job.match_reason = reconciled_reason

        # Rebuild the email body using the outreach call's connective sentences
        # (opening_line/alignment_paragraph) but the EXTRACTION branch's reconciled
        # skill list, since the two calls ran concurrently and generate_outreach()
        # didn't have the final reconciled skills yet when it built its own body.
        job.outreach_email_subject = outreach.get("email_subject", "")
        job.outreach_email_body = build_email_body(
            parsed.get("contact_name", ""),
            outreach.get("opening_line", ""),
            outreach.get("alignment_paragraph", ""),
            reconciled_matched,
        )
        job.outreach_linkedin_variants = outreach.get("linkedin_variants", [])
        job.outreach_linkedin_message = (outreach.get("linkedin_variants") or [""])[0]

        return {
            "status": "success",
            "lead": _serialize_job(job),
            "parsed_fields": {
                "job_title": job.job_title,
                "company": job.company,
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


@router.post("/api/jobs/{lead_id}/generate-outreach")
async def api_generate_outreach(lead_id: str):
    """
    On-demand outreach draft generation for a scraped (or manual) lead already in memory.
    Kept separate from bulk scraping/evaluation so it's only ever run for leads the user
    is actually about to act on, not automatically for every scraped result.
    """
    service = get_scraper_service()
    job = next((j for j in service._results if str(j.id) == str(lead_id)), None)
    if not job:
        raise HTTPException(status_code=404, detail="Lead not found")

    from app.knowledge_base.azure_search import get_knowledge_base
    from app.matching.llm_matcher import build_kb_context
    from app.matching.outreach_generator import generate_outreach

    kb_context = ""
    if job.job_description:
        try:
            kb_chunks = await get_knowledge_base().search(job.job_description, top_k=3)
            kb_context = build_kb_context(kb_chunks)
        except Exception as kb_err:
            logger.warning("KB retrieval failed for on-demand outreach (lead {}): {}", lead_id, kb_err)

    try:
        outreach = await generate_outreach(
            job_title=job.job_title,
            company=job.company,
            job_description=job.job_description,
            matched_skills=job.matched_skills,
            missing_skills=job.missing_skills,
            kb_context=kb_context,
        )
    except Exception as exc:
        logger.error("On-demand outreach generation failed for lead {}: {}", lead_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))

    job.outreach_email_subject = outreach.get("email_subject", "")
    job.outreach_email_body = outreach.get("email_body", "")
    job.outreach_linkedin_variants = outreach.get("linkedin_variants", [])
    job.outreach_linkedin_message = (outreach.get("linkedin_variants") or [""])[0]

    return {"status": "success", "lead": _serialize_job(job)}


@router.post("/api/jobs/generate-outreach-batch")
async def api_generate_outreach_batch(request: Request):
    """
    Generate outreach drafts (email + LinkedIn) for several scraped leads in one click,
    instead of opening each lead's modal one at a time. Each lead's draft is generated
    concurrently (capped) and saved onto the in-memory job immediately, exactly like the
    single-lead endpoint, so a later "Sync to SharePoint" call already carries the
    Outreach_x0020_Email / Linkedin_x0020_message fields with no extra step.
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    lead_ids = data.get("lead_ids") if isinstance(data, dict) else None
    if not lead_ids or not isinstance(lead_ids, list):
        raise HTTPException(status_code=400, detail="lead_ids (non-empty list) is required")

    service = get_scraper_service()
    id_set = {str(i) for i in lead_ids}
    jobs = [j for j in service._results if str(j.id) in id_set]
    if not jobs:
        raise HTTPException(status_code=404, detail="No matching leads found")

    from app.knowledge_base.azure_search import get_knowledge_base
    from app.matching.llm_matcher import build_kb_context
    from app.matching.outreach_generator import generate_outreach

    semaphore = asyncio.Semaphore(5)

    async def _generate_for_job(job):
        async with semaphore:
            kb_context = ""
            if job.job_description:
                try:
                    kb_chunks = await get_knowledge_base().search(job.job_description, top_k=3)
                    kb_context = build_kb_context(kb_chunks)
                except Exception as kb_err:
                    logger.warning("KB retrieval failed for batch outreach (lead {}): {}", job.id, kb_err)

            try:
                outreach = await generate_outreach(
                    job_title=job.job_title,
                    company=job.company,
                    job_description=job.job_description,
                    matched_skills=job.matched_skills,
                    missing_skills=job.missing_skills,
                    kb_context=kb_context,
                )
            except Exception as exc:
                logger.error("Batch outreach generation failed for lead {}: {}", job.id, exc)
                return str(job.id), False

            job.outreach_email_subject = outreach.get("email_subject", "")
            job.outreach_email_body = outreach.get("email_body", "")
            job.outreach_linkedin_variants = outreach.get("linkedin_variants", [])
            job.outreach_linkedin_message = (outreach.get("linkedin_variants") or [""])[0]
            succeeded = bool(job.outreach_email_body)
            return str(job.id), succeeded

    results = await asyncio.gather(*(_generate_for_job(job) for job in jobs))
    succeeded_ids = [lid for lid, ok in results if ok]
    failed_ids = [lid for lid, ok in results if not ok]

    return {
        "status": "success",
        "generated": len(succeeded_ids),
        "failed": failed_ids,
        "leads": [_serialize_job(j) for j in jobs],
    }


@router.post("/api/jobs/{lead_id}/update-outreach")
async def api_update_outreach(lead_id: str, request: Request):
    """Persist user edits to a lead's outreach email/LinkedIn message before syncing to SharePoint."""
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    service = get_scraper_service()
    job = next((j for j in service._results if str(j.id) == str(lead_id)), None)
    if not job:
        raise HTTPException(status_code=404, detail="Lead not found")

    if "email_subject" in data:
        job.outreach_email_subject = (data.get("email_subject") or "").strip()
    if "email_body" in data:
        job.outreach_email_body = (data.get("email_body") or "").strip()
    if "linkedin_message" in data:
        job.outreach_linkedin_message = (data.get("linkedin_message") or "").strip()

    return {"status": "success", "lead": _serialize_job(job)}


@router.post("/api/leads/update-manual")
async def api_update_manual_lead(request: Request):
    """Update an existing in-memory lead when user edits title, country, salary, etc. in manual mode."""
    try:
        data = await request.json()
        lead_id = data.get("id")
        title = (data.get("title") or "").strip()
        company = (data.get("company") or "").strip()
        country = (data.get("country") or "").strip()
        salary = (data.get("salary") or "").strip()
        experience = (data.get("experience") or "").strip()
        notes = (data.get("notes") or "").strip()
        tech = data.get("technology")

        service = get_scraper_service()
        target = None
        if lead_id:
            target = next((j for j in service._results if str(j.id) == str(lead_id)), None)
        if not target and service._results:
            target = next((j for j in service._results if j.search_query == "Manual Entry"), None)

        if target:
            if title:
                target.job_title = title
            if company:
                target.company = company
            if country:
                target.country = country
                target.location = country
            if salary:
                target.salary_range = salary
            if experience:
                target.experience = experience
            if notes:
                target.job_summary = notes
            if tech is not None and isinstance(tech, list):
                target.matched_skills = tech
            logger.info("Updated in-memory manual lead '{}' ({})", target.job_title, target.country)

        return {"status": "success", "lead": _serialize_job(target) if target else None}
    except Exception as exc:
        logger.error("Failed to update manual lead: {}", exc)
        return {"status": "error", "detail": str(exc)}


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
async def api_export_excel(selected_ids: Optional[str] = Query(default=None)):
    """Download clean Excel workbook. Supports filtering by selected_ids comma-separated string."""
    from app.excel.exporter import ExcelExporter

    service = get_scraper_service()
    leads = service.get_results()

    if not leads:
        raise HTTPException(status_code=400, detail="No job leads to export. Run a search first.")

    if selected_ids and isinstance(selected_ids, str):
        id_set = {i.strip() for i in selected_ids.split(",") if i.strip()}
        if id_set:
            leads = [j for j in leads if str(j.id) in id_set]

    if not leads:
        raise HTTPException(status_code=400, detail="No selected job leads match to export.")

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
        filename=output_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/api/export/excel")
async def api_export_excel_post(request: Request):
    """Download clean Excel workbook with JSON payload containing selected_ids."""
    from app.excel.exporter import ExcelExporter

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    service = get_scraper_service()
    leads = service.get_results()

    if not leads:
        raise HTTPException(status_code=400, detail="No job leads to export. Run a search first.")

    selected_ids = body.get("selected_ids")
    if selected_ids and isinstance(selected_ids, list):
        id_set = {str(i) for i in selected_ids}
        leads = [j for j in leads if str(j.id) in id_set]

    if not leads:
        raise HTTPException(status_code=400, detail="No selected job leads match to export.")

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

    return FileResponse(
        path=str(output_path),
        filename=output_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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
                if payload.company:
                    top_job.company = payload.company
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
                if payload.outreach_email_subject:
                    top_job.outreach_email_subject = payload.outreach_email_subject
                if payload.outreach_email_body:
                    top_job.outreach_email_body = payload.outreach_email_body
                if payload.outreach_linkedin_message:
                    top_job.outreach_linkedin_message = payload.outreach_linkedin_message

        return {
            "status": "success",
            "message": "Opportunity successfully created in SharePoint list.",
            "data": res,
        }
    except Exception as exc:
        logger.error("Failed to add opportunity to SharePoint: {}", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/sharepoint/batch-add-opportunity")
async def api_sharepoint_batch_add_opportunity(request: Request):
    """Batch add reviewed Opportunities directly to SharePoint List using the Opportunity Tracker schema."""
    from app.models.opportunity import OpportunityPayload
    from app.sharepoint.graph_exporter import GraphSharePointExporter
    from app.models.job import JobPosting, RemoteType
    from datetime import datetime
    from app.models.scraper import IST

    try:
        body = await request.json()
        raw_opps = body if isinstance(body, list) else body.get("opportunities", [])
        if not raw_opps:
            raise HTTPException(status_code=400, detail="No opportunities provided in request payload.")

        payloads = [OpportunityPayload(**opp) for opp in raw_opps]
        exporter = GraphSharePointExporter()
        opp_dicts = [p.model_dump() for p in payloads]
        res = await exporter.export_opportunities(opp_dicts)

        # Update in-memory scraper leads with all staged opportunities
        service = get_scraper_service()
        for p in reversed(payloads):
            # Check if this opportunity already exists in _results by lead_id or job_title
            existing_match = None
            if p.lead_id:
                existing_match = next((j for j in service._results if str(j.id) == str(p.lead_id)), None)
            if not existing_match:
                existing_match = next((j for j in service._results if j.job_title == p.title and j.search_query == "Manual Entry"), None)
            if existing_match:
                existing_match.job_title = p.title
                existing_match.company = p.company or existing_match.company
                existing_match.country = p.country or existing_match.country
                existing_match.location = p.country or existing_match.location
                existing_match.salary_range = p.salary_range or existing_match.salary_range
                existing_match.experience = p.experience_criteria or existing_match.experience
                existing_match.industry = p.industry or existing_match.industry
                existing_match.job_url = p.website or existing_match.job_url
                if p.technology:
                    existing_match.matched_skills = p.technology
                if p.notes:
                    existing_match.job_summary = p.notes
                if p.job_requirement:
                    existing_match.job_description = p.job_requirement
                if p.outreach_email_subject:
                    existing_match.outreach_email_subject = p.outreach_email_subject
                if p.outreach_email_body:
                    existing_match.outreach_email_body = p.outreach_email_body
                if p.outreach_linkedin_message:
                    existing_match.outreach_linkedin_message = p.outreach_linkedin_message
            else:
                new_job = JobPosting(
                    job_title=p.title or "Untitled Role",
                    company=p.company or "",
                    location=p.country or "Remote",
                    country=p.country or "US",
                    job_url=p.website or "",
                    salary_range=p.salary_range or "Not listed",
                    experience=p.experience_criteria or "Not specified",
                    job_description=p.job_requirement or "",
                    remote_type=RemoteType.FULLY_REMOTE,
                    search_query="Manual Entry",
                    posted_date_raw="Just now",
                    posted_date=datetime.now(tz=IST),
                    match_score=p.matching_score,
                    matched_skills=p.technology if p.technology else (p.matching_skills if isinstance(p.matching_skills, list) else []),
                    missing_skills=p.missing_skills if isinstance(p.missing_skills, list) else [],
                    match_reason=p.matching_reason or "",
                    job_summary=p.notes or "",
                    industry=p.industry or "IT",
                    outreach_email_subject=p.outreach_email_subject or "",
                    outreach_email_body=p.outreach_email_body or "",
                    outreach_linkedin_message=p.outreach_linkedin_message or "",
                )
                service._results.insert(0, new_job)

        success_count = res.get("success_count", res.get("count", len(payloads)))
        total_count = res.get("total", len(payloads))

        return {
            "status": "success",
            "count": success_count,
            "total": total_count,
            "message": f"Successfully created {success_count}/{total_count} opportunities in SharePoint!",
            "data": res,
        }
    except Exception as exc:
        logger.error("Failed to batch add opportunities to SharePoint: {}", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/export/sharepoint")
async def api_export_sharepoint(request: Request):
    """Upload scraped job leads directly to SharePoint List via Graph API. Supports filtering by selected_ids."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    service = get_scraper_service()
    leads = service.get_results()

    if not leads:
        raise HTTPException(status_code=400, detail="No job leads to export. Run a search first.")

    selected_ids = body.get("selected_ids") if isinstance(body, dict) else None
    owner = body.get("owner") if isinstance(body, dict) else None

    try:
        inserted_count = await service.export_sharepoint(selected_ids=selected_ids, owner=owner)
        return {
            "status": "success",
            "message": f"Successfully exported {inserted_count} jobs to SharePoint List via Microsoft Graph API!",
            "count": inserted_count,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"SharePoint Export Error: {str(exc)}")


DICE_MAX_SEARCH_COMBINATIONS = 15


@router.post("/api/dice/search")
async def api_dice_search(request: Request):
    """Search Dice.com via its official MCP server for every (keyword, country)
    combination, score results via the KB/LLM matching pipeline, and return them
    for display. Accepts either `keywords` (list) or a singular `keyword` (str,
    kept for backward compatibility); same for `countries` (list) vs `location`
    (str, a freeform city/state used only when no countries are selected)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    keywords = body.get("keywords")
    if not isinstance(keywords, list) or not keywords:
        single_keyword = (body.get("keyword") or "").strip()
        keywords = [single_keyword] if single_keyword else []
    keywords = [k.strip() for k in keywords if isinstance(k, str) and k.strip()]
    if not keywords:
        raise HTTPException(status_code=422, detail="At least one keyword is required")

    countries = body.get("countries")
    if not isinstance(countries, list):
        countries = []
    countries = [c.strip() for c in countries if isinstance(c, str) and c.strip()]

    combo_count = len(keywords) * max(len(countries), 1)
    if combo_count > DICE_MAX_SEARCH_COMBINATIONS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Too many keyword × country combinations ({combo_count}). "
                f"Narrow your selection to {DICE_MAX_SEARCH_COMBINATIONS} or fewer combinations."
            ),
        )

    jobs_per_page = body.get("jobs_per_page")
    if jobs_per_page is not None:
        try:
            jobs_per_page = min(max(int(jobs_per_page), 1), 50)
        except (TypeError, ValueError):
            jobs_per_page = None

    filters = {
        k: v for k, v in {
            "location": body.get("location"),
            "radius": body.get("radius"),
            "radius_unit": body.get("radius_unit"),
            "workplace_types": body.get("workplace_types"),
            "employment_types": body.get("employment_types"),
            "posted_date": body.get("posted_date"),
            "easy_apply": body.get("easy_apply"),
            "willing_to_sponsor": body.get("willing_to_sponsor"),
            "jobs_per_page": jobs_per_page,
        }.items() if v is not None
    }

    service = get_dice_service()
    try:
        new_jobs = await service.search_multi(keywords, countries, **filters)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Dice search failed: {exc}")

    leads = service.get_results()
    leads.sort(key=lambda j: (j.match_score is not None, j.match_score or 0), reverse=True)
    return {
        "total": len(leads),
        "new_count": len(new_jobs),
        "combos": combo_count,
        "leads": [_serialize_job(j) for j in leads],
    }


@router.get("/api/dice/results")
async def api_dice_results():
    """Return current Dice search results."""
    service = get_dice_service()
    leads = service.get_results()
    leads.sort(key=lambda j: (j.match_score is not None, j.match_score or 0), reverse=True)
    return {"total": len(leads), "leads": [_serialize_job(j) for j in leads]}


@router.post("/api/dice/clear")
async def api_dice_clear():
    """Clear all Dice search results from the dashboard."""
    service = get_dice_service()
    service.clear_results()
    return {"status": "cleared", "total": 0}


@router.post("/api/dice/export/sharepoint")
async def api_dice_export_sharepoint(request: Request):
    """Upload Dice job leads to SharePoint List via Graph API. Supports filtering
    by selected_ids."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    service = get_dice_service()
    leads = service.get_results()

    if not leads:
        raise HTTPException(status_code=400, detail="No Dice job leads to export. Run a search first.")

    selected_ids = body.get("selected_ids") if isinstance(body, dict) else None
    owner = body.get("owner") if isinstance(body, dict) else None

    try:
        inserted_count = await service.export_sharepoint(selected_ids=selected_ids, owner=owner)
        return {
            "status": "success",
            "message": f"Successfully exported {inserted_count} Dice jobs to SharePoint List via Microsoft Graph API!",
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
