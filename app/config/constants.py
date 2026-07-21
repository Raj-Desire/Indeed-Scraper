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
    Country("GB", "United Kingdom", "uk.indeed.com"),
    Country("CA", "Canada", "ca.indeed.com"),
    Country("AU", "Australia", "au.indeed.com"),
    Country("IN", "India", "in.indeed.com"),
    Country("AE", "United Arab Emirates", "www.indeed.ae"),
    Country("DE", "Germany", "de.indeed.com"),
    Country("NL", "Netherlands", "nl.indeed.com"),
    Country("ZA", "South Africa", "za.indeed.com"),
    Country("SG", "Singapore", "sg.indeed.com"),
    Country("IE", "Ireland", "ie.indeed.com"),
    Country("NZ", "New Zealand", "nz.indeed.com"),
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
