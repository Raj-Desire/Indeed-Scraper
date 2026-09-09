"""
Unit Tests for Centralized Timetable Scheduler
==============================================
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from app.scheduler.timetable import (
    DEFAULT_TIMETABLE,
    TimetableManager,
    find_active_slot,
    load_timetable,
    normalize_slot_config,
    parse_slot_time,
)


def test_parse_slot_time_formats():
    """Verify various time string representations parse correctly."""
    assert parse_slot_time("13:00") == (13, 0)
    assert parse_slot_time("13:30") == (13, 30)
    assert parse_slot_time("9:15") == (9, 15)
    assert parse_slot_time("09:00") == (9, 0)
    assert parse_slot_time("13") == (13, 0)
    assert parse_slot_time("1:00 PM") == (13, 0)
    assert parse_slot_time("1PM") == (13, 0)
    assert parse_slot_time("1:30 PM") == (13, 30)
    assert parse_slot_time("11:45 AM") == (11, 45)
    assert parse_slot_time("12:00 AM") == (0, 0)
    assert parse_slot_time("12:00 PM") == (12, 0)
    assert parse_slot_time("invalid_time") is None
    assert parse_slot_time("25:00") is None


def test_normalize_slot_config():
    """Verify default values and type normalization."""
    raw = {
        "query": "sharepoint developer",
        "countries": "US,GB",
        "max_leads": "20",
    }
    norm = normalize_slot_config(raw)
    assert norm["query"] == "sharepoint developer"
    assert norm["countries"] == ["US", "GB"]
    assert norm["max_leads"] == 20
    assert norm["fromage"] == 1
    assert norm["sort_by"] == "date"
    assert norm["enabled"] is True


def test_load_timetable_creates_default_file(tmp_path: Path):
    """Verify loading from non-existent file creates template."""
    custom_path = tmp_path / "subdir" / "schedule.json"
    timetable = load_timetable(custom_path)
    assert custom_path.is_file()
    assert "13:00" in timetable
    assert timetable["13:00"]["query"] == "sharepoint"


def test_find_active_slot_matching():
    """Verify slot is matched when datetime falls in slot hour."""
    timetable = {
        "13:00": {
            "query": "sharepoint",
            "countries": ["US"],
            "max_leads": 15,
            "enabled": True,
        },
        "14:00": {
            "query": "Applied AI Engineer",
            "countries": ["US"],
            "max_leads": 15,
            "enabled": True,
        },
        "15:00": {
            "query": "Data Analyst",
            "countries": ["US"],
            "max_leads": 15,
            "enabled": False,  # Disabled
        },
    }

    # At 13:05 -> matches 13:00
    dt_1305 = datetime(2026, 9, 9, 13, 5)
    res = find_active_slot(timetable, dt_1305)
    assert res is not None
    slot_key, cfg = res
    assert slot_key == "13:00"
    assert cfg["query"] == "sharepoint"

    # At 14:00 -> matches 14:00
    dt_1400 = datetime(2026, 9, 9, 14, 0)
    res = find_active_slot(timetable, dt_1400)
    assert res is not None
    assert res[0] == "14:00"
    assert res[1]["query"] == "Applied AI Engineer"

    # At 15:00 -> disabled slot should be ignored
    dt_1500 = datetime(2026, 9, 9, 15, 0)
    res = find_active_slot(timetable, dt_1500)
    assert res is None

    # At 17:00 -> no slot configured
    dt_1700 = datetime(2026, 9, 9, 17, 0)
    res = find_active_slot(timetable, dt_1700)
    assert res is None


def test_timetable_manager_get_slot(tmp_path: Path):
    """Verify slot lookup by time string or normalized representation."""
    schedule_file = tmp_path / "schedule.json"
    content = {
        "13:00": {"query": "sharepoint", "countries": ["US"]},
        "14:30": {"query": "power platform", "countries": ["US"]},
    }
    schedule_file.write_text(json.dumps(content))

    mgr = TimetableManager(schedule_file)
    assert mgr.get_slot("13:00")["query"] == "sharepoint"
    assert mgr.get_slot("1:00 PM")["query"] == "sharepoint"
    assert mgr.get_slot("14:30")["query"] == "power platform"
    assert mgr.get_slot("2:30 PM")["query"] == "power platform"
    assert mgr.get_slot("20:00") is None
