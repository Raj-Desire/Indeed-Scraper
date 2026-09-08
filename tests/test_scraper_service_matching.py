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
    fake_match_service = _FakeMatchService()
    service._match_service = fake_match_service

    job1 = JobPosting(job_title="Job A", company="Acme", job_description="desc a", posted_date=datetime.now(tz=timezone.utc))
    job2 = JobPosting(job_title="Job B", company="Beta", job_description="desc b", posted_date=datetime.now(tz=timezone.utc))

    service._scraper = _FakeScraper([job1, job2])
    service._date_filter.filter = lambda jobs: jobs
    service._dedup_filter.filter = lambda jobs: jobs

    from app.models.scraper import RunConfig
    asyncio.run(service._run_pipeline(RunConfig()))

    assert fake_match_service.calls == ["Job A", "Job B"]
    assert all(j.match_score == 42 for j in service._results)
    # The finally block must null the reference so the next run reconstructs
    # a fresh MatchService instead of reusing closed HTTP clients.
    assert service._match_service is None


class _FlakyMatchService:
    """Raises for the first job it sees, succeeds normally for the rest."""

    def __init__(self):
        self.calls = []

    async def evaluate_job(self, job):
        self.calls.append(job.job_title)
        if len(self.calls) == 1:
            raise RuntimeError("boom")
        job.match_score = 42
        return job

    async def close(self):
        pass


def test_run_pipeline_isolates_match_service_failure_to_one_job(monkeypatch, tmp_path):
    service = ScraperService()
    service._settings.output_dir = str(tmp_path)
    fake_match_service = _FlakyMatchService()
    service._match_service = fake_match_service

    job1 = JobPosting(job_title="Job A", company="Acme", job_description="desc a", posted_date=datetime.now(tz=timezone.utc))
    job2 = JobPosting(job_title="Job B", company="Beta", job_description="desc b", posted_date=datetime.now(tz=timezone.utc))

    service._scraper = _FakeScraper([job1, job2])
    service._date_filter.filter = lambda jobs: jobs
    service._dedup_filter.filter = lambda jobs: jobs

    from app.models.scraper import RunConfig
    asyncio.run(service._run_pipeline(RunConfig()))

    assert fake_match_service.calls == ["Job A", "Job B"]
    assert [j.job_title for j in service._results] == ["Job A", "Job B"]
    assert job1.match_score is None
    assert job2.match_score == 42
    assert service._match_service is None


class _ReusableFakeMatchService:
    """Never goes dead on close() - isolates the lifecycle wiring bug from real
    Azure client behavior."""

    def __init__(self):
        self.calls = []
        self.close_count = 0

    async def evaluate_job(self, job):
        self.calls.append(job.job_title)
        job.match_score = 42
        return job

    async def close(self):
        self.close_count += 1


def test_run_pipeline_twice_reconstructs_match_service_each_time(monkeypatch, tmp_path):
    """Regression test for the bug where MatchService was constructed once in
    ScraperService.__init__ but closed on every _run_pipeline call, leaving
    run #2+ with dead HTTP clients. Confirms the finally block nulls out
    self._match_service after close(), and that a fresh match service is used
    successfully on the next run."""
    service = ScraperService()
    service._settings.output_dir = str(tmp_path)

    from app.models.scraper import RunConfig

    service._date_filter.filter = lambda jobs: jobs
    service._dedup_filter.filter = lambda jobs: jobs

    # --- Run 1 ---
    fake1 = _ReusableFakeMatchService()
    service._match_service = fake1
    job1 = JobPosting(job_title="Job A", company="Acme", job_description="desc a", posted_date=datetime.now(tz=timezone.utc))
    service._scraper = _FakeScraper([job1])

    asyncio.run(service._run_pipeline(RunConfig()))

    assert fake1.calls == ["Job A"]
    assert fake1.close_count == 1
    assert job1.match_score == 42
    assert service._match_service is None

    # --- Run 2 ---
    fake2 = _ReusableFakeMatchService()
    service._match_service = fake2
    job2 = JobPosting(job_title="Job B", company="Beta", job_description="desc b", posted_date=datetime.now(tz=timezone.utc))
    service._scraper = _FakeScraper([job2])

    asyncio.run(service._run_pipeline(RunConfig()))

    assert fake2.calls == ["Job B"]
    assert fake2.close_count == 1
    assert job2.match_score == 42
    assert service._match_service is None


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_run_pipeline_calls_match_service_for_each_surviving_job(None, Path(d))
        test_run_pipeline_twice_reconstructs_match_service_each_time(None, Path(d))
    print("OK")
