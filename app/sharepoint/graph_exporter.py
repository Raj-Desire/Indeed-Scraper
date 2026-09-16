"""
Microsoft Graph API SharePoint Exporter
=======================================
Direct, clean integration with SharePoint List via Microsoft Graph API and MSAL.
Reads all authentication & endpoint credentials strictly from environment settings (.env).
Supports full 'Opportunity Tracker' list schema (30 columns) and legacy job posting lists.
"""

from __future__ import annotations

import html as _html
from datetime import datetime, timezone
from typing import Any, Optional
import httpx
import msal

from app.config.constants import score_to_priority
from app.config.settings import get_settings
from app.models.job import JobPosting
from app.utils.logger import logger

# The Opportunity Tracker's 'Country' and 'Industry' columns are strict SharePoint
# Choice fields (allowTextEntry disabled) - Graph API rejects the ENTIRE item with an
# opaque "generalException" if the value isn't an exact match for one of these choices.
# The scraper supports dozens of countries and free-text industry detection, so raw
# scraped values (e.g. ISO codes like "IN"/"DE", or "Information Technology") must be
# normalized to one of these exact choice strings before being sent, or omitted.
SHAREPOINT_COUNTRY_CHOICES = {
    "US": "US",
    "ZA": "South Africa",
    "GB": "UK",
}

SHAREPOINT_INDUSTRY_CHOICES = {
    "IT": "IT",
    "INFORMATION TECHNOLOGY": "IT",
    "CONSTRUCTION": "Construction",
    "ENGINEERING & CONSTRUCTION": "Construction",
    "LEGAL": "Legal",
    "HEALTHCARE": "Healthcare",
    "HEALTHCARE & LIFE SCIENCES": "Healthcare",
    "LOGISTICS": "Logistics",
    "MANUFACTURING & LOGISTICS": "Logistics",
}


def _normalize_sharepoint_country(country: Optional[str]) -> Optional[str]:
    """Map a scraped ISO country code to one of the SharePoint 'Country' choices, or None if unsupported."""
    if not country:
        return None
    return SHAREPOINT_COUNTRY_CHOICES.get(country.strip().upper())


def _normalize_sharepoint_industry(industry: Optional[str]) -> str:
    """Map a scraped/detected industry label to one of the SharePoint 'Industry' choices, defaulting to 'IT'."""
    if not industry:
        return "IT"
    return SHAREPOINT_INDUSTRY_CHOICES.get(industry.strip().upper(), "IT")


# 'Job_x0020_Requirement', 'Matching_x0020_Reason', 'Matching_x0020_Skills' and
# 'Missing_x0020_Skills' are all Rich Text (HTML) columns in the Opportunity Tracker
# list. Sending plain text with '\n' line breaks or '### heading' / '* bullet' markers
# doesn't render - HTML collapses bare whitespace and shows the literal '###'/'*'
# characters, which is why job descriptions were showing as one run-on line with
# stray '###' markers. These helpers build real HTML so the content renders correctly.

def _html_escape(text: Any) -> str:
    return _html.escape(str(text), quote=False)


def _structured_text_to_html(text: Optional[str]) -> str:
    """
    Convert the scraper's lightweight structured text (produced by
    _enrich_full_description: '### heading' lines, '• bullet' lines, and plain
    paragraphs) into real HTML - headings become <h3>, consecutive bullets become one
    <ul>, and other lines become <p> paragraphs.
    """
    if not text:
        return ""
    html_parts: list[str] = []
    bullet_buffer: list[str] = []

    def flush_bullets() -> None:
        if bullet_buffer:
            items = "".join(f"<li>{_html_escape(b)}</li>" for b in bullet_buffer)
            html_parts.append(f"<ul>{items}</ul>")
            bullet_buffer.clear()

    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("### "):
            flush_bullets()
            html_parts.append(f"<h3>{_html_escape(line[4:].strip())}</h3>")
        elif line.startswith("•"):
            bullet_buffer.append(line.lstrip("•").strip())
        else:
            flush_bullets()
            html_parts.append(f"<p>{_html_escape(line)}</p>")

    flush_bullets()
    return "".join(html_parts)


def _text_to_html_paragraphs(text: Optional[str]) -> str:
    """Wrap plain (possibly multi-line) text as escaped HTML paragraphs for a Rich Text column."""
    if not text:
        return ""
    paragraphs = [p.strip() for p in str(text).splitlines() if p.strip()]
    if not paragraphs:
        return ""
    return "".join(f"<p>{_html_escape(p)}</p>" for p in paragraphs)


def _skills_to_html_badges(skills: Any, badge_type: str = "matched") -> str:
    """
    Format a list of skills or comma-separated string into HTML pill/square badges
    that render in SharePoint Rich Text columns.
    """
    if not skills:
        return ""
    if isinstance(skills, str):
        if "<span" in skills or "<div" in skills:
            return skills
        skill_list = [s.strip() for s in skills.split(",") if s.strip()]
    elif isinstance(skills, (list, tuple, set)):
        skill_list = [str(s).strip() for s in skills if str(s).strip()]
    else:
        skill_list = [str(skills).strip()]

    if not skill_list:
        return ""

    if badge_type == "missing":
        style = (
            "box-sizing:border-box;border-width:1px;border-style:solid;border-color:rgb(254, 205, 211);"
            "display:inline-block;border-radius:0.375rem;background-color:rgb(255, 241, 242);"
            "padding:0.125rem 0.5rem;font-size:11px;font-weight:500;color:rgb(159, 18, 57);"
            "font-family:Inter, sans-serif;margin:2px 4px 2px 0;"
        )
    else:
        style = (
            "box-sizing:border-box;border-width:1px;border-style:solid;border-color:rgb(167, 243, 208);"
            "display:inline-block;border-radius:0.375rem;background-color:rgb(236, 253, 245);"
            "padding:0.125rem 0.5rem;font-size:11px;font-weight:500;color:rgb(6, 95, 70);"
            "font-family:Inter, sans-serif;margin:2px 4px 2px 0;"
        )

    badges = "".join(f'<span style="{style}">{_html_escape(s)}</span>' for s in skill_list)
    return badges


class GraphSharePointExporter:
    """Exports JobPosting and Opportunity records directly to a SharePoint List using Graph API."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def _acquire_token(self) -> str:
        """Acquire OAuth2 Access Token from Azure AD via MSAL using .env credentials."""
        tenant_id = self._settings.azure_tenant_id.strip()
        client_id = self._settings.azure_client_id.strip()
        client_secret = self._settings.azure_client_secret.strip()

        if not tenant_id or not client_id or not client_secret:
            raise ValueError("Azure AD Credentials missing in .env (AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET)")

        app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
        )
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" in result:
            return result["access_token"]
        raise PermissionError(f"Azure AD Auth Failed: {result.get('error_description')}")

    def build_opportunity_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Sanitize and format dictionary fields strictly matching SharePoint Opportunity Tracker schema.
        Handles Choice, MultiChoice (array of strings), Number, DateTime, and Note/Text fields.
        """
        fields: dict[str, Any] = {}

        # 1. Text & Note Fields

        # Job Title -> dedicated 'Job_x0020_Title' column. Our internal callers have always
        # passed the job/opportunity title under the 'title'/'Title' alias, so that alias is
        # kept pointing at the job title here - only the SharePoint OUTPUT column changes.
        job_title_val = data.get("job_title") or data.get("Job_x0020_Title") or data.get("title") or data.get("Title")
        if job_title_val:
            fields["Job_x0020_Title"] = str(job_title_val).strip()

        # Prospect/Company Name -> SharePoint's 'Title' column. The Opportunity Tracker list
        # displays this column's label as "Prospect/Company Name" even though its internal
        # name is 'Title', so the company name (not the job title) belongs here.
        if data.get("company") or data.get("Company"):
            fields["Title"] = str(data.get("company") or data.get("Company")).strip()

        if data.get("contact_name") or data.get("ContactName"):
            fields["ContactName"] = str(data.get("contact_name") or data.get("ContactName")).strip()
        if data.get("email") or data.get("Email"):
            fields["Email"] = str(data.get("email") or data.get("Email")).strip()
        if data.get("phone") or data.get("Phone"):
            fields["Phone"] = str(data.get("phone") or data.get("Phone")).strip()
        if data.get("notes") or data.get("Notes"):
            fields["Notes"] = str(data.get("notes") or data.get("Notes")).strip()
        if data.get("experience_criteria") or data.get("Experience_x0020_Criteria"):
            fields["Experience_x0020_Criteria"] = str(data.get("experience_criteria") or data.get("Experience_x0020_Criteria")).strip()
        if data.get("salary_range") or data.get("Salary_x0020_Range"):
            fields["Salary_x0020_Range"] = str(data.get("salary_range") or data.get("Salary_x0020_Range")).strip()
        if data.get("job_requirement") or data.get("Job_x0020_Requirement"):
            # Rich Text column - render as real HTML, not raw '### heading' / '\n' text.
            fields["Job_x0020_Requirement"] = _structured_text_to_html(
                data.get("job_requirement") or data.get("Job_x0020_Requirement")
            )
        if data.get("matching_reason") or data.get("Matching_x0020_Reason"):
            # Rich Text column - wrap as HTML paragraph(s).
            fields["Matching_x0020_Reason"] = _text_to_html_paragraphs(
                data.get("matching_reason") or data.get("Matching_x0020_Reason")
            )

        # Matched and Missing Skills (Formatted as styled HTML badges/square boxes)
        matched_skills = data.get("matching_skills") or data.get("Matching_x0020_Skills")
        if matched_skills:
            fields["Matching_x0020_Skills"] = _skills_to_html_badges(matched_skills, badge_type="matched")

        missing_skills = data.get("missing_skills") or data.get("Missing_x0020_Skills")
        if missing_skills:
            fields["Missing_x0020_Skills"] = _skills_to_html_badges(missing_skills, badge_type="missing")

        # 2. Choice Fields
        if data.get("country") or data.get("Country"):
            fields["Country"] = str(data.get("country") or data.get("Country")).strip()
        if data.get("industry") or data.get("Industry"):
            fields["Industry"] = str(data.get("industry") or data.get("Industry")).strip()
        if data.get("lead_source") or data.get("LeadSource"):
            fields["LeadSource"] = str(data.get("lead_source") or data.get("LeadSource")).strip()
        if data.get("owner") or data.get("Owner"):
            fields["Owner"] = str(data.get("owner") or data.get("Owner")).strip()
        if data.get("priority") or data.get("Priority"):
            fields["Priority"] = str(data.get("priority") or data.get("Priority")).strip()
        if data.get("status") or data.get("Status"):
            fields["Status"] = str(data.get("status") or data.get("Status")).strip()
        if data.get("currency_code") or data.get("CurrencyCode"):
            fields["CurrencyCode"] = str(data.get("currency_code") or data.get("CurrencyCode")).strip()
        if data.get("vp_approval_status") or data.get("VPApprovalStatus"):
            fields["VPApprovalStatus"] = str(data.get("vp_approval_status") or data.get("VPApprovalStatus")).strip()
        if data.get("outcome_reason") or data.get("OutcomeReason"):
            fields["OutcomeReason"] = str(data.get("outcome_reason") or data.get("OutcomeReason")).strip()

        # 3. MultiChoice Fields (Must be list of strings with Collection(Edm.String) @odata.type)
        technology = data.get("technology") or data.get("Technology")
        if technology:
            if isinstance(technology, list):
                tech_list = [str(t).strip() for t in technology if t]
            elif isinstance(technology, str) and technology.strip():
                tech_list = [t.strip() for t in technology.split(",") if t.strip()]
            else:
                tech_list = []
            if tech_list:
                fields["Technology@odata.type"] = "Collection(Edm.String)"
                fields["Technology"] = tech_list

        checklist = data.get("checklist") or data.get("Checklist")
        if checklist:
            if isinstance(checklist, list):
                chk_list = [str(c).strip() for c in checklist if c]
            elif isinstance(checklist, str) and checklist.strip():
                chk_list = [c.strip() for c in checklist.split(",") if c.strip()]
            else:
                chk_list = []
            if chk_list:
                fields["Checklist@odata.type"] = "Collection(Edm.String)"
                fields["Checklist"] = chk_list

        # 4. Number Fields
        score = data.get("matching_score") if "matching_score" in data else data.get("Matching_x0020_Score")
        if score is not None and score != "":
            try:
                num_score = float(score)
                # In SharePoint, Percentage columns store values as 0.0 - 1.0 (e.g. 0.75 for 75%).
                # If a value > 1.0 (e.g. 75) is sent, SharePoint scales it by 100 and displays 7,500 (7500%).
                # Dividing by 100 converts 75 to 0.75 so SharePoint renders '75%' or '75'.
                if num_score > 1.0:
                    num_score = round(num_score / 100.0, 4)
                fields["Matching_x0020_Score"] = num_score
            except (ValueError, TypeError):
                pass

        val = data.get("estimated_value") if "estimated_value" in data else data.get("EstimatedValue")
        if val is not None and val != "":
            try:
                fields["EstimatedValue"] = float(val)
            except (ValueError, TypeError):
                pass

        # 5. DateTime Fields (ISO 8601 YYYY-MM-DDTHH:MM:SSZ)
        now_date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
        date_added = data.get("date_added") or data.get("DateAdded")
        if date_added:
            if isinstance(date_added, datetime):
                fields["DateAdded"] = date_added.strftime("%Y-%m-%dT00:00:00Z")
            elif "T" in str(date_added):
                fields["DateAdded"] = str(date_added)
            else:
                fields["DateAdded"] = f"{str(date_added).strip()}T00:00:00Z"
        else:
            fields["DateAdded"] = now_date_str

        for dt_key, target_field in [
            ("next_follow_up_date", "NextFollow_x002d_upDate"),
            ("NextFollow_x002d_upDate", "NextFollow_x002d_upDate"),
            ("last_activity_date", "LastActivityDate"),
            ("LastActivityDate", "LastActivityDate"),
            ("due_date", "DueDate"),
            ("DueDate", "DueDate"),
        ]:
            dt_val = data.get(dt_key)
            if dt_val:
                if isinstance(dt_val, datetime):
                    fields[target_field] = dt_val.strftime("%Y-%m-%dT00:00:00Z")
                elif "T" in str(dt_val):
                    fields[target_field] = str(dt_val)
                else:
                    fields[target_field] = f"{str(dt_val).strip()}T00:00:00Z"

        # Job Link: dedicated field (internal name Job_x0020_Link). Accepts the same
        # aliases the job/opportunity link has been passed under historically
        # (website, job_url, ...) so both the manual-entry and auto-scraper paths
        # populate it without any caller changes.
        website_val = (
            data.get("job_link") or data.get("Job_x0020_Link")
            or data.get("website") or data.get("Website")
            or data.get("job_url") or data.get("Job_x0020_URL")
        )
        if website_val and str(website_val).strip() not in ["N/A", ""]:
            fields["Job_x0020_Link"] = str(website_val).strip()

        # Format Location into Notes if provided so no information is lost
        location_val = data.get("location_remote_type") or data.get("Location_x002f_RemoteType") or data.get("location") or data.get("Location")

        extra_note_parts = []
        if location_val and str(location_val).strip() not in ["N/A", "Not specified", ""] and f"Location: {str(location_val).strip()}" not in fields.get("Notes", ""):
            extra_note_parts.append(f"Location: {str(location_val).strip()}")

        if extra_note_parts:
            existing_notes = fields.get("Notes", "")
            extra_prefix = " | ".join(extra_note_parts)
            fields["Notes"] = f"{extra_prefix} | {existing_notes}" if existing_notes else extra_prefix

        return fields

    async def export_opportunity(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Create a single item in the SharePoint list using the Opportunity Tracker schema.
        Returns the created Graph API item metadata dictionary.
        """
        site_id = self._settings.sharepoint_site_id.strip()
        list_target = self._settings.sharepoint_list_id.strip() or self._settings.sharepoint_list_name.strip()

        if not site_id or not list_target:
            raise ValueError("SharePoint settings missing in .env (SP_SITE_ID / SHAREPOINT_SITE_ID, SP_LIST_ID / SP_LIST_NAME)")

        token = self._acquire_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        fields_dict = self.build_opportunity_fields(data)
        items_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{list_target}/items"

        payload = {"fields": fields_dict}
        log_title = fields_dict.get("Job_x0020_Title") or fields_dict.get("Title", "Untitled")
        logger.info("Posting Opportunity to SharePoint list '{}': {}", list_target, log_title)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(items_url, headers=headers, json=payload)
            if resp.status_code in [200, 201]:
                res_data = resp.json()
                logger.info("Opportunity '{}' created successfully (ID: {}).", log_title, res_data.get("id"))
                return res_data

            # If some fields are not recognized by a non-standard list schema, attempt graceful retry with core fields
            err_text = resp.text
            logger.warning("SharePoint insertion error ({}) for '{}': {}", resp.status_code, log_title, err_text)

            # Retry without non-standard fields that might trigger schema errors
            core_fields = {
                k: v for k, v in fields_dict.items()
                if k in [
                    "Title", "Job_x0020_Title", "Notes", "Country", "Industry", "LeadSource", "Owner",
                    "Priority", "Status", "CurrencyCode", "Job_x0020_Requirement",
                    "Matching_x0020_Score", "Matching_x0020_Skills", "Matching_x0020_Reason",
                    "Missing_x0020_Skills", "Salary_x0020_Range", "Experience_x0020_Criteria",
                    "Technology", "Technology@odata.type", "DateAdded", "Job_x0020_Link"
                ]
            }
            retry_resp = await client.post(items_url, headers=headers, json={"fields": core_fields})
            if retry_resp.status_code in [200, 201]:
                res_data = retry_resp.json()
                logger.info("Opportunity '{}' created on fallback attempt (ID: {}).", core_fields.get("Job_x0020_Title") or core_fields.get("Title"), res_data.get("id"))
                return res_data

            raise RuntimeError(f"SharePoint List Insert Failed ({resp.status_code}): {err_text}")

    async def export_opportunities(self, opportunities: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Batch create multiple items in the SharePoint list using the Opportunity Tracker schema.
        Reuses token and HTTP client session.
        Returns a summary dict with success_count, created_items, and errors.
        """
        if not opportunities:
            return {"success_count": 0, "total": 0, "items": [], "errors": []}

        site_id = self._settings.sharepoint_site_id.strip()
        list_target = self._settings.sharepoint_list_id.strip() or self._settings.sharepoint_list_name.strip()

        if not site_id or not list_target:
            raise ValueError("SharePoint settings missing in .env (SP_SITE_ID / SHAREPOINT_SITE_ID, SP_LIST_ID / SP_LIST_NAME)")

        token = self._acquire_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        items_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{list_target}/items"

        created_items = []
        errors = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            for idx, opp in enumerate(opportunities, 1):
                fields_dict = self.build_opportunity_fields(opp)
                title = fields_dict.get("Job_x0020_Title") or fields_dict.get("Title", f"Opportunity #{idx}")
                payload = {"fields": fields_dict}
                logger.info("Batch posting Opportunity {}/{}: '{}'", idx, len(opportunities), title)

                try:
                    resp = await client.post(items_url, headers=headers, json=payload)
                    if resp.status_code in [200, 201]:
                        res_data = resp.json()
                        created_items.append({"id": res_data.get("id"), "title": title, "status": "created"})
                        logger.info("Opportunity '{}' created in batch (ID: {}).", title, res_data.get("id"))
                        continue

                    # Fallback retry with core fields
                    core_fields = {
                        k: v for k, v in fields_dict.items()
                        if k in [
                            "Title", "Job_x0020_Title", "Notes", "Country", "Industry", "LeadSource", "Owner",
                            "Priority", "Status", "CurrencyCode", "Job_x0020_Requirement",
                            "Matching_x0020_Score", "Matching_x0020_Skills", "Matching_x0020_Reason",
                            "Missing_x0020_Skills", "Salary_x0020_Range", "Experience_x0020_Criteria",
                            "Technology", "Technology@odata.type", "DateAdded", "Job_x0020_Link"
                        ]
                    }
                    retry_resp = await client.post(items_url, headers=headers, json={"fields": core_fields})
                    if retry_resp.status_code in [200, 201]:
                        res_data = retry_resp.json()
                        created_items.append({"id": res_data.get("id"), "title": title, "status": "created_fallback"})
                        logger.info("Opportunity '{}' created on fallback (ID: {}).", title, res_data.get("id"))
                    else:
                        err_msg = f"Failed to insert '{title}' ({resp.status_code}): {resp.text}"
                        logger.error(err_msg)
                        errors.append({"title": title, "error": err_msg})
                except Exception as opp_err:
                    err_msg = f"Exception inserting '{title}': {str(opp_err)}"
                    logger.error(err_msg)
                    errors.append({"title": title, "error": err_msg})

        return {
            "success_count": len(created_items),
            "total": len(opportunities),
            "items": created_items,
            "errors": errors,
        }

    async def export_jobs(self, jobs: list[JobPosting], owner: Optional[str] = None) -> int:
        """
        Upload list of JobPosting objects directly to the SharePoint List.
        Maps all available job and AI evaluation fields into the list schema.

        Args:
            owner: Optional Owner choice (Sizan/Meet/Chetan) selected in the UI,
                applied to every job in this batch.
        """
        if not jobs:
            return 0

        from app.matching.jd_parser import VALID_OWNERS
        owner_val = owner if owner in VALID_OWNERS else None

        site_id = self._settings.sharepoint_site_id.strip()
        list_target = self._settings.sharepoint_list_id.strip() or self._settings.sharepoint_list_name.strip()

        if not site_id or not list_target:
            raise ValueError("SharePoint settings missing in .env (SP_SITE_ID / SHAREPOINT_SITE_ID, SP_LIST_ID / SP_LIST_NAME)")

        token = self._acquire_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        items_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{list_target}/items"
        success_count = 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            for job in jobs:
                sp_country = _normalize_sharepoint_country(job.country)
                notes = job.job_summary or ""
                if not sp_country and job.country:
                    # Country isn't one of the SharePoint list's fixed choices - preserve
                    # the real value in Notes instead of silently losing it.
                    notes = f"Country: {job.country} | {notes}" if notes else f"Country: {job.country}"

                job_dict = {
                    "Title": job.job_title or "Untitled Job",
                    "company": job.company or "",
                    "location_remote_type": job.location_remote_type or "",
                    "Industry": _normalize_sharepoint_industry(job.industry),
                    "LeadSource": "Indeed",
                    "Status": "New",
                    "Priority": score_to_priority(job.match_score),
                    "DateAdded": job.posted_date.strftime("%Y-%m-%d") if job.posted_date else datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
                    "Salary_x0020_Range": job.salary_range if job.salary_range != "Not listed" else "",
                    "Experience_x0020_Criteria": job.experience if job.experience != "Not specified" else "",
                    "Job_x0020_Requirement": job.job_description or "",
                    "Matching_x0020_Score": job.match_score,
                    "Matching_x0020_Skills": job.matched_skills or [],
                    "Matching_x0020_Reason": job.match_reason or "",
                    "Missing_x0020_Skills": job.missing_skills or [],
                    "website": job.job_url or "",
                    "Notes": notes,
                    "owner": owner_val or "",
                }
                if sp_country:
                    job_dict["Country"] = sp_country

                fields_dict = self.build_opportunity_fields(job_dict)
                payload = {"fields": fields_dict}

                resp = await client.post(items_url, headers=headers, json=payload)
                if resp.status_code in [200, 201]:
                    success_count += 1
                else:
                    err_msg = resp.text
                    logger.warning("Failed to insert '{}' to SharePoint ({}): {}", job.job_title, resp.status_code, err_msg)
                    # Retry with basic valid SharePoint fields only
                    notes_summary = f"Location: {job.location_remote_type or 'N/A'}"
                    if not sp_country and job.country:
                        notes_summary = f"Country: {job.country} | {notes_summary}"
                    fallback_fields = {
                        "Title": job.company or "Unknown Company",
                        "Job_x0020_Title": job.job_title or "Untitled Job",
                        "Notes": notes_summary,
                    }
                    if sp_country:
                        fallback_fields["Country"] = sp_country
                    if job.job_url:
                        fallback_fields["Job_x0020_Link"] = job.job_url
                    if owner_val:
                        fallback_fields["Owner"] = owner_val
                    if job.match_score is not None:
                        try:
                            num_score = float(job.match_score)
                            if num_score > 1.0:
                                num_score = round(num_score / 100.0, 4)
                            fallback_fields["Matching_x0020_Score"] = num_score
                        except (ValueError, TypeError):
                            pass
                    retry_resp = await client.post(items_url, headers=headers, json={"fields": fallback_fields})
                    if retry_resp.status_code in [200, 201]:
                        success_count += 1
                        logger.info("Successfully exported '{}' using minimal fallback payload.", job.job_title)
                    else:
                        raise RuntimeError(f"SharePoint List Insert Error ({resp.status_code}): {err_msg}")

        logger.info("Successfully exported {}/{} jobs to SharePoint List!", success_count, len(jobs))
        return success_count
