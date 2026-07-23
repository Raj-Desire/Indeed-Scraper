"""
Parser Module
=============
Provides unified access to parser implementations.
"""

from app.parser.base_parser import BaseJobParser
from app.parser.job_parser import BeautifulSoupParser
from app.utils.logger import logger


def get_parser(engine: str) -> BaseJobParser:
    """
    Factory function to retrieve the appropriate parser instance.
    Defaults to BeautifulSoupParser if unknown.
    """
    engine_lower = (engine or "").lower().strip()
    if engine_lower == "selectolax":
        try:
            from app.parser.selectolax_parser import SelectolaxParser
            return SelectolaxParser()
        except Exception as exc:
            logger.error("Failed to load SelectolaxParser: {}. Falling back to BeautifulSoupParser.", exc)
            return BeautifulSoupParser()
    return BeautifulSoupParser()
