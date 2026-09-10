"""
Microsoft 365 Graph API Email Notifier
======================================
Sends formatted executive HTML email reports with the scraped Excel workbook attached,
using Microsoft Graph API and MSAL with Azure AD App Registration credentials.
"""

import base64
import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import msal

from app.config.constants import COMMON_COUNTRIES, IST
from app.config.settings import get_settings
from app.models.job import JobPosting
from app.utils.logger import logger

_COUNTRY_NAME_MAP = {c.code.upper(): c.name for c in COMMON_COUNTRIES}

_FROMAGE_LABELS = {
    "1": "Last 24 hours (1 day)",
    "3": "Last 3 days",
    "7": "Last 7 days (1 week)",
    "14": "Last 14 days (2 weeks)",
    "30": "Last 30 days (1 month)",
    "all": "All Dates (Anytime)",
}

_LOCATION_LABELS = {
    "all": "All (Remote & On-Site)",
    "remote": "Fully Remote Only",
    "onsite": "On-Site Only",
    "hybrid": "Hybrid Only",
}


# Internal confidential recipients list (used when not exposed in .env)
# INTERNAL_DEFAULT_RECIPIENTS = ["yashS@desireinfoweb.com"]
INTERNAL_DEFAULT_RECIPIENTS = ['raj.ponkiya@t12y7.onmicrosoft.com']


class GraphMailNotifier:
    """Sends email summaries and Excel attachments directly via Microsoft 365 Graph API."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def _acquire_token(self) -> str:
        """Acquire OAuth2 Access Token for Microsoft Graph from Azure AD via MSAL."""
        tenant_id = (self._settings.graph_tenant_id.strip() or self._settings.azure_tenant_id.strip())
        client_id = (self._settings.graph_client_id.strip() or self._settings.azure_client_id.strip())
        client_secret = (self._settings.graph_client_secret.strip() or self._settings.azure_client_secret.strip())

        if not tenant_id or not client_id or not client_secret:
            raise ValueError(
                "Microsoft Graph / Azure AD credentials missing in .env (GRAPH_TENANT_ID or AZURE_TENANT_ID)"
            )


        app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
        )
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" in result:
            return result["access_token"]
        raise PermissionError(f"Azure AD Graph Auth Failed: {result.get('error_description')}")

    def build_html_report(
        self,
        jobs: list[JobPosting],
        query: str = "",
        countries: Optional[list[str]] = None,
        fromage: str = "all",
        location_type: str = "all",
        status: str = "completed",
        error_note: Optional[str] = None,
    ) -> str:
        """Generate a modern, responsive HTML email dashboard with metrics and top leads."""
        now_str = datetime.now(tz=IST).strftime("%Y-%m-%d %I:%M %p IST (GMT+5:30)")
        total_jobs = len(jobs)
        high_matches = sum(1 for j in jobs if (j.match_score or 0) >= 70)
        med_matches = sum(1 for j in jobs if 50 <= (j.match_score or 0) < 70)

        # Format countries display
        if countries:
            formatted_countries = [
                f"{_COUNTRY_NAME_MAP.get(c.upper(), c)} ({c.upper()})" if c.upper() in _COUNTRY_NAME_MAP else c
                for c in countries
            ]
            countries_display = ", ".join(formatted_countries)
            countries_str = ", ".join(countries)
        else:
            countries_display = "All Target Countries"
            countries_str = "All Target Countries"

        query_display = query.strip() if query and query.strip() else "All Configured Roles"
        query_str = query_display

        # Format date posted and location labels
        fromage_key = str(fromage).strip().lower() if fromage is not None else "all"
        fromage_display = _FROMAGE_LABELS.get(fromage_key, f"Last {fromage} days" if fromage_key.isdigit() else str(fromage))

        location_key = str(location_type).strip().lower() if location_type is not None else "all"
        location_display = _LOCATION_LABELS.get(location_key, str(location_type))

        status_clean = (status or "completed").lower()
        if status_clean == "completed":
            badge_html = '<span style="display:inline-block; padding:4px 10px; background:#16a34a; color:#ffffff; font-size:11px; font-weight:700; border-radius:12px; text-transform:uppercase; letter-spacing:0.5px;">Completed</span>'
            notice_html = ""
        elif status_clean in ("partial", "stopped"):
            badge_html = '<span style="display:inline-block; padding:4px 10px; background:#d97706; color:#ffffff; font-size:11px; font-weight:700; border-radius:12px; text-transform:uppercase; letter-spacing:0.5px;">Partial Run</span>'
            notice_reason = f" ({html.escape(error_note)})" if error_note else ""
            notice_html = f"""
            <div style="margin: 15px 25px 0 25px; padding: 12px 18px; background-color: #fffbeb; border-left: 4px solid #f59e0b; border-radius: 4px; font-size: 13px; color: #92400e;">
                <strong>⚠️ Partial Run Notice:</strong> This scraping session stopped early{notice_reason}. All <strong>{total_jobs}</strong> leads captured prior to interruption have been secured and attached below.
            </div>
            """
        else:  # error
            badge_html = '<span style="display:inline-block; padding:4px 10px; background:#dc2626; color:#ffffff; font-size:11px; font-weight:700; border-radius:12px; text-transform:uppercase; letter-spacing:0.5px;">Halted</span>'
            notice_reason = f": {html.escape(error_note)}" if error_note else ""
            notice_html = f"""
            <div style="margin: 15px 25px 0 25px; padding: 12px 18px; background-color: #fef2f2; border-left: 4px solid #ef4444; border-radius: 4px; font-size: 13px; color: #991b1b;">
                <strong>🚨 Run Interrupted{notice_reason}.</strong> {f'Safeguarded {total_jobs} leads in the attached workbook.' if total_jobs > 0 else 'No leads were captured before interruption.'}
            </div>
            """

        # Sort jobs by match score descending
        sorted_jobs = sorted(jobs, key=lambda x: (x.match_score or 0), reverse=True)
        top_jobs = sorted_jobs[:15]  # Display up to 15 top leads in email body

        table_rows = []
        for j in top_jobs:
            score = j.match_score
            if score is not None:
                if score >= 70:
                    badge_style = "background-color: #dcfce7; color: #15803d; border: 1px solid #86efac;"
                elif score >= 50:
                    badge_style = "background-color: #dbeafe; color: #1d4ed8; border: 1px solid #93c5fd;"
                else:
                    badge_style = "background-color: #f1f5f9; color: #475569; border: 1px solid #cbd5e1;"
                score_badge = f'<span style="display:inline-block; padding:3px 8px; font-weight:700; font-size:12px; border-radius:12px; {badge_style}">{score}/100</span>'
            else:
                score_badge = '<span style="color:#94a3b8; font-size:11px;">N/A</span>'

            skills_html = ""
            if j.matched_skills:
                badges = [
                    f'<span style="display:inline-block; margin:2px 3px 2px 0; padding:1px 6px; font-size:11px; background:#eff6ff; color:#1e40af; border-radius:4px;">{html.escape(s)}</span>'
                    for s in j.matched_skills[:4]
                ]
                skills_html = "".join(badges)
            else:
                skills_html = '<span style="color:#94a3b8; font-size:11px;">-</span>'

            title_link = (
                f'<a href="{html.escape(j.job_url)}" target="_blank" style="color:#2563eb; text-decoration:none; font-weight:600;">{html.escape(j.job_title)}</a>'
                if j.job_url
                else html.escape(j.job_title)
            )

            table_rows.append(
                f"""
                <tr style="border-bottom: 1px solid #e2e8f0; font-size: 13px;">
                    <td style="padding: 10px 12px; text-align: center;">{score_badge}</td>
                    <td style="padding: 10px 12px;">
                        <div style="font-size: 14px; margin-bottom: 3px;">{title_link}</div>
                        <div style="color: #64748b; font-size: 12px;">{html.escape(j.company)} &bull; {html.escape(j.location or j.country)} ({html.escape(j.remote_type.value if hasattr(j.remote_type, 'value') else str(j.remote_type))})</div>
                    </td>
                    <td style="padding: 10px 12px; color: #334155; font-size: 12px;">{html.escape(j.salary_range or 'Not listed')}</td>
                    <td style="padding: 10px 12px;">{skills_html}</td>
                </tr>
                """
            )

        rows_html = "".join(table_rows) if table_rows else "<tr><td colspan='4' style='padding:20px; text-align:center; color:#64748b;'>No jobs scraped in this run.</td></tr>"

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 0; background-color: #f8fafc; color: #0f172a; }}
                .container {{ max-width: 860px; margin: 20px auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
                .header {{ background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%); color: #ffffff; padding: 24px 30px; }}
                .stats-grid {{ display: flex; flex-wrap: wrap; background: #f1f5f9; padding: 15px 25px; border-bottom: 1px solid #e2e8f0; }}
                .stat-box {{ flex: 1; min-width: 120px; margin: 5px 10px; }}
                .stat-num {{ font-size: 22px; font-weight: 700; color: #1e293b; }}
                .stat-label {{ font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 600; letter-spacing: 0.5px; }}
                .content {{ padding: 25px; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th {{ background-color: #f8fafc; color: #475569; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; text-align: left; padding: 10px 12px; border-bottom: 2px solid #cbd5e1; }}
                .footer {{ background: #f8fafc; padding: 16px 25px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #64748b; text-align: center; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <h2 style="margin: 0; font-size: 22px; font-weight: 700;">🎯 Indeed Job Sourcing Daily Report</h2>
                        <div>{badge_html}</div>
                    </div>
                    <div style="font-size: 13px; opacity: 0.9;">Run Timestamp: {now_str} &bull; Target: {html.escape(query_str)} ({html.escape(countries_str)})</div>
                </div>
                {notice_html}

                <div class="stats-grid">
                    <div class="stat-box">
                        <div class="stat-num">{total_jobs}</div>
                        <div class="stat-label">Total Leads</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-num" style="color: #16a34a;">{high_matches}</div>
                        <div class="stat-label">High Match (≥70%)</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-num" style="color: #2563eb;">{med_matches}</div>
                        <div class="stat-label">Medium Match (50-69%)</div>
                    </div>
                </div>

                <!-- Search Parameters & Selected Filters Summary -->
                <div style="margin: 15px 25px 0 25px; padding: 14px 18px; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px;">
                    <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #475569; letter-spacing: 0.5px; margin-bottom: 8px;">
                        🔍 Search Parameters & Selected Filters
                    </div>
                    <table style="width: 100%; border: none; font-size: 13px; border-collapse: collapse;">
                        <tr style="border-bottom: 1px dashed #e2e8f0;">
                            <td style="padding: 6px 4px; width: 30%; color: #64748b; font-weight: 600;">Selected Countries:</td>
                            <td style="padding: 6px 4px; width: 70%; color: #0f172a; font-weight: 700;">{html.escape(countries_display)}</td>
                        </tr>
                        <tr style="border-bottom: 1px dashed #e2e8f0;">
                            <td style="padding: 6px 4px; color: #64748b; font-weight: 600;">Search Keyword / Role:</td>
                            <td style="padding: 6px 4px; color: #2563eb; font-weight: 700;">{html.escape(query_display)}</td>
                        </tr>
                        <tr style="border-bottom: 1px dashed #e2e8f0;">
                            <td style="padding: 6px 4px; color: #64748b; font-weight: 600;">Date Posted Filter:</td>
                            <td style="padding: 6px 4px; color: #0f172a; font-weight: 700;">{html.escape(fromage_display)}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 4px; color: #64748b; font-weight: 600;">Location Filter:</td>
                            <td style="padding: 6px 4px; color: #0f172a; font-weight: 600;">{html.escape(location_display)}</td>
                        </tr>
                    </table>
                </div>

                <div class="content">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
                        <h3 style="margin:0; font-size:16px; color:#1e293b;">Top Matched Job Leads</h3>
                        <span style="font-size:12px; color:#64748b;">📎 Full details attached in Excel</span>
                    </div>

                    <table>
                        <thead>
                            <tr>
                                <th style="text-align:center; width: 90px;">Match</th>
                                <th>Job Title & Company</th>
                                <th style="width: 130px;">Salary</th>
                                <th style="width: 220px;">Key Matched Skills</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_html}
                        </tbody>
                    </table>

                    <div style="margin-top: 25px; padding: 14px 18px; background-color: #eff6ff; border-left: 4px solid #3b82f6; border-radius: 4px; font-size: 13px; color: #1e3a8a;">
                        <strong>📁 Attached Workbook:</strong> The complete Excel workbook is attached to this email containing full job descriptions, qualification criteria, and SharePoint sync metadata.
                    </div>
                </div>

                <div class="footer">
                    Indeed Automated Sourcing System &bull; Microsoft 365 Graph Integration &bull; Powered by AI Knowledge Base Matching
                </div>
            </div>
        </body>
        </html>
        """

    async def send_report(
        self,
        jobs: list[JobPosting],
        excel_path: Optional[str] = None,
        query: str = "",
        countries: Optional[list[str]] = None,
        fromage: str = "all",
        location_type: str = "all",
        status: str = "completed",
        error_note: Optional[str] = None,
    ) -> bool:
        """
        Send formatted HTML email with Excel attachment via Microsoft Graph API.
        Supports both full completion, partial lead delivery, and alert notifications.
        """
        if not self._settings.email_notifications_enabled:
            return False

        mail_sender = (self._settings.graph_sender_email.strip() or self._settings.mail_sender.strip())
        recipients_raw = self._settings.notification_email_to.strip()

        # If recipients are not configured in .env, use internal confidential recipients
        if recipients_raw:
            raw_list = [r.strip() for r in recipients_raw.split(",") if r.strip() and "@" in r]
        else:
            raw_list = list(INTERNAL_DEFAULT_RECIPIENTS)

        # Include sender mailbox in recipient list so sender receives a copy
        if mail_sender and "@" in mail_sender and mail_sender not in raw_list:
            raw_list.append(mail_sender)

        recipients = [
            {"emailAddress": {"address": r}}
            for r in raw_list
            if r and "@" in r
        ]

        if not mail_sender or not recipients:
            return False

        try:
            token = self._acquire_token()
        except Exception as auth_err:
            logger.debug("Silent notification auth skipped: {}", auth_err)
            return False

        date_str = datetime.now(tz=IST).strftime("%Y-%m-%d")
        total_jobs = len(jobs)
        status_clean = (status or "completed").lower()
        query_display = query.strip() if query and query.strip() else ""
        query_tag = f" [{query_display}]" if query_display else ""

        if status_clean == "completed":
            subject = f"🎯 Daily Indeed Job Leads ({total_jobs} leads){query_tag} - {date_str}"
        elif status_clean in ("partial", "stopped"):
            subject = f"⚠️ Indeed Job Leads [Partial: {total_jobs} leads]{query_tag} - {date_str}"
        else:  # error
            if total_jobs > 0:
                subject = f"⚠️ Indeed Job Leads [Partial: {total_jobs} leads]{query_tag} - {date_str}"
            else:
                subject = f"🚨 Indeed Scraper Alert: Run Interrupted (0 leads){query_tag} - {date_str}"

        body_html = self.build_html_report(
            jobs,
            query=query,
            countries=countries,
            fromage=fromage,
            location_type=location_type,
            status=status_clean,
            error_note=error_note,
        )

        attachments = []
        if excel_path and Path(excel_path).is_file():
            try:
                file_path = Path(excel_path)
                file_bytes = file_path.read_bytes()
                encoded_content = base64.b64encode(file_bytes).decode("utf-8")
                attachments.append({
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": file_path.name,
                    "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "contentBytes": encoded_content,
                })
            except Exception:
                pass

        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": body_html,
                },
                "toRecipients": recipients,
                "attachments": attachments,
            },
            "saveToSentItems": "true",
        }

        # Microsoft Graph API sendMail endpoint
        endpoint = f"https://graph.microsoft.com/v1.0/users/{mail_sender}/sendMail"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(endpoint, json=payload, headers=headers)
                if response.status_code in (200, 202):
                    logger.info("Email notification successfully sent via Microsoft Graph API to: {}", [r["emailAddress"]["address"] for r in recipients])
                    return True
                else:
                    logger.warning("Microsoft Graph sendMail HTTP error {}: {}", response.status_code, response.text)
                    return False
        except Exception as req_err:
            logger.error("Microsoft Graph sendMail exception: {}", req_err)
            return False
