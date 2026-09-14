"""
Excel Exporter
==============
Generates a clean, professionally formatted Excel workbook (.xlsx)
containing all scraped job leads along with the executive search parameters header.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.config.constants import COMMON_COUNTRIES, IST
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


class ExcelExporter:
    """Generates styled Excel workbooks for scraped job postings."""

    def export(
        self,
        jobs: list[JobPosting],
        output_dir: str = "outputs",
        query: str = "",
        countries: Optional[list[str]] = None,
        fromage: str = "all",
        location_type: str = "all",
    ) -> Path:
        """
        Export job postings to an Excel workbook with a clean executive parameters header.

        Args:
            jobs: List of JobPosting objects.
            output_dir: Target directory path.
            query: Search query or role keyword.
            countries: Target country codes/names.
            fromage: Date posted filter window.
            location_type: Remote/onsite/all filter.

        Returns:
            Path object pointing to the generated .xlsx file.
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now(tz=IST).strftime("%Y-%m-%d")
        file_path = output_path / f"Indeed_Job_Leads_{date_str}.xlsx"

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Job Leads"

        # Format parameter labels
        if countries:
            formatted_countries = [
                f"{_COUNTRY_NAME_MAP.get(c.upper(), c)} ({c.upper()})" if c.upper() in _COUNTRY_NAME_MAP else c
                for c in countries
            ]
            countries_display = ", ".join(formatted_countries)
        else:
            countries_display = "All Target Countries"

        query_display = query.strip() if query and query.strip() else "All Configured Roles"
        fromage_key = str(fromage).strip().lower() if fromage is not None else "all"
        fromage_display = _FROMAGE_LABELS.get(fromage_key, f"Last {fromage} days" if fromage_key.isdigit() else str(fromage))
        location_key = str(location_type).strip().lower() if location_type is not None else "all"
        location_display = _LOCATION_LABELS.get(location_key, str(location_type))

        # Thin gray border for summary card
        card_border = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1"),
        )
        label_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
        label_font = Font(name="Calibri", size=10, bold=True, color="64748B")

        # ---------------------------------------------------------------------
        # Row 1: Executive Title Banner
        # ---------------------------------------------------------------------
        ws.merge_cells("A1:N1")
        banner = ws.cell(row=1, column=1, value="🎯 INDEED JOB SOURCING REPORT")
        banner.font = Font(name="Calibri", size=13, bold=True, color="FFFFFF")
        banner.fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        banner.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 30

        # ---------------------------------------------------------------------
        # Row 2: Search Parameters Card Header
        # ---------------------------------------------------------------------
        ws.merge_cells("A2:N2")
        param_hdr = ws.cell(row=2, column=1, value="🔍 SEARCH PARAMETERS & SELECTED FILTERS")
        param_hdr.font = Font(name="Calibri", size=10, bold=True, color="1E293B")
        param_hdr.fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
        param_hdr.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws.row_dimensions[2].height = 22

        # ---------------------------------------------------------------------
        # Row 3: Selected Countries & Date Posted Filter
        # ---------------------------------------------------------------------
        c_lbl = ws.cell(row=3, column=1, value="Selected Countries:")
        c_lbl.font = label_font
        c_lbl.fill = label_fill
        c_lbl.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        c_lbl.border = card_border

        ws.merge_cells("B3:E3")
        c_val = ws.cell(row=3, column=2, value=countries_display)
        c_val.font = Font(name="Calibri", size=10, bold=True, color="0F172A")
        c_val.alignment = Alignment(horizontal="left", vertical="center")
        for col in range(2, 6):
            ws.cell(row=3, column=col).border = card_border

        d_lbl = ws.cell(row=3, column=6, value="Date Posted Filter:")
        d_lbl.font = label_font
        d_lbl.fill = label_fill
        d_lbl.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        d_lbl.border = card_border

        ws.merge_cells("G3:N3")
        d_val = ws.cell(row=3, column=7, value=fromage_display)
        d_val.font = Font(name="Calibri", size=10, bold=True, color="0F172A")
        d_val.alignment = Alignment(horizontal="left", vertical="center")
        for col in range(7, 15):
            ws.cell(row=3, column=col).border = card_border
        ws.row_dimensions[3].height = 20

        # ---------------------------------------------------------------------
        # Row 4: Search Keyword / Role & Location Filter
        # ---------------------------------------------------------------------
        q_lbl = ws.cell(row=4, column=1, value="Search Keyword / Role:")
        q_lbl.font = label_font
        q_lbl.fill = label_fill
        q_lbl.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        q_lbl.border = card_border

        ws.merge_cells("B4:E4")
        q_val = ws.cell(row=4, column=2, value=query_display)
        q_val.font = Font(name="Calibri", size=10, bold=True, color="1D4ED8")
        q_val.alignment = Alignment(horizontal="left", vertical="center")
        for col in range(2, 6):
            ws.cell(row=4, column=col).border = card_border

        l_lbl = ws.cell(row=4, column=6, value="Location Filter:")
        l_lbl.font = label_font
        l_lbl.fill = label_fill
        l_lbl.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        l_lbl.border = card_border

        ws.merge_cells("G4:N4")
        l_val = ws.cell(row=4, column=7, value=location_display)
        l_val.font = Font(name="Calibri", size=10, bold=True, color="0F172A")
        l_val.alignment = Alignment(horizontal="left", vertical="center")
        for col in range(7, 15):
            ws.cell(row=4, column=col).border = card_border
        ws.row_dimensions[4].height = 20

        # ---------------------------------------------------------------------
        # Row 5: Export Timestamp & Total Leads
        # ---------------------------------------------------------------------
        t_lbl = ws.cell(row=5, column=1, value="Export Timestamp:")
        t_lbl.font = label_font
        t_lbl.fill = label_fill
        t_lbl.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        t_lbl.border = card_border

        ws.merge_cells("B5:E5")
        t_val = ws.cell(row=5, column=2, value=datetime.now(tz=IST).strftime("%Y-%m-%d %I:%M %p IST (GMT+5:30)"))
        t_val.font = Font(name="Calibri", size=9, color="475569")
        t_val.alignment = Alignment(horizontal="left", vertical="center")
        for col in range(2, 6):
            ws.cell(row=5, column=col).border = card_border

        lead_lbl = ws.cell(row=5, column=6, value="Total Leads:")
        lead_lbl.font = label_font
        lead_lbl.fill = label_fill
        lead_lbl.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        lead_lbl.border = card_border

        ws.merge_cells("G5:N5")
        lead_val = ws.cell(row=5, column=7, value=f"{len(jobs)} leads captured")
        lead_val.font = Font(name="Calibri", size=9, bold=True, color="15803D")
        lead_val.alignment = Alignment(horizontal="left", vertical="center")
        for col in range(7, 15):
            ws.cell(row=5, column=col).border = card_border
        ws.row_dimensions[5].height = 20

        # Row 6: Visual spacing
        ws.row_dimensions[6].height = 10

        # ---------------------------------------------------------------------
        # Row 7: Data Table Headers
        # ---------------------------------------------------------------------
        headers = [
            "Job Title",
            "Company",
            "Country",
            "Location/Remote Type",
            "Experience Criteria",
            "Salary Range",
            "Industry",
            "Company Size",
            "Job Description",
            "Match Score",
            "Matched Skills",
            "Missing Skills",
            "Match Reason",
            "Job URL",
        ]

        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

        header_row_idx = 7
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=header_row_idx, column=col_num, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align

        ws.row_dimensions[header_row_idx].height = 28

        # ---------------------------------------------------------------------
        # Rows 8+: Data rows
        # ---------------------------------------------------------------------
        row_font = Font(name="Calibri", size=10)
        link_font = Font(name="Calibri", size=10, color="0563C1", underline="single")
        table_border = Border(
            left=Side(style="thin", color="D3D3D3"),
            right=Side(style="thin", color="D3D3D3"),
            top=Side(style="thin", color="D3D3D3"),
            bottom=Side(style="thin", color="D3D3D3"),
        )

        for row_idx, job in enumerate(jobs, start=header_row_idx + 1):
            row_values = [
                job.job_title,
                job.company,
                job.country,
                job.location_remote_type,
                job.experience,
                job.salary_range,
                job.industry,
                job.company_size,
                job.job_description,
                job.match_score if job.match_score is not None else "",
                ", ".join(job.matched_skills),
                ", ".join(job.missing_skills),
                job.match_reason,
                job.job_url,
            ]

            for col_idx, val in enumerate(row_values, start=1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.border = table_border
                cell.font = row_font

                if col_idx == 14 and str(val).startswith("http"):  # Job URL hyperlink
                    cell.value = "View on Indeed"
                    cell.hyperlink = str(val)
                    cell.font = link_font
                else:
                    cell.value = val

        # Auto-adjust column widths based on table rows
        for col_idx, header in enumerate(headers, 1):
            col_letter = get_column_letter(col_idx)
            max_len = len(header)
            for row_num in range(header_row_idx + 1, header_row_idx + 1 + len(jobs)):
                cell_val = str(ws.cell(row=row_num, column=col_idx).value or "")
                if len(cell_val) > max_len:
                    max_len = len(cell_val)
            ws.column_dimensions[col_letter].width = min(max(max_len + 4, 14), 50)

        # Freeze pane below header row so parameters and headers stay visible
        ws.freeze_panes = f"A{header_row_idx + 1}"

        wb.save(file_path)
        logger.info("Excel exported with parameters header: {} ({} leads)", file_path, len(jobs))
        return file_path

