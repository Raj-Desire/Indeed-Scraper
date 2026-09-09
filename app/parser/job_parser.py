"""
Job HTML Parser (BeautifulSoup4 + lxml)
=======================================
Extracts structured job data from Indeed search results and detail pages.
Implements field-specific, multi-strategy DOM extraction with full diagnostic logging.
"""

import json
import re
from datetime import datetime, timezone
from typing import Optional, Any
from uuid import uuid4

from bs4 import BeautifulSoup, Tag

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


class BeautifulSoupParser(BaseJobParser):
    """
    Parses HTML from Indeed search results and job detail pages using BeautifulSoup4 + lxml.
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
        soup = BeautifulSoup(html, "lxml")
        job_cards = self._find_job_cards(soup)

        if not job_cards:
            logger.debug("No job cards found in HTML (country={}, search_query={})", country, search_query)
            return []

        jobs: list[JobPosting] = []
        seen_ids = set()

        for card in job_cards:
            try:
                job = self._parse_job_card(card, country, search_query)
                if job:
                    # Deduplicate within same page
                    if job.indeed_job_id and job.indeed_job_id in seen_ids:
                        continue
                    if job.indeed_job_id:
                        seen_ids.add(job.indeed_job_id)
                    jobs.append(job)
            except Exception as exc:
                logger.debug("Failed to parse job card: {}", exc)

        return jobs

    def _find_job_cards(self, soup: BeautifulSoup) -> list[Tag]:
        """
        Find all job card elements on the page using structured selectors.
        """
        # Primary container: .job_seen_beacon
        cards = soup.find_all(class_=re.compile(r"job_seen_beacon|cardOutline"))
        if cards:
            selector_health.record_hit("job_cards_container")
            logger.debug("[BeautifulSoup] Found {} cards via class 'job_seen_beacon|cardOutline'", len(cards))
            return cards

        # Fallback 1: li tags containing data-jk
        li_cards = []
        for li in soup.find_all("li"):
            if li.find(attrs={"data-jk": True}) or li.get("data-jk"):
                li_cards.append(li)
        if li_cards:
            selector_health.record_miss("job_cards_container")
            selector_health.record_hit("job_cards_li_fallback")
            logger.debug("[BeautifulSoup] Found {} cards via li[data-jk]", len(li_cards))
            return li_cards

        # Fallback 2: data-jk containers directly
        jk_cards = soup.find_all(attrs={"data-jk": True})
        if jk_cards:
            selector_health.record_miss("job_cards_container")
            selector_health.record_hit("job_cards_jk_fallback")
            logger.debug("[BeautifulSoup] Found {} cards via [data-jk]", len(jk_cards))
            return jk_cards

        selector_health.record_miss("job_cards_container")
        return []

    def _parse_job_card(
        self,
        card: Tag,
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
            logger.debug("[BeautifulSoup] Field 'job_title' not found on card -> skipping card")
            return None
        selector_health.record_hit("card_job_title")

        # 2. Company Name
        company = self._extract_company(card)
        if not company:
            selector_health.record_miss("card_company")
            logger.debug("[BeautifulSoup] Field 'company' not found on card -> skipping card")
            return None
        selector_health.record_hit("card_company")

        # 3. Job URL & ID
        job_url, job_id = self._extract_job_url(card, country)
        if not job_url:
            selector_health.record_miss("card_job_url")
            logger.debug("[BeautifulSoup] Field 'job_url' not found on card -> skipping card")
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
    # Field-Specific Card Extractors (BeautifulSoup)
    # =========================================================================

    def _extract_title(self, card: Tag) -> Optional[str]:
        # Strategy 1: Heading title link span
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
            el = card.select_one(sel)
            if el:
                val = clean_text(el.get("title") or el.get_text())
                if val:
                    logger.debug("[BeautifulSoup] Extracted 'job_title'='{}' using selector='{}'", val, sel)
                    return val

        # Strategy 2: Any h2/h3 heading anchor in card
        heading = card.find(["h2", "h3"])
        if heading:
            anchor = heading.find("a")
            val = clean_text(anchor.get_text() if anchor else heading.get_text())
            if val:
                logger.debug("[BeautifulSoup] Extracted 'job_title'='{}' from heading tag='{}'", val, heading.name)
                return val

        return None

    def _extract_company(self, card: Tag) -> Optional[str]:
        # Strategy 1: Explicit company testid & class selectors
        for sel in [
            "[data-testid='company-name']",
            "span[data-testid='company-name']",
            "a[data-testid='company-name']",
            ".companyName",
            "span.companyName",
            "span.company",
            ".company_location [class*='company']",
        ]:
            el = card.select_one(sel)
            if el:
                val = clean_text(el.get_text())
                if val:
                    logger.debug("[BeautifulSoup] Extracted 'company'='{}' using selector='{}'", val, sel)
                    return val
        return None

    def _extract_location(self, card: Tag) -> Optional[str]:
        # Strategy 1: Location testid and class selectors
        for sel in [
            "[data-testid='text-location']",
            "div[data-testid='text-location']",
            "div[data-testid='text-location'] span",
            ".companyLocation",
            "div.companyLocation",
            ".location",
        ]:
            el = card.select_one(sel)
            if el:
                val = clean_text(el.get_text())
                if val:
                    logger.debug("[BeautifulSoup] Extracted 'location'='{}' using selector='{}'", val, sel)
                    return val
        return None

    def _extract_salary_from_card(self, card: Tag) -> Optional[str]:
        # Dedicated salary snippet selectors
        for sel in [
            "[data-testid='attribute_snippet_testid']",
            ".salary-snippet-container",
            ".salaryOnly",
            ".salary-snippet",
            ".jobMetaDataGroup [class*='salary']",
            ".metadataContainer [class*='salary']",
        ]:
            el = card.select_one(sel)
            if el:
                val = clean_text(el.get_text())
                # Validate that this is actually a salary / compensation item
                if val and (any(c in val for c in ["$", "£", "€", "₹", "rs", "lpa", "lakh"]) or re.search(r"\d+k", val, re.IGNORECASE)):
                    logger.debug("[BeautifulSoup] Extracted 'salary_range'='{}' using selector='{}'", val, sel)
                    return val

        # Secondary: scan metadata chips for currency symbols
        for meta_item in card.select(".metadataContainer li, .jobMetaDataGroup div, .metadata div"):
            text = clean_text(meta_item.get_text())
            if any(c in text for c in ["$", "£", "€", "₹"]) and any(char.isdigit() for char in text):
                logger.debug("[BeautifulSoup] Extracted 'salary_range'='{}' from metadata chip", text)
                return text

        return None

    def _extract_posted_date_from_card(self, card: Tag) -> tuple[Optional[datetime], str]:
        for sel in [
            "[data-testid='myJobsStateDate']",
            "span.date",
            ".date",
            ".result-link-source",
            "[class*='myJobsStateDate']",
        ]:
            el = card.select_one(sel)
            if el:
                raw_text = clean_text(el.get_text())
                if raw_text:
                    parsed_dt, is_ambiguous = parse_indeed_relative_date(raw_text)
                    logger.debug("[BeautifulSoup] Extracted 'posted_date_raw'='{}' (parsed={}) using selector='{}'", raw_text, parsed_dt, sel)
                    return parsed_dt, raw_text
        return None, ""

    def _extract_snippet_from_card(self, card: Tag) -> Optional[str]:
        for sel in [
            "ul:not(.metadataContainer):not(.heading6)",
            "[data-testid='job-snippet']",
            ".job-snippet",
            ".underCardSnippet",
            ".jobCardShelfContainer",
            ".job-snippet ul",
        ]:
            el = card.select_one(sel)
            if el:
                val = clean_text(el.get_text())
                if val and len(val) > 10:
                    logger.debug("[BeautifulSoup] Extracted 'job_description' snippet (len={}) using selector='{}'", len(val), sel)
                    return val
        return None

    def _extract_remote_type_from_card(self, card: Tag, title: str, location: Optional[str], snippet: Optional[str]) -> RemoteType:
        # Strategy 1: Dedicated workplace / remote metadata chip in card
        loc_text = (location or "").lower()
        if "remote" in loc_text and "hybrid" not in loc_text:
            return RemoteType.FULLY_REMOTE
        if "hybrid" in loc_text:
            return RemoteType.HYBRID

        # Strategy 2: Check card metadata chips
        for chip in card.select(".metadataContainer li, [data-testid='attribute_snippet_testid']"):
            chip_text = chip.get_text().lower()
            if "hybrid" in chip_text:
                return RemoteType.HYBRID
            if "remote" in chip_text:
                return RemoteType.FULLY_REMOTE
            if "on-site" in chip_text or "in-office" in chip_text:
                return RemoteType.ON_SITE

        # Strategy 3: Text analysis fallback on title + snippet
        remote_str = detect_remote_type(title, location or "", snippet or "")
        return RemoteType(remote_str)

    def _extract_experience_from_card(self, card: Tag, snippet: Optional[str]) -> Optional[str]:
        # Strategy 1: Dedicated qualification / experience badge on card
        for badge in card.select("[data-testid*='qualification'], .metadataContainer li"):
            b_text = badge.get_text()
            exp = extract_experience(b_text)
            if exp and exp != "Not specified":
                logger.debug("[BeautifulSoup] Extracted 'experience'='{}' from card qualification badge", exp)
                return exp

        # Strategy 2: Extract from snippet if present
        if snippet:
            exp = extract_experience(snippet)
            if exp and exp != "Not specified":
                logger.debug("[BeautifulSoup] Extracted 'experience'='{}' from card snippet", exp)
                return exp

        return None

    def _extract_industry_from_card(self, card: Tag, title: str, company: str, snippet: Optional[str]) -> Optional[str]:
        # Extract industry strictly if clear keywords match in title, company, or card text
        card_text = f"{title} {company} {snippet or ''}"
        ind = extract_industry(card_text)
        return ind if ind != "Not listed" else None

    def _extract_company_size_from_card(self, card: Tag, snippet: Optional[str]) -> Optional[str]:
        card_text = card.get_text(separator=" ")
        size = extract_company_size(card_text)
        return size if size != "Not listed" else None

    def _extract_job_url(self, card: Tag, country_input: str) -> tuple[str, str]:
        domain = resolve_country_domain(country_input)
        base = f"https://{domain}"

        # Strategy 1: data-jk attribute directly on card or descendant
        job_id = card.get("data-jk", "")
        if not job_id:
            jk_el = card.find(attrs={"data-jk": True})
            if jk_el:
                job_id = jk_el.get("data-jk", "")

        if job_id:
            return f"{base}/viewjob?jk={job_id}", job_id

        # Strategy 2: Anchor tag with job link
        for anchor in card.find_all("a", href=True):
            href = anchor.get("href", "")
            if "/viewjob" in href or "/rc/clk" in href or "jk=" in href or "/pagead" in href:
                full_url = href if href.startswith("http") else base + href
                extracted_id = extract_indeed_job_id(full_url) or str(uuid4())[:12]
                return full_url, extracted_id

        # Strategy 3: First anchor
        first_a = card.find("a", href=True)
        if first_a:
            href = first_a.get("href", "")
            full_url = href if href.startswith("http") else base + href
            return full_url, str(uuid4())[:12]

        return "", str(uuid4())[:12]

    # =========================================================================
    # Detail Page Enrichment (BeautifulSoup)
    # =========================================================================

    def enrich_with_description(
        self, job: JobPosting, description_html: str
    ) -> JobPosting:
        """
        Enrich an existing JobPosting with full details from the job detail page.
        Uses structured JSON-LD first, then dedicated DOM containers, then semantically structured description.
        """
        soup = BeautifulSoup(description_html, "lxml")

        # Layer 1: JSON-LD Structured Data
        json_ld_data = self._extract_json_ld(soup)
        if json_ld_data:
            logger.debug("[BeautifulSoup] Found JSON-LD JobPosting data for job_id={}", job.indeed_job_id)
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

        # Layer 2: Detail Page Header (Title, Company, Location)
        self._enrich_header_metadata(job, soup)

        # Layer 3: Full Job Description Container
        self._enrich_full_description(job, soup)
        if job.job_description and len(job.job_description) > 30:
            job.has_full_description = True
            selector_health.record_hit("detail_job_description")
        else:
            selector_health.record_miss("detail_job_description")

        # Layer 4: Dedicated Salary & Qualifications Sections
        self._enrich_detail_salary(job, soup)
        self._enrich_detail_experience(job, soup)
        self._enrich_detail_industry_and_size(job, soup)

        return job

    def _extract_json_ld(self, soup: BeautifulSoup) -> Optional[dict]:
        scripts = soup.find_all("script", type="application/ld+json")
        for s in scripts:
            try:
                if s.string:
                    data = json.loads(s.string)
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

    def _enrich_header_metadata(self, job: JobPosting, soup: BeautifulSoup) -> None:
        # Title
        if not job.job_title:
            for sel in [
                "h1.jobsearch-JobInfoHeader-title",
                "[data-testid='jobsearch-JobInfoHeader-title']",
                "h1[class*='JobInfoHeader']",
                "h1",
            ]:
                el = soup.select_one(sel)
                if el:
                    val = clean_text(el.get_text())
                    if val:
                        job.job_title = val
                        logger.debug("[BeautifulSoup] Detail enriched 'job_title'='{}' via selector='{}'", val, sel)
                        break

        # Company
        if not job.company:
            for sel in [
                "[data-testid='inlineHeader-companyName']",
                "[data-testid='company-name']",
                ".jobsearch-CompanyInfoContainer a",
                ".jobsearch-CompanyInfoContainer span",
                "div[class*='CompanyInfo'] a",
            ]:
                el = soup.select_one(sel)
                if el:
                    val = clean_text(el.get_text())
                    if val:
                        job.company = val
                        logger.debug("[BeautifulSoup] Detail enriched 'company'='{}' via selector='{}'", val, sel)
                        break

        # Location
        if not job.location:
            for sel in [
                "[data-testid='inlineHeader-companyLocation']",
                "[data-testid='job-location']",
                ".jobsearch-JobInfoHeader-companyLocation",
                "div[class*='companyLocation']",
            ]:
                el = soup.select_one(sel)
                if el:
                    val = clean_text(el.get_text())
                    if val:
                        job.location = val
                        logger.debug("[BeautifulSoup] Detail enriched 'location'='{}' via selector='{}'", val, sel)
                        break

    def _enrich_full_description(self, job: JobPosting, soup: BeautifulSoup) -> None:
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
            container = soup.select_one(sel)
            if container:
                # Structure-preserving text extraction: headings, paragraphs, list items
                lines = []
                for child in container.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "div"]):
                    tag_name = child.name
                    if tag_name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                        t = clean_text(child.get_text())
                        if t and not any(t == l.strip("# ") for l in lines):
                            lines.append(f"\n### {t}\n")
                    elif tag_name == "li":
                        t = clean_text(child.get_text())
                        if t and not any(t == l.lstrip("• ") for l in lines):
                            lines.append(f"• {t}")
                    elif tag_name in ["p", "div"] and not child.find(["p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"]):
                        t = clean_text(child.get_text())
                        if t and len(t) > 5 and not any(t in l for l in lines):
                            lines.append(f"{t}\n")

                raw_text = clean_text(container.get_text(separator="\n\n"))
                if lines and len(" ".join(lines)) > 50:
                    formatted_text = "\n".join(lines).strip()
                    if len(raw_text) > len(formatted_text) * 1.35:
                        chosen_text = raw_text
                    else:
                        chosen_text = formatted_text
                else:
                    chosen_text = raw_text

                if chosen_text and len(chosen_text) > 30:
                    job.job_description = chosen_text
                    job.has_full_description = True
                    logger.debug("[BeautifulSoup] Detail enriched 'job_description' (len={}) via selector='{}'", len(chosen_text), sel)
                    break

    def _enrich_detail_salary(self, job: JobPosting, soup: BeautifulSoup) -> None:
        if job.salary_range and job.salary_range != "Not listed":
            return

        # Strategy 1: Dedicated Detail Page Pay Section
        for sel in [
            "#salaryInfoAndJobType",
            "[data-testid='jobsearch-OtherJobDetailsContainer']",
            "div[id*='salary']",
            "[aria-label*='Pay']",
            "[data-testid='attribute_snippet_testid']",
            "#jobDetailsSection",
        ]:
            el = soup.select_one(sel)
            if el:
                text = clean_text(el.get_text())
                sal = extract_salary_range(text)
                if sal and sal != "Not listed":
                    job.salary_range = sal
                    logger.debug("[BeautifulSoup] Detail enriched 'salary_range'='{}' via selector='{}'", sal, sel)
                    return

        # Strategy 2: Extract from description if present
        if job.job_description:
            sal = extract_salary_range(job.job_description)
            if sal and sal != "Not listed":
                job.salary_range = sal
                logger.debug("[BeautifulSoup] Detail enriched 'salary_range'='{}' from job description", sal)

    def _enrich_detail_experience(self, job: JobPosting, soup: BeautifulSoup) -> None:
        if job.experience and job.experience != "Not specified":
            return

        # Strategy 1: Qualifications/Requirements DOM Section
        for sel in [
            "#qualificationsSection",
            "[data-testid='qualification-experience']",
            "div[class*='qualifications']",
            "div[id*='qualifications']",
        ]:
            el = soup.select_one(sel)
            if el:
                exp = extract_experience(clean_text(el.get_text()))
                if exp and exp != "Not specified":
                    job.experience = exp
                    logger.debug("[BeautifulSoup] Detail enriched 'experience'='{}' via selector='{}'", exp, sel)
                    return

        # Strategy 2: Extract from description text
        if job.job_description:
            exp = extract_experience(job.job_description)
            if exp and exp != "Not specified":
                job.experience = exp
                logger.debug("[BeautifulSoup] Detail enriched 'experience'='{}' from job description", exp)

    def _enrich_detail_industry_and_size(self, job: JobPosting, soup: BeautifulSoup) -> None:
        # Industry
        if (not job.industry or job.industry == "Not listed") and job.job_description:
            ind = extract_industry(f"{job.job_title} {job.company} {job.job_description}")
            if ind != "Not listed":
                job.industry = ind

        # Company Size
        if not job.company_size or job.company_size == "Not listed":
            for sel in [
                "[data-testid='company-size']",
                ".companyOverview",
                "#companyOverview",
            ]:
                el = soup.select_one(sel)
                if el:
                    size = extract_company_size(clean_text(el.get_text()))
                    if size != "Not listed":
                        job.company_size = size
                        return
            if job.job_description:
                size = extract_company_size(job.job_description)
                if size != "Not listed":
                    job.company_size = size
