"""
Business Rules & Constants
==========================
Defines common target countries and domain mappings.
Supports both selecting predefined countries and typing any custom country/role.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

# India Standard Time (IST) - GMT+5:30
IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def get_ist_now() -> datetime:
    """Return the current datetime in India Standard Time (IST / GMT+5:30)."""
    return datetime.now(tz=IST)


# --- Outreach Generation Rules ---
# Tunable rules for the AI-generated outreach email/LinkedIn drafts (app.matching.outreach_generator).
# Centralized here so the pitch tone/structure can be tuned without touching the LLM-calling code.
OUTREACH_SENDER_COMPANY = "Desire Infoweb Pvt. Ltd."
OUTREACH_SENDER_BLURB = "a Microsoft Solution Partner"
OUTREACH_TEAM_SIZE = "40+"
OUTREACH_RATE_PLACEHOLDER = "[Rate]"
OUTREACH_MONTHLY_RATE_PLACEHOLDER = "$[XXXX]"
OUTREACH_ENGAGEMENT_MODELS = [
    f"Hourly Engagement - pay only for the time used - {OUTREACH_RATE_PLACEHOLDER}/hr",
    "Fixed-Cost Project - one price for a clearly defined task - price shared after understanding your needs",
    f"Monthly Dedicated Engineer - one engineer works full-time with your team - {OUTREACH_MONTHLY_RATE_PLACEHOLDER}/month",
]
OUTREACH_LINKEDIN_VARIANT_COUNT = 4
OUTREACH_LINKEDIN_MAX_CHARS = 300
OUTREACH_TONE_GUIDELINES = (
    "Professional, warm, and confident - written like a real person, not a template. Reference the "
    "specific role, company, and what the job is actually trying to accomplish (not just a tech "
    "checklist) so the opening line reads as a genuine, personal reaction to THIS posting. Avoid "
    "generic openers like 'I hope you're doing well' or 'I came across your job posting'. Keep it "
    "concise, natural, and easy to skim - the way an experienced BDE would actually write it."
)


# Canonical match_score -> Priority thresholds. Single source of truth so the
# SharePoint export, AI JD extraction, and dashboard UI never disagree on what
# a given score means.
SCORE_PRIORITY_HIGH_THRESHOLD = 70
SCORE_PRIORITY_MEDIUM_THRESHOLD = 40


def score_to_priority(score: Optional[float]) -> str:
    """Map a 0-100 match_score to 'High' / 'Medium' / 'Low'. None/unparseable -> 'Low'."""
    if score is None:
        return "Low"
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "Low"
    if value >= SCORE_PRIORITY_HIGH_THRESHOLD:
        return "High"
    if value >= SCORE_PRIORITY_MEDIUM_THRESHOLD:
        return "Medium"
    return "Low"


@dataclass(frozen=True)
class Country:
    """Represents a target country for Indeed job searches."""
    code: str
    name: str
    domain: str


# Common target countries list for UI dropdown selection - shortlisted to the
# markets we actually target after company evaluation.
COMMON_COUNTRIES: tuple[Country, ...] = (
    Country("US", "United States", "www.indeed.com"),
    Country("GB", "United Kingdom", "uk.indeed.com"),
    Country("CA", "Canada", "ca.indeed.com"),
    Country("AU", "Australia", "au.indeed.com"),
    Country("DE", "Germany", "de.indeed.com"),
    Country("NL", "Netherlands", "nl.indeed.com"),
    Country("CH", "Switzerland", "ch.indeed.com"),
    Country("AE", "United Arab Emirates", "www.indeed.ae"),
    Country("SA", "Saudi Arabia", "sa.indeed.com"),
    Country("SG", "Singapore", "sg.indeed.com"),
    Country("IE", "Ireland", "ie.indeed.com"),
    Country("ZA", "South Africa", "za.indeed.com"),
    Country("NZ", "New Zealand", "nz.indeed.com"),
    Country("DK", "Denmark", "dk.indeed.com"),
    Country("SE", "Sweden", "se.indeed.com"),
    Country("QA", "Qatar", "qa.indeed.com"),
    Country("NO", "Norway", "no.indeed.com"),
    Country("BE", "Belgium", "be.indeed.com"),
    Country("KW", "Kuwait", "kw.indeed.com"),
    Country("FR", "France", "fr.indeed.com"),
    Country("CZ", "Czech Republic", "cz.indeed.com"),
    Country("TR", "Turkey", "tr.indeed.com"),
    Country("TW", "Taiwan", "tw.indeed.com"),
)

# Map ISO country codes to domain
COUNTRY_DOMAIN_MAP: dict[str, str] = {c.code.upper(): c.domain for c in COMMON_COUNTRIES}


# Map ISO country codes to matching IANA timezone IDs.
# Used by the browser context so the fingerprinted timezone always matches
# the country being scraped (fixes the en-US locale / Asia/Kolkata mismatch).
COUNTRY_TIMEZONE_MAP: dict[str, str] = {
    "US": "America/New_York",
    "CA": "America/Toronto",
    "GB": "Europe/London",
    "IE": "Europe/Dublin",
    "DE": "Europe/Berlin",
    "FR": "Europe/Paris",
    "NL": "Europe/Amsterdam",
    "BE": "Europe/Brussels",
    "CH": "Europe/Zurich",
    "SE": "Europe/Stockholm",
    "NO": "Europe/Oslo",
    "DK": "Europe/Copenhagen",
    "CZ": "Europe/Prague",
    "TR": "Europe/Istanbul",
    "AE": "Asia/Dubai",
    "SA": "Asia/Riyadh",
    "QA": "Asia/Qatar",
    "KW": "Asia/Kuwait",
    "ZA": "Africa/Johannesburg",
    "SG": "Asia/Singapore",
    "TW": "Asia/Taipei",
    "AU": "Australia/Sydney",
    "NZ": "Pacific/Auckland",
}

# Map ISO country codes to BCP-47 locale strings.
# Keeps the browser's navigator.language consistent with the country timezone.
COUNTRY_LOCALE_MAP: dict[str, str] = {
    "US": "en-US",
    "CA": "en-CA",
    "GB": "en-GB",
    "IE": "en-IE",
    "DE": "de-DE",
    "FR": "fr-FR",
    "NL": "nl-NL",
    "BE": "nl-BE",
    "CH": "de-CH",
    "SE": "sv-SE",
    "NO": "nb-NO",
    "DK": "da-DK",
    "CZ": "cs-CZ",
    "TR": "tr-TR",
    "AE": "ar-AE",
    "SA": "ar-SA",
    "QA": "ar-QA",
    "KW": "ar-KW",
    "ZA": "en-ZA",
    "SG": "en-SG",
    "TW": "zh-TW",
    "AU": "en-AU",
    "NZ": "en-NZ",
}


def resolve_country_domain(country_input: str) -> str:
    """
    Resolve domain for any country code or name entered by the user.

    Args:
        country_input: ISO code (e.g. 'US') or country name.

    Returns:
        Indeed domain (e.g. 'www.indeed.com', 'uk.indeed.com').
    """
    inp = country_input.strip().upper()
    if inp in COUNTRY_DOMAIN_MAP:
        return COUNTRY_DOMAIN_MAP[inp]

    # Search by name match
    for c in COMMON_COUNTRIES:
        if inp == c.name.upper() or inp in c.name.upper():
            return c.domain

    # Default fallback
    return "www.indeed.com"


def resolve_country_timezone(country_input: str) -> str:
    """Return the IANA timezone ID for the given country code or name."""
    inp = country_input.strip().upper()
    if inp in COUNTRY_TIMEZONE_MAP:
        return COUNTRY_TIMEZONE_MAP[inp]
    # Name-based fallback
    for c in COMMON_COUNTRIES:
        if inp == c.name.upper() or inp in c.name.upper():
            return COUNTRY_TIMEZONE_MAP.get(c.code, "America/New_York")
    return "America/New_York"


def resolve_country_locale(country_input: str) -> str:
    """Return the BCP-47 locale string for the given country code or name."""
    inp = country_input.strip().upper()
    if inp in COUNTRY_LOCALE_MAP:
        return COUNTRY_LOCALE_MAP[inp]
    # Name-based fallback
    for c in COMMON_COUNTRIES:
        if inp == c.name.upper() or inp in c.name.upper():
            return COUNTRY_LOCALE_MAP.get(c.code, "en-US")
    return "en-US"
