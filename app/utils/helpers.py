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
from app.config.constants import resolve_country_domain


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
    # Normalize unicode hyphens/dashes and quotes
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    text = text.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
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
    Attempt to extract salary/rate/compensation information from job text or description.

    Args:
        text: Job description text or card text.

    Returns:
        Salary range string or "Not listed".
    """
    if not text:
        return "Not listed"

    # Pattern 1: Explicit Compensation label e.g. "Compensation: $250,000–$500,000 + 1%-5% equity" or "Pay: $120,000/yr"
    p_comp = re.search(
        r"(?:(?:salary|compensation|pay|rate)\s*[:\-–]\s*)([\$£€₹Rs\.\d,\s–—\-\+kK%a-zA-Z/]+?(?:year|yr|annum|pa|hour|hr|day|month|mo|equity|bonus|\n|$))",
        text,
        re.IGNORECASE,
    )
    if p_comp:
        candidate = p_comp.group(1).strip()
        # Must have at least one digit AND currency or frequency indicator
        if any(char.isdigit() for char in candidate) and (any(c in candidate for c in ["$", "£", "€", "₹", "Rs", "LPA", "lakh"]) or re.search(r"\d+k", candidate, re.IGNORECASE)):
            candidate_clean = candidate.split("\n")[0].strip()
            if len(candidate_clean) > 3:
                return candidate_clean

    patterns = [
        # $250,000 - $500,000 a year / per year / etc.
        r"(\$[\d,]+(?:\s*[\-–—to]+\s*\$?[\d,]+)?(?:\s*(?:\+|plus\s+)?(?:\d+[%–—\-]+)?(?:\s*equity|\s*bonus)?)?(?:\s*(?:a|per\s*)?(?:year|yr|annum|pa|hour|hr|day|month|mo))?)",
        r"(£[\d,]+(?:\s*[\-–—to]+\s*£?[\d,]+)?(?:\s*(?:a|per\s*)?(?:year|yr|annum|pa|hour|hr|day|month|mo))?)",
        r"(€[\d,]+(?:\s*[\-–—to]+\s*€?[\d,]+)?(?:\s*(?:a|per\s*)?(?:year|yr|annum|pa|hour|hr|day|month|mo))?)",
        r"(₹\s*[\d,]+(?:\s*[\-–—to]+\s*₹?\s*[\d,]+)?(?:\s*(?:a|per\s*)?(?:year|yr|annum|pa|hour|hr|day|month|mo|lakh|lpa))?)",
        r"(Rs\.?\s*[\d,]+(?:\s*[\-–—to]+\s*Rs\.?\s*[\d,]+)?(?:\s*(?:a|per\s*)?(?:year|yr|annum|pa|hour|hr|day|month|mo|lakh|lpa))?)",
        r"([\d,.]+\s*(?:Lakh|LPA|Lakhs)\s*[\-–—to]+\s*[\d,.]+\s*(?:Lakh|LPA|Lakhs)?)",
        r"([\d,]+k?\s*[\-–—to]+\s*[\d,]+k?\s*(?:USD|GBP|EUR|AUD|CAD|INR)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = match.group(1).strip()
            if any(char.isdigit() for char in val) and (any(c in val for c in ["$", "£", "€", "₹", "Rs", "LPA", "lakh"]) or re.search(r"\d+k", val, re.IGNORECASE)):
                return val
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


def get_indeed_search_url(
    country_input: str,
    query: str,
    location: str = "",
    page: int = 0,
    fromage: str = "all",
) -> str:
    """
    Build an Indeed search URL for any country, query, page, and date posted filter.
    """
    domain = resolve_country_domain(country_input)
    start = page * 10
    params = {
        "q": query.strip(),
        "start": start,
        "sort": "date",
    }
    if location:
        params["l"] = location.strip()
    if fromage and str(fromage).strip().lower() != "all":
        params["fromage"] = str(fromage).strip()

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


COMMON_INDUSTRIES = [
    ("Information Technology", [r"\bIT\b", r"software", r"technology", r"computer", r"cloud", r"cybersecurity", r"data science", r"\bai\b", r"machine learning", r"systems"]),
    ("Healthcare & Life Sciences", [r"health", r"pharma", r"medical", r"clinical", r"biotech", r"hospital", r"nursing", r"healthcare"]),
    ("Financial Services & Banking", [r"finance", r"financial", r"banking", r"bank\b", r"investment", r"accounting", r"fintech"]),
    ("Engineering & Construction", [r"engineering", r"engineer\b", r"construction", r"civil", r"mechanical", r"electrical"]),
    ("Management & Consulting", [r"consulting", r"advisory", r"management consulting", r"\bpmo\b", r"strategy"]),
    ("Marketing & Advertising", [r"marketing", r"advertising", r"media", r"\bpr\b", r"digital marketing", r"\bseo\b"]),
    ("Education & Training", [r"education", r"university", r"school", r"teaching", r"academic"]),
    ("Retail & E-commerce", [r"retail", r"e-commerce", r"ecommerce", r"sales", r"store"]),
    ("Manufacturing & Logistics", [r"manufacturing", r"logistics", r"supply chain", r"warehouse", r"operations"]),
]


def extract_industry(text: str) -> str:
    """Extract industry name based on keywords in title, company, or description."""
    if not text:
        return "Not listed"
    for industry_name, patterns in COMMON_INDUSTRIES:
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                return industry_name
    return "Not listed"


def extract_company_size(text: str) -> str:
    """Extract company workforce size if mentioned in card text or description."""
    if not text:
        return "Not listed"

    match = re.search(r"(\b\d{1,3}(?:,\d{3})*(?:\+|\s*(?:to|-)\s*\d{1,3}(?:,\d{3})*)?\s*employees?\b)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip().title()

    match_size = re.search(r"company size:?\s*([\d,+-]+(?:\s*employees)?)", text, re.IGNORECASE)
    if match_size:
        return match_size.group(1).strip().title()

    return "Not listed"


def extract_experience(text: str) -> str:
    """
    Extract experience requirements/criteria mentioned in job text, card, or description.
    
    Examples extracted:
    - "3+ years of experience" -> "3+ Years Of Experience"
    - "5-7 years experience" -> "5-7 Years Experience"
    - "Minimum 2 years" -> "Minimum 2 Years"
    - "Skills required: Python (3+ yrs)" -> "3+ Yrs Experience"
    - "Fresher" / "Entry level" -> "Entry Level / Fresher"
    """
    if not text:
        return "Not specified"

    # Check for entry level / fresher keywords
    if re.search(r"\b(entry[\s-]level|fresher|freshers|no\s+experience\s+required|0\s*[-–]\s*1\s*(?:years?|yrs?))\b", text, re.IGNORECASE):
        return "Entry Level / Fresher"

    # Pattern 1: Explicit labels like "Experience: 2-7 years", "Work Experience: 3 to 5 yrs", "Min. 4+ Years"
    explicit_patterns = [
        r"(?:experience|exp|work\s+experience|relevant\s+experience)\s*[:\-–—]\s*(\d{1,2}(?:\s*[\-–—to]+\s*\d{1,2})?\+?\s*(?:years?|yrs?|months?|mos?)(?:\s*(?:of)?\s*(?:relevant|hands[\-–—\s]on|professional|work)?\s*experience)?)",
        r"(?:minimum|min\.?|at\s+least)\s+(\d{1,2}(?:\s*[\-–—to]+\s*\d{1,2})?\+?\s*(?:years?|yrs?))",
        r"(\d{1,2}(?:\s*[\-–—to]+\s*\d{1,2})?\+?\s*(?:years?|yrs?))\s+(?:of\s+)?(?:experience|proven\s+experience|relevant\s+experience)",
    ]
    for pat in explicit_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            clean_res = re.sub(r"[–—]", "-", m.group(1).strip())
            clean_res = re.sub(r"\s+", " ", clean_res)
            return f"{clean_res.title()} Experience"

    # Pattern 2: e.g. "2-7 years", "3+ years of experience", "5 to 8 years experience", "1-3 yrs exp"
    p1 = re.search(
        r"(\b\d{1,2}\s*(?:\+|[\-–—\s]*\d{1,2})?\s*(?:to\s*\d{1,2}\s*)?(?:years?|yrs?)(?:\s+(?:of\s+)?(?:experience|exp|relevant\s+experience|professional\s+experience))?\b)",
        text,
        re.IGNORECASE,
    )
    if p1:
        match_str = p1.group(1).strip()
        match_str = re.sub(r"\s+", " ", match_str)
        if not re.search(r"experience|exp", match_str, re.IGNORECASE):
            start_pos = max(0, p1.start() - 35)
            end_pos = min(len(text), p1.end() + 35)
            surrounding = text[start_pos:end_pos].lower()
            if any(k in surrounding for k in ["experience", "exp", "background", "minimum", "req", "proven", "skills", "must have", "qualif"]):
                return f"{match_str.title()} Experience"
            elif "+" in match_str or "-" in match_str or "to" in match_str.lower():
                return f"{match_str.title()} Experience"
        else:
            return match_str.title()

    # Pattern 3: e.g. "Minimum 3 years", "At least 5 years", "Must have 2+ years"
    p3 = re.search(
        r"(\b(?:minimum|min|at\s+least|must\s+have|require[sd]?)\s+\d{1,2}\s*(?:\+|-\s*\d{1,2})?\s*(?:years?|yrs?)(?:\s+of\s+experience)?\b)",
        text,
        re.IGNORECASE,
    )
    if p3:
        return p3.group(1).strip().title()

    # Pattern 4: Skill parenthetical / bullet pattern e.g. "Python (3+ years)" or "React (2+ yrs)"
    p_skill = re.search(
        r"(?:\([^\)]*?(\d{1,2}\+?\s*(?:years?|yrs?))[^\)]*?\))",
        text,
        re.IGNORECASE,
    )
    if p_skill:
        return f"{p_skill.group(1).strip().title()} Experience"

    return "Not specified"



