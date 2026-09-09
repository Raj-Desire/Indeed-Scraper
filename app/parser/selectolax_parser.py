"""
Selectolax HTML Parser (Selectolax + Lexbor)
===========================================
Extracts structured job data from Indeed search results and detail pages.
Implements field-specific, multi-strategy DOM extraction with full diagnostic logging.
"""

import json
import re
from datetime import datetime, timezone
from typing import Optional, Any
from uuid import uuid4

from selectolax.lexbor import LexborHTMLParser, LexborNode

from app.config.constants import resolve_country_domain
from app.models.job import JobPosting, RemoteType
from app.parser.base_parser import BaseJobParser
from app.scraper.selector_health import selector_health
from app.utils.helpers import (
    clean_text,
    extract_indeed_job_id,
    parse_indeed_relative_date,
    detect_remote_type,
    extract_salary_range,
    extract_industry,
    extract_company_size,
    extract_experience,
)
from app.utils.logger import logger


class SelectolaxParser(BaseJobParser):
    """
    Parses HTML from Indeed search results and job detail pages using Selectolax (Lexbor engine).
    Each field uses dedicated DOM container inspection and fallback strategies.
    Logs extraction diagnostics per field.
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
        seen_ids = set()

        for card in job_cards:
            try:
                job = self._parse_job_card(card, country, search_query)
                if job:
                    if job.indeed_job_id and job.indeed_job_id in seen_ids:
                        continue
                    if job.indeed_job_id:
                        seen_ids.add(job.indeed_job_id)
                    jobs.append(job)
            except Exception as exc:
                logger.debug("Failed to parse job card: {}", exc)

        return jobs

    def _find_job_cards(self, tree: LexborHTMLParser) -> list[LexborNode]:
        """
        Find all job card elements on the page using structured selectors.
        """
        # Primary container: div[class*="job_seen_beacon"], div[class*="cardOutline"]
        raw_cards = tree.css('div[class*="job_seen_beacon"], div[class*="cardOutline"]')
        if raw_cards:
            cards = list(dict.fromkeys(raw_cards))
            selector_health.record_hit("job_cards_container")
            logger.debug("[Selectolax] Found {} cards via 'job_seen_beacon|cardOutline'", len(cards))
            return cards

        # Fallback 1: li tags containing data-jk
        li_cards = []
        for li in tree.css("li"):
            if li.css_first("[data-jk]") or "data-jk" in li.attributes:
                li_cards.append(li)
        if li_cards:
            selector_health.record_miss("job_cards_container")
            selector_health.record_hit("job_cards_li_fallback")
            logger.debug("[Selectolax] Found {} cards via li[data-jk]", len(li_cards))
            return li_cards

        # Fallback 2: data-jk containers directly
        jk_cards = tree.css("[data-jk]")
        if jk_cards:
            selector_health.record_miss("job_cards_container")
            selector_health.record_hit("job_cards_jk_fallback")
            logger.debug("[Selectolax] Found {} cards via [data-jk]", len(jk_cards))
            return jk_cards

        selector_health.record_miss("job_cards_container")
        return []

    def _parse_job_card(
        self,
        card: LexborNode,
        country: str,
        search_query: str,
    ) -> Optional[JobPosting]:
        """
        Extract existing fields from a single job card element.
        """
        # 1. Job Title
        title = self._extract_title(card)
        if not title:
            selector_health.record_miss("card_job_title")
            logger.debug("[Selectolax] Field 'job_title' not found on card -> skipping card")
            return None
        selector_health.record_hit("card_job_title")

        # 2. Company Name
        company = self._extract_company(card)
        if not company:
            selector_health.record_miss("card_company")
            logger.debug("[Selectolax] Field 'company' not found on card -> skipping card")
            return None
        selector_health.record_hit("card_company")

        # 3. Job URL & ID
        job_url, job_id = self._extract_job_url(card, country)
        if not job_url:
            selector_health.record_miss("card_job_url")
            logger.debug("[Selectolax] Field 'job_url' not found on card -> skipping card")
            return None
        selector_health.record_hit("card_job_url")

        # 4. Location
        location = self._extract_location(card)
        if location:
            selector_health.record_hit("card_location")
        else:
            selector_health.record_miss("card_location")

        # 5. Salary
        salary = self._extract_salary_from_card(card)
        if salary and salary != "Not listed":
            selector_health.record_hit("card_salary")
        else:
            selector_health.record_miss("card_salary")

        # 6. Posted Date
        posted_date, date_raw = self._extract_posted_date_from_card(card)

        # 7. Snippet / Description
        snippet = self._extract_snippet_from_card(card)

        # 8. Remote Type
        remote_type = self._extract_remote_type_from_card(card, title, location, snippet)

        # 9. Experience
        experience = self._extract_experience_from_card(card, snippet)

        # 10. Industry & Company Size (Explicit from card context only)
        industry = self._extract_industry_from_card(card, title, company, snippet)
        company_size = self._extract_company_size_from_card(card, snippet)

        return JobPosting(
            id=uuid4(),
            indeed_job_id=job_id,
            job_title=title,
            company=company,
            location=location or "",
            remote_type=remote_type,
            salary_range=salary or "Not listed",
            industry=industry or "Not listed",
            company_size=company_size or "Not listed",
            experience=experience or "Not specified",
            posted_date_raw=date_raw or "",
            posted_date=posted_date,
            job_description=snippet or "",
            job_url=job_url,
            apply_url=job_url,
            country=country,
            search_query=search_query,
            scraped_at=datetime.now(tz=timezone.utc),
        )

    # =========================================================================
    # Field-Specific Card Extractors (Selectolax)
    # =========================================================================

    def _extract_title(self, card: LexborNode) -> Optional[str]:
        for sel in [
            "h2.jobTitle a span[title]",
            "h2.jobTitle span[title]",
            "h3.jobTitle a span[title]",
            "h3.jobTitle span[title]",
            "[data-testid='jobTitle'] span",
            "[data-testid='jobTitle']",
            "h2.jobTitle a",
            "h3.jobTitle a",
            "a.jcs-JobTitle span",
            "a.jcs-JobTitle",
        ]:
            el = card.css_first(sel)
            if el:
                val = clean_text(el.attributes.get("title") or el.text(deep=True, strip=True))
                if val:
                    logger.debug("[Selectolax] Extracted 'job_title'='{}' using selector='{}'", val, sel)
                    return val

        # Fallback to heading tag
        for h_sel in ["h2", "h3"]:
            h = card.css_first(h_sel)
            if h:
                a = h.css_first("a")
                val = clean_text(a.text(deep=True, strip=True) if a else h.text(deep=True, strip=True))
                if val:
                    logger.debug("[Selectolax] Extracted 'job_title'='{}' from heading tag='{}'", val, h_sel)
                    return val

        return None

    def _extract_company(self, card: LexborNode) -> Optional[str]:
        for sel in [
            "[data-testid='company-name']",
            "span[data-testid='company-name']",
            "a[data-testid='company-name']",
            ".companyName",
            "span.companyName",
            "span.company",
            ".company_location [class*='company']",
        ]:
            el = card.css_first(sel)
            if el:
                val = clean_text(el.text(deep=True, strip=True))
                if val:
                    logger.debug("[Selectolax] Extracted 'company'='{}' using selector='{}'", val, sel)
                    return val
        return None

    def _extract_location(self, card: LexborNode) -> Optional[str]:
        for sel in [
            "[data-testid='text-location']",
            "div[data-testid='text-location']",
            "div[data-testid='text-location'] span",
            ".companyLocation",
            "div.companyLocation",
            ".location",
        ]:
            el = card.css_first(sel)
            if el:
                val = clean_text(el.text(deep=True, strip=True))
                if val:
                    logger.debug("[Selectolax] Extracted 'location'='{}' using selector='{}'", val, sel)
                    return val
        return None

    def _extract_salary_from_card(self, card: LexborNode) -> Optional[str]:
        for sel in [
            "[data-testid='attribute_snippet_testid']",
            ".salary-snippet-container",
            ".salaryOnly",
            ".salary-snippet",
            ".jobMetaDataGroup [class*='salary']",
            ".metadataContainer [class*='salary']",
        ]:
            el = card.css_first(sel)
            if el:
                val = clean_text(el.text(deep=True, strip=True))
                if val and (any(c in val for c in ["$", "£", "€", "₹", "rs", "lpa", "lakh"]) or re.search(r"\d+k", val, re.IGNORECASE)):
                    logger.debug("[Selectolax] Extracted 'salary_range'='{}' using selector='{}'", val, sel)
                    return val

        for meta_item in card.css(".metadataContainer li, .jobMetaDataGroup div, .metadata div"):
            text = clean_text(meta_item.text(deep=True, strip=True))
            if any(c in text for c in ["$", "£", "€", "₹"]) and any(char.isdigit() for char in text):
                logger.debug("[Selectolax] Extracted 'salary_range'='{}' from metadata chip", text)
                return text

        return None

    def _extract_posted_date_from_card(self, card: LexborNode) -> tuple[Optional[datetime], str]:
        for sel in [
            "[data-testid='myJobsStateDate']",
            "span.date",
            ".date",
            ".result-link-source",
            "[class*='myJobsStateDate']",
        ]:
            el = card.css_first(sel)
            if el:
                raw_text = clean_text(el.text(deep=True, strip=True))
                if raw_text:
                    parsed_dt, is_ambiguous = parse_indeed_relative_date(raw_text)
                    logger.debug("[Selectolax] Extracted 'posted_date_raw'='{}' (parsed={}) using selector='{}'", raw_text, parsed_dt, sel)
                    return parsed_dt, raw_text
        return None, ""

    def _extract_snippet_from_card(self, card: LexborNode) -> Optional[str]:
        for sel in [
            "ul:not(.metadataContainer):not(.heading6)",
            "[data-testid='job-snippet']",
            ".job-snippet",
            ".underCardSnippet",
            ".jobCardShelfContainer",
            ".job-snippet ul",
        ]:
            el = card.css_first(sel)
            if el:
                val = clean_text(el.text(deep=True, strip=True))
                if val and len(val) > 10:
                    logger.debug("[Selectolax] Extracted 'job_description' snippet (len={}) using selector='{}'", len(val), sel)
                    return val
        return None

    def _extract_remote_type_from_card(self, card: LexborNode, title: str, location: Optional[str], snippet: Optional[str]) -> RemoteType:
        loc_text = (location or "").lower()
        if "remote" in loc_text and "hybrid" not in loc_text:
            return RemoteType.FULLY_REMOTE
        if "hybrid" in loc_text:
            return RemoteType.HYBRID

        for chip in card.css(".metadataContainer li, [data-testid='attribute_snippet_testid']"):
            chip_text = chip.text(deep=True, strip=True).lower()
            if "hybrid" in chip_text:
                return RemoteType.HYBRID
            if "remote" in chip_text:
                return RemoteType.FULLY_REMOTE
            if "on-site" in chip_text or "in-office" in chip_text:
                return RemoteType.ON_SITE

        remote_str = detect_remote_type(title, location or "", snippet or "")
        return RemoteType(remote_str)

    def _extract_experience_from_card(self, card: LexborNode, snippet: Optional[str]) -> Optional[str]:
        for badge in card.css("[data-testid*='qualification'], .metadataContainer li"):
            b_text = badge.text(deep=True, strip=True)
            exp = extract_experience(b_text)
            if exp and exp != "Not specified":
                logger.debug("[Selectolax] Extracted 'experience'='{}' from card qualification badge", exp)
                return exp

        if snippet:
            exp = extract_experience(snippet)
            if exp and exp != "Not specified":
                logger.debug("[Selectolax] Extracted 'experience'='{}' from card snippet", exp)
                return exp

        return None

    def _extract_industry_from_card(self, card: LexborNode, title: str, company: str, snippet: Optional[str]) -> Optional[str]:
        card_text = f"{title} {company} {snippet or ''}"
        ind = extract_industry(card_text)
        return ind if ind != "Not listed" else None

    def _extract_company_size_from_card(self, card: LexborNode, snippet: Optional[str]) -> Optional[str]:
        card_text = card.text(deep=True, separator=" ", strip=True)
        size = extract_company_size(card_text)
        return size if size != "Not listed" else None

    def _extract_job_url(self, card: LexborNode, country_input: str) -> tuple[str, str]:
        domain = resolve_country_domain(country_input)
        base = f"https://{domain}"

        job_id = card.attributes.get("data-jk", "")
        if not job_id:
            jk_el = card.css_first("[data-jk]")
            if jk_el:
                job_id = jk_el.attributes.get("data-jk", "")

        if job_id:
            return f"{base}/viewjob?jk={job_id}", job_id

        for anchor in card.css("a[href]"):
            href = anchor.attributes.get("href", "")
            if "/viewjob" in href or "/rc/clk" in href or "jk=" in href or "/pagead" in href:
                full_url = href if href.startswith("http") else base + href
                extracted_id = extract_indeed_job_id(full_url) or str(uuid4())[:12]
                return full_url, extracted_id

        first_a = card.css_first("a[href]")
        if first_a:
            href = first_a.attributes.get("href", "")
            full_url = href if href.startswith("http") else base + href
            return full_url, str(uuid4())[:12]

        return "", str(uuid4())[:12]

    # =========================================================================
    # Detail Page Enrichment (Selectolax)
    # =========================================================================

    def enrich_with_description(
        self, job: JobPosting, description_html: str
    ) -> JobPosting:
        """
        Enrich an existing JobPosting with full details from the job detail page using Selectolax.
        """
        tree = LexborHTMLParser(description_html)

        # Layer 1: JSON-LD Structured Data
        json_ld_data = self._extract_json_ld(tree)
        if json_ld_data:
            logger.debug("[Selectolax] Found JSON-LD JobPosting data for job_id={}", job.indeed_job_id)
            if not job.job_title and json_ld_data.get("title"):
                job.job_title = clean_text(json_ld_data["title"])

            if not job.company:
                org = json_ld_data.get("hiringOrganization")
                if isinstance(org, dict) and org.get("name"):
                    job.company = clean_text(org["name"])
                elif isinstance(org, str):
                    job.company = clean_text(org)

            if json_ld_data.get("datePosted") and not job.posted_date:
                try:
                    dt = datetime.fromisoformat(json_ld_data["datePosted"].replace("Z", "+00:00"))
                    job.posted_date = dt
                    job.posted_date_raw = json_ld_data["datePosted"]
                except Exception:
                    pass

            if json_ld_data.get("jobLocationType") == "TELECOMMUTE":
                job.remote_type = RemoteType.FULLY_REMOTE

            if json_ld_data.get("baseSalary") and (not job.salary_range or job.salary_range == "Not listed"):
                sal_val = self._format_json_ld_salary(json_ld_data["baseSalary"])
                if sal_val:
                    job.salary_range = sal_val

        # Layer 2: Detail Header (Title, Company, Location)
        self._enrich_header_metadata(job, tree)

        # Layer 3: Full Job Description Container
        self._enrich_full_description(job, tree)
        if job.job_description and len(job.job_description) > 30:
            job.has_full_description = True
            selector_health.record_hit("detail_job_description")
        else:
            selector_health.record_miss("detail_job_description")

        # Layer 4: Dedicated Sections (Salary, Experience, Industry, Size)
        self._enrich_detail_salary(job, tree)
        self._enrich_detail_experience(job, tree)
        self._enrich_detail_industry_and_size(job, tree)

        return job

    def _extract_json_ld(self, tree: LexborHTMLParser) -> Optional[dict]:
        for s in tree.css('script[type="application/ld+json"]'):
            try:
                raw_text = s.text(deep=True, strip=True)
                if raw_text:
                    data = json.loads(raw_text)
                    if isinstance(data, dict) and data.get("@type") == "JobPosting":
                        return data
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                                return item
            except Exception:
                continue
        return None

    def _format_json_ld_salary(self, base_salary: Any) -> Optional[str]:
        if not isinstance(base_salary, dict):
            return None
        value = base_salary.get("value")
        currency = base_salary.get("currency", "$")
        if isinstance(value, dict):
            min_v = value.get("minValue")
            max_v = value.get("maxValue")
            unit = value.get("unitText", "").lower()
            unit_str = f" per {unit}" if unit else ""
            if min_v and max_v:
                return f"{currency}{min_v:,.0f} - {currency}{max_v:,.0f}{unit_str}"
            elif min_v:
                return f"{currency}{min_v:,.0f}{unit_str}"
            elif value.get("value"):
                return f"{currency}{value.get('value'):,.0f}{unit_str}"
        return None

    def _enrich_header_metadata(self, job: JobPosting, tree: LexborHTMLParser) -> None:
        if not job.job_title:
            for sel in [
                "h1.jobsearch-JobInfoHeader-title",
                "[data-testid='jobsearch-JobInfoHeader-title']",
                "h1[class*='JobInfoHeader']",
                "h1",
            ]:
                el = tree.css_first(sel)
                if el:
                    val = clean_text(el.text(deep=True, strip=True))
                    if val:
                        job.job_title = val
                        logger.debug("[Selectolax] Detail enriched 'job_title'='{}' via selector='{}'", val, sel)
                        break

        if not job.company:
            for sel in [
                "[data-testid='inlineHeader-companyName']",
                "[data-testid='company-name']",
                ".jobsearch-CompanyInfoContainer a",
                ".jobsearch-CompanyInfoContainer span",
                "div[class*='CompanyInfo'] a",
            ]:
                el = tree.css_first(sel)
                if el:
                    val = clean_text(el.text(deep=True, strip=True))
                    if val:
                        job.company = val
                        logger.debug("[Selectolax] Detail enriched 'company'='{}' via selector='{}'", val, sel)
                        break

        if not job.location:
            for sel in [
                "[data-testid='inlineHeader-companyLocation']",
                "[data-testid='job-location']",
                ".jobsearch-JobInfoHeader-companyLocation",
                "div[class*='companyLocation']",
            ]:
                el = tree.css_first(sel)
                if el:
                    val = clean_text(el.text(deep=True, strip=True))
                    if val:
                        job.location = val
                        logger.debug("[Selectolax] Detail enriched 'location'='{}' via selector='{}'", val, sel)
                        break

    def _enrich_full_description(self, job: JobPosting, tree: LexborHTMLParser) -> None:
        desc_selectors = [
            "#jobDescriptionText",
            "div#jobDescriptionText",
            "[data-testid='jobDescription']",
            "div[data-testid='jobDescription']",
            ".jobsearch-jobDescriptionText",
            ".jobsearch-JobComponent-description",
            ".jobDescriptionContent",
            "#jobDetailsSection",
            ".jobsearch-ViewJobLayout-jobDisplay",
        ]
        for sel in desc_selectors:
            container = tree.css_first(sel)
            if container:
                # Structure-preserving extraction using recursive tags
                lines = []
                for child in container.css("h1, h2, h3, h4, h5, h6, p, li"):
                    tag_name = child.tag
                    text = clean_text(child.text(deep=True, strip=True))
                    if not text:
                        continue
                    if tag_name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                        if not any(text == l.strip("# ") for l in lines):
                            lines.append(f"\n### {text}\n")
                    elif tag_name == "li":
                        if not any(text == l.lstrip("• ") for l in lines):
                            lines.append(f"• {text}")
                    elif tag_name == "p":
                        if not any(text in l for l in lines):
                            lines.append(f"{text}\n")

                raw_text = clean_text(container.text(deep=True, separator="\n\n", strip=True))
                if lines and len(" ".join(lines)) > 50:
                    formatted_text = "\n".join(lines).strip()
                    # If raw_text captures significantly more content (e.g. unhandled divs/spans), prefer raw_text
                    if len(raw_text) > len(formatted_text) * 1.35:
                        chosen_text = raw_text
                    else:
                        chosen_text = formatted_text
                else:
                    chosen_text = raw_text

                if chosen_text and len(chosen_text) > 30:
                    job.job_description = chosen_text
                    job.has_full_description = True
                    logger.debug("[Selectolax] Detail enriched 'job_description' (len={}) via selector='{}'", len(chosen_text), sel)
                    break

    def _enrich_detail_salary(self, job: JobPosting, tree: LexborHTMLParser) -> None:
        if job.salary_range and job.salary_range != "Not listed":
            return

        for sel in [
            "#salaryInfoAndJobType",
            "[data-testid='jobsearch-OtherJobDetailsContainer']",
            "div[id*='salary']",
            "[aria-label*='Pay']",
            "[data-testid='attribute_snippet_testid']",
            "#jobDetailsSection",
        ]:
            el = tree.css_first(sel)
            if el:
                text = clean_text(el.text(deep=True, strip=True))
                sal = extract_salary_range(text)
                if sal and sal != "Not listed":
                    job.salary_range = sal
                    logger.debug("[Selectolax] Detail enriched 'salary_range'='{}' via selector='{}'", sal, sel)
                    return

        if job.job_description:
            sal = extract_salary_range(job.job_description)
            if sal and sal != "Not listed":
                job.salary_range = sal
                logger.debug("[Selectolax] Detail enriched 'salary_range'='{}' from job description", sal)

    def _enrich_detail_experience(self, job: JobPosting, tree: LexborHTMLParser) -> None:
        if job.experience and job.experience != "Not specified":
            return

        for sel in [
            "#qualificationsSection",
            "[data-testid='qualification-experience']",
            "div[class*='qualifications']",
            "div[id*='qualifications']",
        ]:
            el = tree.css_first(sel)
            if el:
                exp = extract_experience(clean_text(el.text(deep=True, strip=True)))
                if exp and exp != "Not specified":
                    job.experience = exp
                    logger.debug("[Selectolax] Detail enriched 'experience'='{}' via selector='{}'", exp, sel)
                    return

        if job.job_description:
            exp = extract_experience(job.job_description)
            if exp and exp != "Not specified":
                job.experience = exp
                logger.debug("[Selectolax] Detail enriched 'experience'='{}' from job description", exp)

    def _enrich_detail_industry_and_size(self, job: JobPosting, tree: LexborHTMLParser) -> None:
        if (not job.industry or job.industry == "Not listed") and job.job_description:
            ind = extract_industry(f"{job.job_title} {job.company} {job.job_description}")
            if ind != "Not listed":
                job.industry = ind

        if not job.company_size or job.company_size == "Not listed":
            for sel in [
                "[data-testid='company-size']",
                ".companyOverview",
                "#companyOverview",
            ]:
                el = tree.css_first(sel)
                if el:
                    size = extract_company_size(clean_text(el.text(deep=True, strip=True)))
                    if size != "Not listed":
                        job.company_size = size
                        return
            if job.job_description:
                size = extract_company_size(job.job_description)
                if size != "Not listed":
                    job.company_size = size
