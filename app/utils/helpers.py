"""
Shared Utility Helpers
======================
Date parsing, text cleaning, URL normalization, and other small utilities
used across multiple modules.
"""

import re
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from app.utils.logger import logger


# =============================================================================
# Date Parsing
# =============================================================================

def parse_indeed_relative_date(raw_date: str) -> tuple[Optional[datetime], bool]:
    """
    Parse Indeed's relative date strings into absolute UTC datetimes.

    Indeed shows dates like:
    - "Just posted"
    - "Posted today"
    - "1 day ago" / "2 days ago"
    - "X hours ago"
    - "30+ days ago"
    - An actual date like "July 15, 2025"

    Returns:
        Tuple of (parsed_datetime_or_None, is_ambiguous)
        - parsed_datetime: UTC datetime approximation, or None if unparseable
        - is_ambiguous: True if the date string was unclear/missing
    """
    if not raw_date:
        return None, True

    now = datetime.now(tz=timezone.utc)
    text = raw_date.lower().strip()

    # "just posted", "today", "posted today"
    if any(token in text for token in ["just posted", "posted today", "today"]):
        return now, False

    # "X hours ago"
    hours_match = re.search(r"(\d+)\s*hour", text)
    if hours_match:
        hours = int(hours_match.group(1))
        return now - timedelta(hours=hours), False

    # "1 day ago" — treat as borderline (within window)
    if re.search(r"^1\s*day\s*ago", text):
        return now - timedelta(hours=23), False

    # "2+ days ago" — outside our 24h window
    days_match = re.search(r"(\d+)\+?\s*day", text)
    if days_match:
        days = int(days_match.group(1))
        return now - timedelta(days=days), False

    # "30+ days ago"
    if "30+" in text or "month" in text:
        return now - timedelta(days=31), False

    # Try parsing absolute date formats
    date_formats = [
        "%B %d, %Y",      # July 15, 2025
        "%b %d, %Y",      # Jul 15, 2025
        "%Y-%m-%d",        # 2025-07-15
        "%d/%m/%Y",        # 15/07/2025
        "%m/%d/%Y",        # 07/15/2025
    ]
    for fmt in date_formats:
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=timezone.utc), False
        except ValueError:
            continue

    logger.debug("Could not parse date string: '{}'", raw_date)
    return None, True


def is_within_age_limit(posted_date: Optional[datetime], max_hours: int = 24) -> bool:
    """
    Check whether a job was posted within the allowed age window.

    Args:
        posted_date: Parsed UTC datetime of when the job was posted.
        max_hours: Maximum age in hours (default 24 = last 24 hours only).

    Returns:
        True if the job is within the window, False otherwise.
    """
    if posted_date is None:
        return False
    now = datetime.now(tz=timezone.utc)
    if posted_date.tzinfo is None:
        posted_date = posted_date.replace(tzinfo=timezone.utc)
    age = now - posted_date
    return age.total_seconds() <= (max_hours * 3600)


# =============================================================================
# Text Cleaning
# =============================================================================

def clean_text(text: str) -> str:
    """
    Strip HTML tags, normalize whitespace, and remove non-printable characters.

    Args:
        text: Raw text or HTML string.

    Returns:
        Cleaned plain text string.
    """
    if not text:
        return ""
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common HTML entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"')
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def truncate_text(text: str, max_length: int = 500, suffix: str = "...") -> str:
    """Truncate text to max_length characters, appending suffix if truncated."""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def extract_salary_range(text: str) -> str:
    """
    Attempt to extract salary/rate information from job description text.

    Args:
        text: Job description text.

    Returns:
        Salary range string or "Not listed".
    """
    patterns = [
        r"\$[\d,]+(?:\s*[-–]\s*\$[\d,]+)?(?:\s*(?:per\s*)?(?:year|yr|annum|pa|hour|hr|day))?",
        r"£[\d,]+(?:\s*[-–]\s*£[\d,]+)?(?:\s*(?:per\s*)?(?:year|yr|annum|pa|hour|hr|day))?",
        r"€[\d,]+(?:\s*[-–]\s*€[\d,]+)?(?:\s*(?:per\s*)?(?:year|yr|annum|pa|hour|hr|day))?",
        r"[\d,]+k?\s*[-–]\s*[\d,]+k?\s*(?:USD|GBP|EUR|AUD|CAD)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return "Not listed"


# =============================================================================
# URL Utilities
# =============================================================================

def extract_indeed_job_id(url: str) -> str:
    """
    Extract Indeed's internal job ID (jk parameter) from a job URL.

    Args:
        url: Full Indeed job URL.

    Returns:
        The 'jk' parameter value, or a hash of the URL if not found.
    """
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if "jk" in params:
            return params["jk"][0]
        # For /viewjob URLs, the ID may be in the path
        path_match = re.search(r"jk=([a-f0-9]+)", url)
        if path_match:
            return path_match.group(1)
    except Exception:
        pass
    # Fallback: hash the URL
    return hashlib.md5(url.encode()).hexdigest()[:16]


def normalize_indeed_url(url: str) -> str:
    """
    Normalize an Indeed URL by removing tracking parameters.
    Keeps only the 'jk' parameter for clean deduplication.

    Args:
        url: Raw Indeed URL with tracking params.

    Returns:
        Cleaned URL with only essential parameters.
    """
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        # Keep only the job key parameter
        clean_params = {}
        if "jk" in params:
            clean_params["jk"] = params["jk"][0]
        clean_query = urlencode(clean_params)
        return urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, "", clean_query, "")
        )
    except Exception:
        return url


# =============================================================================
# Indeed Domain Mapping
# =============================================================================

INDEED_DOMAIN_MAP: dict[str, str] = {
    "US": "www.indeed.com",
    "CA": "ca.indeed.com",
    "GB": "uk.indeed.com",
    "AU": "au.indeed.com",
    "NZ": "nz.indeed.com",
    "DE": "de.indeed.com",
    "NL": "nl.indeed.com",
    "CH": "www.indeed.ch",
    "SE": "se.indeed.com",
    "NO": "no.indeed.com",
    "DK": "dk.indeed.com",
    "FI": "fi.indeed.com",
    "IE": "ie.indeed.com",
    "BE": "be.indeed.com",
    "FR": "fr.indeed.com",
    "SG": "sg.indeed.com",
    "AE": "www.indeed.ae",
    "SA": "sa.indeed.com",
    "ZA": "za.indeed.com",
    "JP": "jp.indeed.com",
    "KR": "kr.indeed.com",
}


from app.config.constants import resolve_country_domain

def get_indeed_search_url(
    country_input: str,
    query: str,
    location: str = "remote",
    page: int = 0,
) -> str:
    """
    Build an Indeed search URL for any country, query, and page.
    """
    domain = resolve_country_domain(country_input)
    start = page * 10
    params = {
        "q": query.strip(),
        "l": location,
        "start": start,
        "sort": "date",
    }
    query_string = urlencode(params)
    return f"https://{domain}/jobs?{query_string}"


# =============================================================================
# Text Analysis Helpers
# =============================================================================

def count_keyword_matches(text: str, keywords: list[str]) -> int:
    """
    Count how many keywords from the list appear in the text (case-insensitive).

    Args:
        text: Text to search within.
        keywords: List of keyword strings.

    Returns:
        Count of matching keywords.
    """
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in text_lower)


def any_keyword_matches(text: str, keywords: list[str]) -> bool:
    """Return True if any keyword appears in the text."""
    return count_keyword_matches(text, keywords) > 0


def detect_remote_type(title: str, location: str, description: str) -> str:
    """
    Detect the remote type of a job from its text fields.

    Args:
        title: Job title.
        location: Location field.
        description: Full job description.

    Returns:
        RemoteType enum value string.
    """
    combined = f"{title} {location} {description}".lower()

    if any(term in combined for term in ["fully remote", "100% remote", "work from anywhere", "remote only"]):
        return "Fully Remote"
    if any(term in combined for term in ["hybrid", "remote/hybrid", "hybrid remote"]):
        return "Hybrid"
    if "remote" in combined:
        return "Fully Remote"
    if any(term in combined for term in ["on-site", "onsite", "in-office", "in office"]):
        return "On-Site"
    return "Unknown"


def generate_job_fingerprint(title: str, company: str) -> str:
    """
    Generate a deduplication fingerprint from job title and company.
    Used as secondary dedup when Indeed job ID is not available.

    Args:
        title: Job title (normalized).
        company: Company name (normalized).

    Returns:
        MD5 hash string.
    """
    normalized = f"{title.lower().strip()}|{company.lower().strip()}"
    return hashlib.md5(normalized.encode()).hexdigest()


STOP_WORDS = {"in", "of", "for", "the", "a", "an", "at", "by", "on", "with", "and", "or", "to", "all", "is", "are"}

ROLE_SYNONYMS = {
    "developer": [r"developer", r"engineer", r"programmer", r"architect", r"specialist", r"coder", r"lead", r"consultant"],
    "engineer": [r"engineer", r"developer", r"programmer", r"architect", r"specialist", r"coder", r"lead", r"consultant"],
    "ai": [r"\bai\b", r"artificial\s+intelligence", r"genai", r"generative\s+ai", r"llm", r"large\s+language\s+model", r"machine\s+learning", r"deep\s+learning", r"neural", r"nlp", r"chatgpt", r"gpt"],
    "ml": [r"\bml\b", r"machine\s+learning", r"deep\s+learning", r"data\s+science", r"data\s+scientist"],
}


def is_job_matching_query(job_title: str, company: str, location: str, description: str, query: str) -> bool:
    """
    Check if a job posting matches the search query.
    Ensures short tech acronyms (e.g. 'AI', 'ML') match on word boundaries or domain synonyms,
    and requires all non-stopword query tokens to match.
    """
    cleaned_query = query.lower().replace('"', '').strip()
    if not cleaned_query:
        return True

    tokens = [t.strip() for t in cleaned_query.replace(",", " ").split() if t.strip()]
    meaningful_tokens = [t for t in tokens if t not in STOP_WORDS]

    if not meaningful_tokens:
        return True

    combined_text = f"{job_title} {company} {location} {description}".lower()

    for token in meaningful_tokens:
        patterns = []
        if token in ROLE_SYNONYMS:
            patterns.extend(ROLE_SYNONYMS[token])
        else:
            escaped = re.escape(token)
            if len(token) <= 2:
                patterns.append(rf"\b{escaped}\b")
            else:
                patterns.append(rf"\b{escaped}\b" if token.isalnum() else escaped)

        token_matched = any(re.search(pat, combined_text, re.IGNORECASE) for pat in patterns)
        if not token_matched:
            return False

    return True

