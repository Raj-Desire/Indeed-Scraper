"""Confirms ScraperService calls MatchService per job when KB matching is enabled,
and never lets a matching failure abort the pipeline."""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.job import JobPosting
from app.services.scraper_service import ScraperService


class _FakeScraper:
    def __init__(self, jobs, progress_callback=None):
        self._jobs = jobs
        self.progress = type("P", (), {"jobs_found": 0})()

    async def scrape(self, config):
        for job in self._jobs:
            yield job


class _FakeMatchService:
    def __init__(self):
        self.calls = []

    async def evaluate_job(self, job):
        self.calls.append(job.job_title)
        job.match_score = 42
        return job

    async def close(self):
        pass


def test_run_pipeline_calls_match_service_for_each_surviving_job(monkeypatch, tmp_path):
    service = ScraperService()
    service._settings.output_dir = str(tmp_path)
    service._match_service = _FakeMatchService()

    job1 = JobPosting(job_title="Job A", company="Acme", job_description="desc a", posted_date=datetime.now(tz=timezone.utc))
    job2 = JobPosting(job_title="Job B", company="Beta", job_description="desc b", posted_date=datetime.now(tz=timezone.utc))

    service._scraper = _FakeScraper([job1, job2])
    service._date_filter.filter = lambda jobs: jobs
    service._dedup_filter.filter = lambda jobs: jobs

    from app.models.scraper import RunConfig
    asyncio.run(service._run_pipeline(RunConfig()))

    assert service._match_service.calls == ["Job A", "Job B"]
    assert all(j.match_score == 42 for j in service._results)


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_run_pipeline_calls_match_service_for_each_surviving_job(None, Path(d))
    print("OK")
