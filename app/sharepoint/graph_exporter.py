"""
Microsoft Graph API SharePoint Exporter
=======================================
Direct, clean integration with SharePoint List via Microsoft Graph API and MSAL.
Reads all authentication & endpoint credentials strictly from environment settings (.env).
Supports full 'Opportunity Tracker' list schema (30 columns) and legacy job posting lists.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
import httpx
import msal

from app.config.settings import get_settings
from app.models.job import JobPosting
from app.utils.logger import logger


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
        if data.get("title") or data.get("Title"):
            fields["Title"] = str(data.get("title") or data.get("Title")).strip()
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
            fields["Job_x0020_Requirement"] = str(data.get("job_requirement") or data.get("Job_x0020_Requirement")).strip()
        if data.get("matching_reason") or data.get("Matching_x0020_Reason"):
            fields["Matching_x0020_Reason"] = str(data.get("matching_reason") or data.get("Matching_x0020_Reason")).strip()

        # Matched and Missing Skills (Accepts list of str or comma-separated string)
        matched_skills = data.get("matching_skills") or data.get("Matching_x0020_Skills")
        if matched_skills:
            if isinstance(matched_skills, list):
                fields["Matching_x0020_Skills"] = ", ".join([str(s).strip() for s in matched_skills if s])
            else:
                fields["Matching_x0020_Skills"] = str(matched_skills).strip()

        missing_skills = data.get("missing_skills") or data.get("Missing_x0020_Skills")
        if missing_skills:
            if isinstance(missing_skills, list):
                fields["Missing_x0020_Skills"] = ", ".join([str(s).strip() for s in missing_skills if s])
            else:
                fields["Missing_x0020_Skills"] = str(missing_skills).strip()

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

        # Format Location and URL into Notes if provided so no information is lost
        location_val = data.get("location_remote_type") or data.get("Location_x002f_RemoteType") or data.get("location") or data.get("Location")
        website_val = data.get("website") or data.get("Website") or data.get("job_url") or data.get("Job_x0020_URL")

        extra_note_parts = []
        if location_val and str(location_val).strip() not in ["N/A", "Not specified", ""] and f"Location: {str(location_val).strip()}" not in fields.get("Notes", ""):
            extra_note_parts.append(f"Location: {str(location_val).strip()}")
        if website_val and str(website_val).strip() not in ["N/A", ""] and f"URL: {str(website_val).strip()}" not in fields.get("Notes", ""):
            extra_note_parts.append(f"URL: {str(website_val).strip()}")

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
        logger.info("Posting Opportunity to SharePoint list '{}': {}", list_target, fields_dict.get("Title", "Untitled"))

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(items_url, headers=headers, json=payload)
            if resp.status_code in [200, 201]:
                res_data = resp.json()
                logger.info("Opportunity '{}' created successfully (ID: {}).", fields_dict.get("Title"), res_data.get("id"))
                return res_data

            # If some fields are not recognized by a non-standard list schema, attempt graceful retry with core fields
            err_text = resp.text
            logger.warning("SharePoint insertion error ({}) for '{}': {}", resp.status_code, fields_dict.get("Title"), err_text)
            
            # Retry without non-standard fields that might trigger schema errors
            core_fields = {
                k: v for k, v in fields_dict.items()
                if k in [
                    "Title", "Notes", "Country", "Industry", "LeadSource", "Owner",
                    "Priority", "Status", "CurrencyCode", "Job_x0020_Requirement",
                    "Matching_x0020_Score", "Matching_x0020_Skills", "Matching_x0020_Reason",
                    "Missing_x0020_Skills", "Salary_x0020_Range", "Experience_x0020_Criteria",
                    "Technology", "Technology@odata.type", "DateAdded"
                ]
            }
            retry_resp = await client.post(items_url, headers=headers, json={"fields": core_fields})
            if retry_resp.status_code in [200, 201]:
                res_data = retry_resp.json()
                logger.info("Opportunity '{}' created on fallback attempt (ID: {}).", core_fields.get("Title"), res_data.get("id"))
                return res_data

            raise RuntimeError(f"SharePoint List Insert Failed ({resp.status_code}): {err_text}")

    async def export_jobs(self, jobs: list[JobPosting]) -> int:
        """
        Upload list of JobPosting objects directly to the SharePoint List.
        Maps all available job and AI evaluation fields into the list schema.
        """
        if not jobs:
            return 0

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
                job_dict = {
                    "Title": job.job_title or "Untitled Job",
                    "company": job.company or "",
                    "Country": job.country or "US",
                    "location_remote_type": job.location_remote_type or "",
                    "Industry": "IT" if job.industry in ["Not listed", ""] else (job.industry or "IT"),
                    "LeadSource": "Indeed",
                    "Status": "New",
                    "Priority": "High" if (job.match_score and job.match_score >= 70) else ("Medium" if (job.match_score and job.match_score >= 40) else "Low"),
                    "DateAdded": job.posted_date.strftime("%Y-%m-%d") if job.posted_date else datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
                    "Salary_x0020_Range": job.salary_range if job.salary_range != "Not listed" else "",
                    "Experience_x0020_Criteria": job.experience if job.experience != "Not specified" else "",
                    "Job_x0020_Requirement": job.job_description or "",
                    "Matching_x0020_Score": job.match_score,
                    "Matching_x0020_Skills": job.matched_skills or [],
                    "Matching_x0020_Reason": job.match_reason or "",
                    "Missing_x0020_Skills": job.missing_skills or [],
                    "website": job.job_url or "",
                    "Notes": job.job_summary or "",
                }

                fields_dict = self.build_opportunity_fields(job_dict)
                payload = {"fields": fields_dict}

                resp = await client.post(items_url, headers=headers, json=payload)
                if resp.status_code in [200, 201]:
                    success_count += 1
                else:
                    err_msg = resp.text
                    logger.warning("Failed to insert '{}' to SharePoint ({}): {}", job.job_title, resp.status_code, err_msg)
                    # Retry with basic valid SharePoint fields only
                    notes_summary = f"Company: {job.company or 'N/A'} | Location: {job.location_remote_type or 'N/A'} | URL: {job.job_url or 'N/A'}"
                    fallback_fields = {
                        "Title": job.job_title or "Untitled Job",
                        "Country": job.country or "US",
                        "Notes": notes_summary,
                    }
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
