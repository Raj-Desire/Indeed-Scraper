"""
Selector Health Monitor
=======================
Tracks success and failure rates of DOM selectors across scraping runs
to proactively detect Indeed layout drift and extraction regressions.
"""

from collections import defaultdict
from app.utils.logger import logger


class SelectorHealthMonitor:
    """Monitors extraction selector hit-rates and warns when layout drift occurs."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._hits = defaultdict(int)
            cls._instance._misses = defaultdict(int)
        return cls._instance

    def record_hit(self, selector_name: str) -> None:
        """Record a successful selector extraction."""
        self._hits[selector_name] += 1

    def record_miss(self, selector_name: str) -> None:
        """Record a failed or empty selector extraction."""
        self._misses[selector_name] += 1

    def report(self) -> dict[str, dict[str, float]]:
        """Log and return selector health metrics."""
        report_data = {}
        all_selectors = set(self._hits.keys()) | set(self._misses.keys())

        if not all_selectors:
            return report_data

        logger.info("--- Selector Health Report ---")
        for sel in sorted(all_selectors):
            hits = self._hits[sel]
            misses = self._misses[sel]
            total = hits + misses
            success_rate = (hits / total * 100.0) if total > 0 else 0.0
            report_data[sel] = {
                "hits": hits,
                "misses": misses,
                "success_rate": round(success_rate, 1),
            }

            if misses > hits and total >= 5:
                logger.warning(
                    "Selector '{}' health alert: {} hits vs {} misses ({:.1f}% success) — possible layout drift!",
                    sel, hits, misses, success_rate,
                )
            else:
                logger.debug(
                    "Selector '{}': {} hits, {} misses ({:.1f}% success)",
                    sel, hits, misses, success_rate,
                )

        return report_data

    def reset(self) -> None:
        """Reset hit and miss counters."""
        self._hits.clear()
        self._misses.clear()


selector_health = SelectorHealthMonitor()
