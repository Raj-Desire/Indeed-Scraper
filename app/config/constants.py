"""
Business Rules & Constants
==========================
Defines common target countries and domain mappings.
Supports both selecting predefined countries and typing any custom country/role.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Country:
    """Represents a target country for Indeed job searches."""
    code: str
    name: str
    domain: str


# Common target countries list for UI dropdown selection
COMMON_COUNTRIES: tuple[Country, ...] = (
    Country("US", "United States", "www.indeed.com"),
    Country("CA", "Canada", "ca.indeed.com"),
    Country("MX", "Mexico", "mx.indeed.com"),
    Country("GB", "United Kingdom", "uk.indeed.com"),
    Country("DE", "Germany", "de.indeed.com"),
    Country("FR", "France", "fr.indeed.com"),
    Country("NL", "Netherlands", "nl.indeed.com"),
    Country("BE", "Belgium", "be.indeed.com"),
    Country("IE", "Ireland", "ie.indeed.com"),
    Country("CH", "Switzerland", "ch.indeed.com"),
    Country("AT", "Austria", "at.indeed.com"),
    Country("LU", "Luxembourg", "lu.indeed.com"),
    Country("SE", "Sweden", "se.indeed.com"),
    Country("NO", "Norway", "no.indeed.com"),
    Country("DK", "Denmark", "dk.indeed.com"),
    Country("FI", "Finland", "fi.indeed.com"),
    Country("ES", "Spain", "es.indeed.com"),
    Country("PT", "Portugal", "pt.indeed.com"),
    Country("IT", "Italy", "it.indeed.com"),
    Country("GR", "Greece", "gr.indeed.com"),
    Country("PL", "Poland", "pl.indeed.com"),
    Country("RO", "Romania", "ro.indeed.com"),
    Country("BG", "Bulgaria", "bg.indeed.com"),
    Country("HR", "Croatia", "hr.indeed.com"),
    Country("SK", "Slovakia", "sk.indeed.com"),
    Country("SI", "Slovenia", "si.indeed.com"),
    Country("LT", "Lithuania", "lt.indeed.com"),
    Country("LV", "Latvia", "lv.indeed.com"),
    Country("EE", "Estonia", "ee.indeed.com"),
    Country("AE", "United Arab Emirates", "www.indeed.ae"),
    Country("SA", "Saudi Arabia", "sa.indeed.com"),
    Country("QA", "Qatar", "qa.indeed.com"),
    Country("KW", "Kuwait", "kw.indeed.com"),
    Country("BH", "Bahrain", "bh.indeed.com"),
    Country("OM", "Oman", "om.indeed.com"),
    Country("IL", "Israel", "il.indeed.com"),
    Country("JO", "Jordan", "jo.indeed.com"),
    Country("ZA", "South Africa", "za.indeed.com"),
    Country("MA", "Morocco", "ma.indeed.com"),
    Country("GH", "Ghana", "gh.indeed.com"),
    Country("CN", "China", "cn.indeed.com"),
    Country("HK", "Hong Kong", "hk.indeed.com"),
    Country("SG", "Singapore", "sg.indeed.com"),
    Country("MY", "Malaysia", "malaysia.indeed.com"),
    Country("BN", "Brunei", "bn.indeed.com"),
    Country("AU", "Australia", "au.indeed.com"),
    Country("NZ", "New Zealand", "nz.indeed.com"),
    Country("FJ", "Fiji", "fj.indeed.com"),
    Country("PG", "Papua New Guinea", "pg.indeed.com"),
    Country("BR", "Brazil", "br.indeed.com"),
    Country("PE", "Peru", "pe.indeed.com"),
    Country("EC", "Ecuador", "ec.indeed.com"),
    Country("PA", "Panama", "pa.indeed.com"),
    Country("GT", "Guatemala", "gt.indeed.com"),
    Country("GE", "Georgia", "ge.indeed.com"),
    Country("AZ", "Azerbaijan", "az.indeed.com"),
    Country("JP", "Japan", "jp.indeed.com"),
    Country("KR", "South Korea", "kr.indeed.com"),
)

# Map ISO country codes to domain
COUNTRY_DOMAIN_MAP: dict[str, str] = {c.code.upper(): c.domain for c in COMMON_COUNTRIES}


# Map ISO country codes to matching IANA timezone IDs.
# Used by the browser context so the fingerprinted timezone always matches
# the country being scraped (fixes the en-US locale / Asia/Kolkata mismatch).
COUNTRY_TIMEZONE_MAP: dict[str, str] = {
    "US": "America/New_York",
    "CA": "America/Toronto",
    "MX": "America/Mexico_City",
    "GB": "Europe/London",
    "IE": "Europe/Dublin",
    "DE": "Europe/Berlin",
    "FR": "Europe/Paris",
    "NL": "Europe/Amsterdam",
    "BE": "Europe/Brussels",
    "CH": "Europe/Zurich",
    "AT": "Europe/Vienna",
    "LU": "Europe/Luxembourg",
    "SE": "Europe/Stockholm",
    "NO": "Europe/Oslo",
    "DK": "Europe/Copenhagen",
    "FI": "Europe/Helsinki",
    "ES": "Europe/Madrid",
    "PT": "Europe/Lisbon",
    "IT": "Europe/Rome",
    "GR": "Europe/Athens",
    "PL": "Europe/Warsaw",
    "RO": "Europe/Bucharest",
    "BG": "Europe/Sofia",
    "HR": "Europe/Zagreb",
    "SK": "Europe/Bratislava",
    "SI": "Europe/Ljubljana",
    "LT": "Europe/Vilnius",
    "LV": "Europe/Riga",
    "EE": "Europe/Tallinn",
    "AE": "Asia/Dubai",
    "SA": "Asia/Riyadh",
    "QA": "Asia/Qatar",
    "KW": "Asia/Kuwait",
    "BH": "Asia/Bahrain",
    "OM": "Asia/Muscat",
    "IL": "Asia/Jerusalem",
    "JO": "Asia/Amman",
    "ZA": "Africa/Johannesburg",
    "MA": "Africa/Casablanca",
    "GH": "Africa/Accra",
    "CN": "Asia/Shanghai",
    "HK": "Asia/Hong_Kong",
    "SG": "Asia/Singapore",
    "MY": "Asia/Kuala_Lumpur",
    "BN": "Asia/Brunei",
    "AU": "Australia/Sydney",
    "NZ": "Pacific/Auckland",
    "FJ": "Pacific/Fiji",
    "PG": "Pacific/Port_Moresby",
    "BR": "America/Sao_Paulo",
    "PE": "America/Lima",
    "EC": "America/Guayaquil",
    "PA": "America/Panama",
    "GT": "America/Guatemala",
    "GE": "Asia/Tbilisi",
    "AZ": "Asia/Baku",
    "JP": "Asia/Tokyo",
    "KR": "Asia/Seoul",
}

# Map ISO country codes to BCP-47 locale strings.
# Keeps the browser's navigator.language consistent with the country timezone.
COUNTRY_LOCALE_MAP: dict[str, str] = {
    "US": "en-US",
    "CA": "en-CA",
    "MX": "es-MX",
    "GB": "en-GB",
    "IE": "en-IE",
    "DE": "de-DE",
    "FR": "fr-FR",
    "NL": "nl-NL",
    "BE": "nl-BE",
    "CH": "de-CH",
    "AT": "de-AT",
    "LU": "fr-LU",
    "SE": "sv-SE",
    "NO": "nb-NO",
    "DK": "da-DK",
    "FI": "fi-FI",
    "ES": "es-ES",
    "PT": "pt-PT",
    "IT": "it-IT",
    "GR": "el-GR",
    "PL": "pl-PL",
    "RO": "ro-RO",
    "BG": "bg-BG",
    "HR": "hr-HR",
    "SK": "sk-SK",
    "SI": "sl-SI",
    "LT": "lt-LT",
    "LV": "lv-LV",
    "EE": "et-EE",
    "AE": "ar-AE",
    "SA": "ar-SA",
    "QA": "ar-QA",
    "KW": "ar-KW",
    "BH": "ar-BH",
    "OM": "ar-OM",
    "IL": "he-IL",
    "JO": "ar-JO",
    "ZA": "en-ZA",
    "MA": "ar-MA",
    "GH": "en-GH",
    "CN": "zh-CN",
    "HK": "zh-HK",
    "SG": "en-SG",
    "MY": "en-MY",
    "BN": "ms-BN",
    "AU": "en-AU",
    "NZ": "en-NZ",
    "FJ": "en-FJ",
    "PG": "en-PG",
    "BR": "pt-BR",
    "PE": "es-PE",
    "EC": "es-EC",
    "PA": "es-PA",
    "GT": "es-GT",
    "GE": "ka-GE",
    "AZ": "az-AZ",
    "JP": "ja-JP",
    "KR": "ko-KR",
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
