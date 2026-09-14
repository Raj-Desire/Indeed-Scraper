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


def test_job_posting_summary_fallback_and_override():
    job = JobPosting(
        job_title="Software Engineer",
        company="Tech Co",
        job_description="About the job: We are looking for a Senior React Developer to design scalable cloud web apps.",
    )
    # Default fallback summary extracts from description
    assert "Senior React Developer" in job.summary

    # Explicit job_summary overrides fallback
    job.job_summary = "Custom 2-sentence summary of the job."
    assert job.summary == "Custom 2-sentence summary of the job."


if __name__ == "__main__":
    test_job_posting_has_match_fields_with_safe_defaults()
    test_job_posting_existing_fields_still_work()
    test_job_posting_match_fields_are_settable()
    test_job_posting_summary_fallback_and_override()
    print("OK")
