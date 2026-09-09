"""
Browser Fingerprint Profiles Per Target Country
================================================
Provides tailored HTTP Accept-Language headers, locales, timezones,
and currency tokens to prevent regional fingerprint contradictions.
"""

from typing import TypedDict


class BrowserProfile(TypedDict):
    locale: str
    timezone_id: str
    accept_language: str
    currency: str


BROWSER_PROFILES: dict[str, BrowserProfile] = {
    "US": {
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "accept_language": "en-US,en;q=0.9",
        "currency": "USD",
    },
    "GB": {
        "locale": "en-GB",
        "timezone_id": "Europe/London",
        "accept_language": "en-GB,en;q=0.9",
        "currency": "GBP",
    },
    "CA": {
        "locale": "en-CA",
        "timezone_id": "America/Toronto",
        "accept_language": "en-CA,en-US;q=0.9,en;q=0.8,fr-CA;q=0.7",
        "currency": "CAD",
    },
    "AU": {
        "locale": "en-AU",
        "timezone_id": "Australia/Sydney",
        "accept_language": "en-AU,en-GB;q=0.9,en;q=0.8",
        "currency": "AUD",
    },
    "IN": {
        "locale": "en-IN",
        "timezone_id": "Asia/Kolkata",
        "accept_language": "en-IN,en-GB;q=0.9,en;q=0.8,hi;q=0.6",
        "currency": "INR",
    },
    "DE": {
        "locale": "de-DE",
        "timezone_id": "Europe/Berlin",
        "accept_language": "de-DE,de;q=0.9,en;q=0.8",
        "currency": "EUR",
    },
    "FR": {
        "locale": "fr-FR",
        "timezone_id": "Europe/Paris",
        "accept_language": "fr-FR,fr;q=0.9,en;q=0.8",
        "currency": "EUR",
    },
    "NL": {
        "locale": "nl-NL",
        "timezone_id": "Europe/Amsterdam",
        "accept_language": "nl-NL,nl;q=0.9,en;q=0.8",
        "currency": "EUR",
    },
    "ES": {
        "locale": "es-ES",
        "timezone_id": "Europe/Madrid",
        "accept_language": "es-ES,es;q=0.9,en;q=0.8",
        "currency": "EUR",
    },
    "IT": {
        "locale": "it-IT",
        "timezone_id": "Europe/Rome",
        "accept_language": "it-IT,it;q=0.9,en;q=0.8",
        "currency": "EUR",
    },
    "IE": {
        "locale": "en-IE",
        "timezone_id": "Europe/Dublin",
        "accept_language": "en-IE,en-GB;q=0.9,en;q=0.8",
        "currency": "EUR",
    },
    "SG": {
        "locale": "en-SG",
        "timezone_id": "Asia/Singapore",
        "accept_language": "en-SG,en;q=0.9,zh-CN;q=0.7",
        "currency": "SGD",
    },
    "NZ": {
        "locale": "en-NZ",
        "timezone_id": "Pacific/Auckland",
        "accept_language": "en-NZ,en-GB;q=0.9,en;q=0.8",
        "currency": "NZD",
    },
    "AE": {
        "locale": "en-AE",
        "timezone_id": "Asia/Dubai",
        "accept_language": "en-AE,en;q=0.9,ar;q=0.8",
        "currency": "AED",
    },
    "SA": {
        "locale": "ar-SA",
        "timezone_id": "Asia/Riyadh",
        "accept_language": "ar-SA,ar;q=0.9,en;q=0.8",
        "currency": "SAR",
    },
    "ZA": {
        "locale": "en-ZA",
        "timezone_id": "Africa/Johannesburg",
        "accept_language": "en-ZA,en-GB;q=0.9,en;q=0.8",
        "currency": "ZAR",
    },
    "CH": {
        "locale": "de-CH",
        "timezone_id": "Europe/Zurich",
        "accept_language": "de-CH,de;q=0.9,fr;q=0.8,en;q=0.7",
        "currency": "CHF",
    },
    "SE": {
        "locale": "sv-SE",
        "timezone_id": "Europe/Stockholm",
        "accept_language": "sv-SE,sv;q=0.9,en;q=0.8",
        "currency": "SEK",
    },
    "BR": {
        "locale": "pt-BR",
        "timezone_id": "America/Sao_Paulo",
        "accept_language": "pt-BR,pt;q=0.9,en;q=0.8",
        "currency": "BRL",
    },
    "MX": {
        "locale": "es-MX",
        "timezone_id": "America/Mexico_City",
        "accept_language": "es-MX,es;q=0.9,en;q=0.8",
        "currency": "MXN",
    },
    "JP": {
        "locale": "ja-JP",
        "timezone_id": "Asia/Tokyo",
        "accept_language": "ja-JP,ja;q=0.9,en;q=0.8",
        "currency": "JPY",
    },
}

DEFAULT_BROWSER_PROFILE: BrowserProfile = {
    "locale": "en-US",
    "timezone_id": "America/New_York",
    "accept_language": "en-US,en;q=0.9",
    "currency": "USD",
}


def get_browser_profile(country: str) -> BrowserProfile:
    """Retrieve the full fingerprint browser profile for a given country code."""
    code = (country or "US").strip().upper()
    return BROWSER_PROFILES.get(code, DEFAULT_BROWSER_PROFILE)
