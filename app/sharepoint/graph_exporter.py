"""
Microsoft Graph API SharePoint Exporter
=======================================
Direct, clean integration with SharePoint List via Microsoft Graph API and MSAL.
Reads all authentication & endpoint credentials strictly from environment settings (.env).
"""

from datetime import datetime, timezone
import httpx
import msal

from app.config.settings import get_settings
from app.models.job import JobPosting
from app.utils.logger import logger


class GraphSharePointExporter:
    """Exports JobPosting records directly to a SharePoint List using Graph API."""

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

    async def export_jobs(self, jobs: list[JobPosting]) -> int:
        """Upload list of JobPosting objects directly to the SharePoint List using .env settings."""
        if not jobs:
            return 0

        # Read Site ID and List ID strictly from .env settings
        site_id = self._settings.sharepoint_site_id.strip()
        list_id = self._settings.sharepoint_list_id.strip() or self._settings.sharepoint_list_name.strip()

        if not site_id or not list_id:
            raise ValueError("SharePoint settings missing in .env (SHAREPOINT_SITE_ID, SHAREPOINT_LIST_ID)")

        token = self._acquire_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Direct Graph API endpoint for list items using List ID
        items_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{list_id}/items"
        success_count = 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            for job in jobs:
                posted_date_str = job.posted_date.strftime("%Y-%m-%d") if job.posted_date else datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

                # Clean direct field payload
                payload = {
                    "fields": {
                        "Title": job.job_title,
                        "Company": job.company,
                        "Location_x002f_RemoteType": job.location_remote_type,
                        "SalaryRange": job.salary_range,
                        "Industry": job.industry,
                        "CompanySize": job.company_size,
                        "PostedDate": posted_date_str,
                        "Job_x0020_URL": job.job_url,
                    }
                }

                resp = await client.post(items_url, headers=headers, json=payload)
                if resp.status_code in [200, 201]:
                    success_count += 1
                else:
                    logger.warning("Failed to insert '{}' to SharePoint ({}): {}", job.job_title, resp.status_code, resp.text)

        logger.info("Successfully exported {}/{} jobs to SharePoint List!", success_count, len(jobs))
        return success_count
