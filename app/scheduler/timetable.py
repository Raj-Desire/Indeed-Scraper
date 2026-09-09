"""
Centralized Timetable Scheduler Module
=======================================
Parses, validates, and matches scheduled scraping queries based on the
daily timetable defined in config/schedule.json.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.utils.logger import logger

DEFAULT_SCHEDULE_PATH = Path("config/schedule.json")

DEFAULT_TIMETABLE = {
    "13:00": {
        "query": "sharepoint",
        "countries": ["US"],
        "max_leads": 15,
        "fromage": 1,
        "sort_by": "date",
        "enabled": True,
    },
    "14:00": {
        "query": "Applied AI Engineer",
        "countries": ["US"],
        "max_leads": 15,
        "fromage": 1,
        "sort_by": "date",
        "enabled": True,
    },
    "15:00": {
        "query": "Data Analyst",
        "countries": ["US"],
        "max_leads": 15,
        "fromage": 1,
        "sort_by": "date",
        "enabled": True,
    },
    "18:00": {
        "query": "Full Stack Developer",
        "countries": ["US"],
        "max_leads": 15,
        "fromage": 1,
        "sort_by": "date",
        "enabled": True,
    },
}


def parse_slot_time(slot_str: str) -> Optional[tuple[int, int]]:
    """
    Parse various time string representations into (hour_24, minute).
    Supported formats:
      - '13:00', '13:30', '9:15', '09:00'
      - '13' (treated as 13:00)
      - '1:00 PM', '1:00pm', '1 PM', '9 AM'
    """
    slot_clean = slot_str.strip().upper()

    # Match 12-hour format with AM/PM (e.g., '1:00 PM', '1PM', '11:30 AM')
    ampm_match = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(AM|PM)$", slot_clean)
    if ampm_match:
        hour = int(ampm_match.group(1))
        minute = int(ampm_match.group(2) or 0)
        period = ampm_match.group(3)
        if period == "PM" and hour < 12:
            hour += 12
        elif period == "AM" and hour == 12:
            hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute

    # Match 24-hour format: '13:00', '09:30'
    match_24 = re.match(r"^(\d{1,2}):(\d{2})$", slot_clean)
    if match_24:
        hour = int(match_24.group(1))
        minute = int(match_24.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute

    # Match single hour: '13', '9'
    match_hour_only = re.match(r"^(\d{1,2})$", slot_clean)
    if match_hour_only:
        hour = int(match_hour_only.group(1))
        if 0 <= hour <= 23:
            return hour, 0

    return None


def normalize_slot_config(raw_config: dict[str, Any]) -> dict[str, Any]:
    """Ensure slot configuration has all standard fields with sensible defaults."""
    countries = raw_config.get("countries", ["US"])
    if isinstance(countries, str):
        countries = [c.strip().upper() for c in countries.split(",") if c.strip()]

    return {
        "query": str(raw_config.get("query", "sharepoint")).strip(),
        "countries": countries,
        "max_leads": int(raw_config.get("max_leads", 15)),
        "fromage": int(raw_config.get("fromage", 1)),
        "sort_by": str(raw_config.get("sort_by", "date")).strip().lower(),
        "enabled": bool(raw_config.get("enabled", True)),
    }


def load_timetable(file_path: Optional[Path | str] = None) -> dict[str, dict[str, Any]]:
    """
    Load daily timetable from JSON file. If file does not exist,
    creates the default template and returns it.
    """
    path = Path(file_path) if file_path else DEFAULT_SCHEDULE_PATH

    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(json.dumps(DEFAULT_TIMETABLE, indent=2), encoding="utf-8")
            logger.info("Created default timetable config at: {}", path)
        except Exception as err:
            logger.warning("Could not persist default schedule.json: {}", err)
            return DEFAULT_TIMETABLE

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            logger.warning("Schedule file {} is not a JSON object; using default timetable.", path)
            return DEFAULT_TIMETABLE

        normalized = {}
        for slot_key, slot_val in data.items():
            if isinstance(slot_val, dict):
                normalized[slot_key] = normalize_slot_config(slot_val)
        return normalized
    except Exception as err:
        logger.error("Failed to parse timetable file {}: {}. Falling back to default.", path, err)
        return DEFAULT_TIMETABLE


def find_active_slot(
    timetable: dict[str, dict[str, Any]],
    current_dt: Optional[datetime] = None,
) -> Optional[tuple[str, dict[str, Any]]]:
    """
    Find a slot configured in the timetable that matches the given datetime.
    
    Matching strategy:
      1. Exact match on HH:MM (e.g. 13:00)
      2. Hour-level match (e.g. if current_dt is 13:05, matches slot 13:00 or 13)
         to ensure Windows Task Scheduler slight timing skews don't miss the run.
    """
    now = current_dt or datetime.now()
    now_hour = now.hour
    now_minute = now.minute

    candidates = []

    for slot_key, config in timetable.items():
        if not config.get("enabled", True):
            continue

        parsed = parse_slot_time(slot_key)
        if not parsed:
            continue

        slot_hour, slot_minute = parsed

        # Exact match (hour and minute match within 15 min window)
        if slot_hour == now_hour and abs(slot_minute - now_minute) <= 15:
            return slot_key, config

        # Hour-level match (same hour, e.g. run anytime during that hour slot)
        if slot_hour == now_hour:
            candidates.append((abs(slot_minute - now_minute), slot_key, config))

    if candidates:
        # Pick the candidate closest to current minute
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1], candidates[0][2]

    return None


class TimetableManager:
    """Convenience class to manage and query the timetable."""

    def __init__(self, schedule_path: Optional[Path | str] = None) -> None:
        self.schedule_path = Path(schedule_path) if schedule_path else DEFAULT_SCHEDULE_PATH
        self.timetable = load_timetable(self.schedule_path)

    def reload(self) -> dict[str, dict[str, Any]]:
        self.timetable = load_timetable(self.schedule_path)
        return self.timetable

    def get_current_slot(self, dt: Optional[datetime] = None) -> Optional[tuple[str, dict[str, Any]]]:
        return find_active_slot(self.timetable, current_dt=dt)

    def get_slot(self, slot_key: str) -> Optional[dict[str, Any]]:
        # Direct lookup or normalized parsed lookup
        if slot_key in self.timetable:
            return self.timetable[slot_key]

        target_parsed = parse_slot_time(slot_key)
        if not target_parsed:
            return None

        for k, v in self.timetable.items():
            k_parsed = parse_slot_time(k)
            if k_parsed and k_parsed == target_parsed:
                return v

        return None
