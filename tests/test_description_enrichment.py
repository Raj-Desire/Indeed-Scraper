"""
Tests for Full Job Description Scraping and Enrichment
Verifies that:
1. Initial search card parse provides a snippet with has_full_description=False.
2. enrich_with_description successfully extracts full multi-paragraph and bulleted descriptions.
3. has_full_description is updated to True.
4. Both Selectolax and BeautifulSoup parsers handle formatting and fallback extraction.
"""

from uuid import uuid4
from app.models.job import JobPosting
from app.parser.selectolax_parser import SelectolaxParser
from app.parser.job_parser import BeautifulSoupParser


SAMPLE_DETAIL_HTML = """
<html>
<body>
<div id="jobDescriptionText">
    <h2>About the Role</h2>
    <p>We are seeking an Applied AI Engineer to design and deploy state-of-the-art LLM solutions.</p>
    <h3>Key Responsibilities</h3>
    <ul>
        <li>Build agentic workflows using Python and LangChain.</li>
        <li>Deploy high-throughput models on Azure AI and Kubernetes.</li>
        <li>Collaborate with cross-functional product teams to deliver AI features.</li>
    </ul>
    <h3>Qualifications</h3>
    <ul>
        <li>5+ years of software development experience in Python.</li>
        <li>Strong understanding of RAG, vector databases, and prompt engineering.</li>
    </ul>
</div>
</body>
</html>
"""


def test_selectolax_full_description_enrichment():
    parser = SelectolaxParser()
    job = JobPosting(
        id=uuid4(),
        indeed_job_id="test_jk_001",
        job_title="Applied AI Engineer",
        company="TechCorp",
        location="Remote",
        job_description="Short 100 character snippet from search card.",
        has_full_description=False,
    )

    assert not job.has_full_description
    assert len(job.job_description) < 100

    parser.enrich_with_description(job, SAMPLE_DETAIL_HTML)

    assert job.has_full_description is True
    assert len(job.job_description) > 300
    assert "Applied AI Engineer" in job.job_description
    assert "agentic workflows" in job.job_description
    assert "Qualifications" in job.job_description


def test_beautifulsoup_full_description_enrichment():
    parser = BeautifulSoupParser()
    job = JobPosting(
        id=uuid4(),
        indeed_job_id="test_jk_002",
        job_title="Applied AI Engineer",
        company="TechCorp",
        location="Remote",
        job_description="Short 100 character snippet from search card.",
        has_full_description=False,
    )

    assert not job.has_full_description

    parser.enrich_with_description(job, SAMPLE_DETAIL_HTML)

    assert job.has_full_description is True
    assert len(job.job_description) > 300
    assert "agentic workflows" in job.job_description
    assert "Qualifications" in job.job_description


def test_enrichment_does_not_override_with_blank():
    parser = SelectolaxParser()
    job = JobPosting(
        id=uuid4(),
        indeed_job_id="test_jk_003",
        job_title="AI Engineer",
        company="TechCorp",
        location="Remote",
        job_description="Existing snippet text.",
        has_full_description=False,
    )

    blank_html = "<html><body><div>No job description here</div></body></html>"
    parser.enrich_with_description(job, blank_html)

    # Should retain original snippet if detail container not found
    assert job.job_description == "Existing snippet text."
    assert job.has_full_description is False
