import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.direct_matcher.direct_match_service import (
    DirectMatchRequest,
    DirectMatchResponse,
    DirectMatchOrchestrator,
)
from app.models.job import JobPosting


def test_direct_match_orchestrator_evaluation():
    # Mock match service & sp exporter
    mock_match_service = MagicMock()

    async def mock_eval(job: JobPosting):
        job.match_score = 88
        job.matched_skills = ["SharePoint", "SPFx", "TypeScript"]
        job.missing_skills = ["GraphQL"]
        job.match_reason = "Excellent match for SPFx developer profile in Knowledge Base."
        job.job_summary = "Builds custom Web Parts and extensions."
        return job

    mock_match_service.evaluate_job = AsyncMock(side_effect=mock_eval)

    mock_sp_exporter = MagicMock()
    mock_sp_exporter.export_jobs = AsyncMock(return_value=1)

    orchestrator = DirectMatchOrchestrator(
        match_service=mock_match_service,
        sp_exporter=mock_sp_exporter,
    )

    req = DirectMatchRequest(
        job_title="Senior SharePoint Architect",
        company="Contoso Ltd",
        country="US",
        job_description="Seeking a Senior SPFx TypeScript developer with 5+ years of experience in SharePoint Online.",
        auto_sharepoint_save=True,
    )

    resp: DirectMatchResponse = asyncio.run(orchestrator.evaluate_direct_jd(req))

    assert resp.job_title == "Senior SharePoint Architect"
    assert resp.company == "Contoso Ltd"
    assert resp.match_score == 88
    assert "SPFx" in resp.matched_skills
    assert "GraphQL" in resp.missing_skills
    assert resp.sharepoint_saved is True
    assert resp.sharepoint_error is None
    mock_sp_exporter.export_jobs.assert_called_once()


if __name__ == "__main__":
    test_direct_match_orchestrator_evaluation()
    print("ALL TESTS PASSED")

