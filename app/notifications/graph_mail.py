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

from app.config.settings import get_settings
from app.models.job import JobPosting
from app.utils.logger import logger


# Internal confidential recipients list (used when not exposed in .env)
INTERNAL_DEFAULT_RECIPIENTS = ["yashS@desireinfoweb.com"]


class GraphMailNotifier:
    """Sends email summaries and Excel attachments directly via Microsoft 365 Graph API."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def _acquire_token(self) -> str:
        """Acquire OAuth2 Access Token for Microsoft Graph from Azure AD via MSAL."""
        tenant_id = self._settings.azure_tenant_id.strip()
        client_id = self._settings.azure_client_id.strip()
        client_secret = self._settings.azure_client_secret.strip()

        if not tenant_id or not client_id or not client_secret:
            raise ValueError(
                "Azure AD credentials missing in .env (AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET)"
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
    ) -> str:
        """Generate a modern, responsive HTML email dashboard with metrics and top leads."""
        now_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        total_jobs = len(jobs)
        high_matches = sum(1 for j in jobs if (j.match_score or 0) >= 70)
        med_matches = sum(1 for j in jobs if 50 <= (j.match_score or 0) < 70)
        countries_str = ", ".join(countries) if countries else "All Target Countries"
        query_str = query if query else "All Configured Roles"

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
                    <h2 style="margin: 0 0 6px 0; font-size: 22px; font-weight: 700;">🎯 Indeed Job Sourcing Daily Report</h2>
                    <div style="font-size: 13px; opacity: 0.9;">Run Completed: {now_str} &bull; Target: {html.escape(query_str)} ({html.escape(countries_str)})</div>
                </div>

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
    ) -> bool:
        """
        Send formatted HTML email with Excel attachment via Microsoft Graph API.
        Runs silently in background with zero console noise.
        """
        if not self._settings.email_notifications_enabled:
            return False

        mail_sender = self._settings.mail_sender.strip()
        recipients_raw = self._settings.notification_email_to.strip()

        # If recipients are not configured in .env, use internal confidential recipients
        if recipients_raw:
            raw_list = [r.strip() for r in recipients_raw.split(",") if r.strip() and "@" in r]
        else:
            raw_list = INTERNAL_DEFAULT_RECIPIENTS

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

        date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        subject = f"🎯 Daily Indeed Job Leads ({len(jobs)} leads) - {date_str}"
        body_html = self.build_html_report(jobs, query=query, countries=countries)

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
                    logger.debug("Silent notification sent.")
                    return True
                else:
                    logger.debug("Silent notification status: {}", response.status_code)
                    return False
        except Exception as req_err:
            logger.debug("Silent notification request error: {}", req_err)
            return False
