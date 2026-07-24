"""
Selectolax HTML Parser
======================
Uses selectolax (Lexbor engine) to extract structured job data from Indeed's
search results pages and job detail pages.
"""

import re
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from selectolax.lexbor import LexborHTMLParser

from app.config.constants import resolve_country_domain
from app.models.job import JobPosting, RemoteType
from app.parser.base_parser import BaseJobParser
from app.utils.helpers import (
    clean_text,
    extract_indeed_job_id,
    parse_indeed_relative_date,
    detect_remote_type,
    extract_salary_range,
    extract_industry,
    extract_company_size,
)
from app.utils.logger import logger


class SelectolaxParser(BaseJobParser):
    """
    Parses HTML from Indeed search results and job detail pages using Selectolax.
    All methods return empty/default values rather than raising exceptions
    to ensure the pipeline stays resilient to partial HTML failures.
    """

    def parse_search_results(
        self,
        html: str,
        country: str = "US",
        search_query: str = "",
    ) -> list[JobPosting]:
        """
        Parse all job cards from an Indeed search results page.
        """
        tree = LexborHTMLParser(html)
        job_cards = self._find_job_cards(tree)

        if not job_cards:
            logger.debug("No job cards found in HTML (country={}, search_query={})", country, search_query)
            return []

        jobs: list[JobPosting] = []
        for card in job_cards:
            try:
                job = self._parse_job_card(card, country, search_query)
                if job:
                    jobs.append(job)
            except Exception as exc:
                logger.debug("Failed to parse job card: {}", exc)

        return jobs

    def _find_job_cards(self, tree: LexborHTMLParser) -> list:
        """
        Find all job card elements on the page.
        Tries multiple CSS selectors to handle Indeed's A/B tested layouts.
        """
        # Find all li tags containing job card markers
        cards = []
        for li in tree.css("li"):
            if li.css_first('div[class*="job_seen_beacon"], div[class*="cardOutline"], div[class*="resultContent"], div[data-jk]'):
                cards.append(li)
        if cards:
            return cards

        selectors = [
            'div[class*="job_seen_beacon"], div[class*="cardOutline"], div[class*="resultContent"]',
            'li[class*="job_seen_beacon"], li[class*="cardOutline"]',
            'div[data-jk]',
            'td[class*="resultContent"]',
        ]
        for selector in selectors:
            c = tree.css(selector)
            if c:
                return c
        return []

    def _parse_job_card(
        self,
        card,
        country: str,
        search_query: str,
    ) -> Optional[JobPosting]:
        """
        Extract all available fields from a single job card element.

        Returns None if essential fields (title, company, URL) are missing.
        """
        # --- Job Title ---
        title = self._extract_text(card, [
            "h2.jobTitle span[title]",
            "h2.jobTitle a span",
            "[data-testid='jobTitle']",
            ".jobTitle",
            "h2 a span",
        ])
        if not title:
            return None

        # --- Company Name ---
        company = self._extract_text(card, [
            "[data-testid='company-name']",
            ".companyName",
            ".company",
            "span.company",
        ])
        if not company:
            return None

        # --- Job URL & ID ---
        job_url, job_id = self._extract_job_url(card, country)
        if not job_url:
            return None

        # --- Location ---
        location = self._extract_text(card, [
            "[data-testid='text-location']",
            ".companyLocation",
            ".location",
            "div.location",
        ])

        # --- Salary ---
        salary_raw = self._extract_text(card, [
            "[data-testid='attribute_snippet_testid']",
            ".salary-snippet-container",
            ".salaryOnly",
            ".salary",
        ])
        
        # Verify if extracted text is a real salary and not a job type/benefit counts
        is_real_salary = False
        if salary_raw:
            cleaned_sal = salary_raw.lower()
            has_currency = any(c in cleaned_sal for c in ["$", "£", "€", "₹", "rs", "lpa", "lakh"])
            has_k = "k" in cleaned_sal and any(char.isdigit() for char in cleaned_sal)
            has_large_number = False
            numbers = re.findall(r"\d+", cleaned_sal)
            if numbers and any(int(num) >= 100 for num in numbers):
                has_large_number = True
                
            if has_currency or has_k or has_large_number:
                is_real_salary = True
                
        salary_val = salary_raw if is_real_salary else "Not listed"
        salary = salary_val if salary_val != "Not listed" else extract_salary_range(title + " " + location)

        # --- Posted Date ---
        date_raw = self._extract_text(card, [
            "[data-testid='myJobsStateDate']",
            ".date",
            "span.date",
            ".result-link-source",
        ])
        posted_date, is_ambiguous = parse_indeed_relative_date(date_raw)

        # --- Job Snippet / Description ---
        snippet = self._extract_text(card, [
            "ul:not(.metadataContainer):not(.heading6)",  # Matches non-benefit lists (the actual description bullet points)
            "[data-testid='job-snippet']",
            ".job-snippet",
            ".underCardSnippet",
            ".jobCardShelfContainer",
            ".css-92a849",
            "div.job-snippet ul",
            "ul.heading6",
            "div.heading6",
        ])
        clean_snippet = clean_text(snippet)

        # --- Remote Type ---
        remote_str = detect_remote_type(title, location, clean_snippet)
        remote_type = RemoteType(remote_str)

        card_full_text = card.text(deep=True, separator=" ", strip=True) if hasattr(card, "text") else ""
        industry = extract_industry(title + " " + company + " " + clean_snippet + " " + card_full_text)
        company_size = extract_company_size(card_full_text + " " + clean_snippet)

        return JobPosting(
            id=uuid4(),
            indeed_job_id=job_id,
            job_title=clean_text(title),
            company=clean_text(company),
            location=clean_text(location),
            remote_type=remote_type,
            salary_range=clean_text(salary) if salary else "Not listed",
            industry=industry,
            company_size=company_size,
            posted_date_raw=date_raw or "",
            posted_date=posted_date,
            job_description=clean_snippet,
            job_url=job_url,
            apply_url=job_url,
            country=country,
            search_query=search_query,
            scraped_at=datetime.now(tz=timezone.utc),
        )

    def _extract_job_url(
        self, card, country_input: str
    ) -> tuple[str, str]:
        """
        Extract the job URL and job ID from a card element.
        """
        domain = resolve_country_domain(country_input)
        base = f"https://{domain}"

        # Try data-jk attribute first (most reliable)
        job_id = card.attributes.get("data-jk", "")
        if not job_id:
            jk_el = card.css_first("[data-jk]")
            if jk_el:
                job_id = jk_el.attributes.get("data-jk", "")
                
        if job_id:
            return f"{base}/viewjob?jk={job_id}", job_id

        # Try anchor tags
        for anchor in card.css("a[href]"):
            href = anchor.attributes.get("href", "")
            if "/viewjob" in href or "/rc/clk" in href or "jk=" in href or "/pagead" in href:
                full_url = href if href.startswith("http") else base + href
                extracted_id = extract_indeed_job_id(full_url) or str(uuid4())[:12]
                return full_url, extracted_id

        # Fallback anchor tag if no specific href matches
        first_a = card.css_first("a[href]")
        if first_a:
            href = first_a.attributes.get("href", "")
            full_url = href if href.startswith("http") else base + href
            return full_url, str(uuid4())[:12]

        return "", str(uuid4())[:12]

    def _extract_text(self, element, selectors: list[str]) -> str:
        """
        Try CSS selectors in order and return the first match's text.
        """
        for selector in selectors:
            try:
                found = element.css_first(selector)
                if found:
                    return found.text(deep=True, separator=" ", strip=True)
            except Exception:
                continue
        return ""

    def enrich_with_description(
        self, job: JobPosting, description_html: str
    ) -> JobPosting:
        """
        Enrich an existing JobPosting with a full job description.
        Used when loading the job detail page separately.
        """
        tree = LexborHTMLParser(description_html)

        # Find the main description container
        desc_selectors = [
            "#jobDescriptionText",
            ".jobsearch-jobDescriptionText",
            ".jobDescriptionContent",
            "[data-testid='jobDescription']",
        ]
        for sel in desc_selectors:
            container = tree.css_first(sel)
            if container:
                job.job_description = clean_text(container.text(deep=True, separator="\n", strip=True))
                break

        # Enrich salary if not already found
        if job.salary_range == "Not listed" and job.job_description:
            salary = extract_salary_range(job.job_description)
            if salary != "Not listed":
                job.salary_range = salary

        # Enrich remote type from description
        if job.remote_type == RemoteType.UNKNOWN:
            remote_str = detect_remote_type(
                job.job_title, job.location, job.job_description
            )
            job.remote_type = RemoteType(remote_str)

        return job
