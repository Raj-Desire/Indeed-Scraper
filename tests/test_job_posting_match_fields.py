"""Confirms JobPosting carries KB-match fields without breaking existing fields."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.job import JobPosting


def test_job_posting_has_match_fields_with_safe_defaults():
    job = JobPosting(job_title="SharePoint Developer", company="Acme Corp")
    assert job.match_score is None
    assert job.matched_skills == []
    assert job.missing_skills == []
    assert job.match_reason == ""


def test_job_posting_existing_fields_still_work():
    job = JobPosting(job_title="Data Engineer", company="Beta LLC", location="Remote")
    assert job.job_title == "Data Engineer"
    assert job.company == "Beta LLC"
    assert job.location_remote_type  # existing property still computed


def test_job_posting_match_fields_are_settable():
    job = JobPosting(job_title="X", company="Y")
    job.match_score = 85
    job.matched_skills = ["Python", "Azure"]
    job.missing_skills = ["Dynamics 365"]
    job.match_reason = "Strong overlap on Python/Azure"
    dumped = job.model_dump()
    assert dumped["match_score"] == 85
    assert dumped["matched_skills"] == ["Python", "Azure"]


if __name__ == "__main__":
    test_job_posting_has_match_fields_with_safe_defaults()
    test_job_posting_existing_fields_still_work()
    test_job_posting_match_fields_are_settable()
    print("OK")
