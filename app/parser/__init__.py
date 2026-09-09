"""
Parser Module
=============
Provides unified access to parser implementations.
"""

from app.parser.base_parser import BaseJobParser
from app.parser.job_parser import BeautifulSoupParser
from app.utils.logger import logger


def get_parser(engine: str = "selectolax") -> BaseJobParser:
    """
    Factory function to retrieve the appropriate parser instance.
    Defaults to SelectolaxParser (3-5x faster) with automatic fallback to BeautifulSoupParser.
    """
    engine_lower = (engine or "selectolax").lower().strip()
    if engine_lower == "beautifulsoup":
        return BeautifulSoupParser()

    # Default: Try Selectolax first, gracefully fall back to BeautifulSoup if unavailable
    try:
        from app.parser.selectolax_parser import SelectolaxParser
        return SelectolaxParser()
    except Exception as exc:
        logger.warning("Failed to initialize SelectolaxParser ({}); falling back to BeautifulSoupParser.", exc)
        return BeautifulSoupParser()
