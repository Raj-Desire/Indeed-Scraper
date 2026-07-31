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
