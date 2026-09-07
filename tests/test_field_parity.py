"""
Field-by-Field Parity Test Suite
=================================
Tests BeautifulSoup4 and Selectolax parsers against real Indeed search results
and job detail fixtures. Outputs a detailed field-by-field parity comparison table.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from uuid import uuid4
from datetime import datetime

from app.parser.job_parser import BeautifulSoupParser
from app.parser.selectolax_parser import SelectolaxParser
from app.models.job import JobPosting, RemoteType
from tests.fixtures.fixture_279243a404f89d8b import FIXTURE_279243a404f89d8b


def run_field_comparison():
    print("=" * 100)
    print("RUNNING PARSER FIELD-BY-FIELD COMPARISON TEST")
    print("=" * 100)

    # 1. Search Results Parsing Comparison
    with open("tests/fixtures/indeed_search_results.html", "r", encoding="utf-8") as f:
        search_html = f.read()

    bs_parser = BeautifulSoupParser()
    sl_parser = SelectolaxParser()

    bs_jobs = bs_parser.parse_search_results(search_html, country="US", search_query="AI Engineer")
    sl_jobs = sl_parser.parse_search_results(search_html, country="US", search_query="AI Engineer")

    print(f"\n[Search Results Test] BS jobs parsed: {len(bs_jobs)} | Selectolax jobs parsed: {len(sl_jobs)}")
    assert len(bs_jobs) > 0, "BeautifulSoup must parse search results"
    assert len(sl_jobs) > 0, "Selectolax must parse search results"

    # Compare first search job card
    bs_j1 = bs_jobs[0]
    sl_j1 = sl_jobs[0]

    print("\n--- Card Level Comparison (First Job: jk={}) ---".format(bs_j1.indeed_job_id))
    fields_to_check = [
        "job_title", "company", "location", "country", "remote_type",
        "salary_range", "experience", "posted_date_raw", "job_url"
    ]
    
    print(f"{'Field':<20} | {'BeautifulSoup':<30} | {'Selectolax':<30} | {'Match':<8}")
    print("-" * 95)
    for field in fields_to_check:
        v_bs = str(getattr(bs_j1, field))
        v_sl = str(getattr(sl_j1, field))
        match = "PASS" if v_bs == v_sl else "DIFF"
        print(f"{field:<20} | {v_bs[:30]:<30} | {v_sl[:30]:<30} | {match:<8}")

    # 2. Detail Page Enrichment Comparison (jk=279243a404f89d8b)
    print("\n" + "=" * 100)
    print("RUNNING DETAIL PAGE ENRICHMENT TEST (jk=279243a404f89d8b)")
    print("=" * 100)

    bs_job = JobPosting(
        id=uuid4(),
        indeed_job_id="279243a404f89d8b",
        job_title="",
        company="",
        location="",
        country="US",
        job_url="https://www.indeed.com/viewjob?jk=279243a404f89d8b",
    )
    sl_job = JobPosting(
        id=uuid4(),
        indeed_job_id="279243a404f89d8b",
        job_title="",
        company="",
        location="",
        country="US",
        job_url="https://www.indeed.com/viewjob?jk=279243a404f89d8b",
    )

    bs_enriched = bs_parser.enrich_with_description(bs_job, FIXTURE_279243a404f89d8b)
    sl_enriched = sl_parser.enrich_with_description(sl_job, FIXTURE_279243a404f89d8b)

    expected_values = {
        "job_title": "Senior AI Engineer",
        "company": "TechVision Solutions",
        "location": "San Francisco, CA (Remote)",
        "country": "US",
        "remote_type": "Fully Remote",
        "salary_range": "$180,000 - $240,000 per year",
        "experience": "5+ Years Experience",
        "company_size": "250 To 500 Employees",
        "industry": "Information Technology",
        "posted_date_raw": "2026-09-05T14:30:00Z",
        "job_description_present": True,
    }

    print(f"\n{'Field':<24} | {'BeautifulSoup':<28} | {'Selectolax':<28} | {'Expected':<28} | {'Match':<6}")
    print("-" * 125)

    all_passed = True
    for field, expected in expected_values.items():
        if field == "job_description_present":
            bs_val = bool(bs_enriched.job_description and len(bs_enriched.job_description) > 50)
            sl_val = bool(sl_enriched.job_description and len(sl_enriched.job_description) > 50)
            v_bs_str = f"Extracted ({len(bs_enriched.job_description)} chars)"
            v_sl_str = f"Extracted ({len(sl_enriched.job_description)} chars)"
            exp_str = "Extracted (>50 chars)"
            match = "PASS" if bs_val == sl_val == expected else "FAIL"
        else:
            v_bs = getattr(bs_enriched, field)
            v_sl = getattr(sl_enriched, field)
            v_bs_str = str(v_bs.value if hasattr(v_bs, "value") else v_bs)
            v_sl_str = str(v_sl.value if hasattr(v_sl, "value") else v_sl)
            exp_str = str(expected)
            match = "PASS" if (v_bs_str == exp_str and v_sl_str == exp_str) else "FAIL"

        if match == "FAIL":
            all_passed = False

        print(f"{field:<24} | {v_bs_str[:28]:<28} | {v_sl_str[:28]:<28} | {exp_str[:28]:<28} | {match:<6}")

    print("-" * 125)
    if all_passed:
        print("[SUCCESS] ALL FIELDS MATCHED EXPECTED VALUES WITH 100% PARITY!")
    else:
        print("[WARNING] Some fields did not match expected values. Check details above.")

    # Print sample of extracted job description
    print("\n[Sample BeautifulSoup Extracted Description (First 250 chars)]:\n", bs_enriched.job_description[:250])
    print("\n[Sample Selectolax Extracted Description (First 250 chars)]:\n", sl_enriched.job_description[:250])


if __name__ == "__main__":
    run_field_comparison()
