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
        job_description="Existing snippet text from search results with over 150 characters of description preview.",
        has_full_description=False,
    )

    blank_html = "<html><body><div>No job description here</div></body></html>"
    parser.enrich_with_description(job, blank_html)

    # Should retain original snippet without falsely marking has_full_description=True
    assert job.job_description == "Existing snippet text from search results with over 150 characters of description preview."
    assert job.has_full_description is False


def test_json_ld_description_enrichment():
    parser = BeautifulSoupParser()
    job = JobPosting(
        id=uuid4(),
        indeed_job_id="test_jk_004",
        job_title="AI Engineer",
        company="TechCorp",
        location="Remote",
        job_description="Short snippet.",
        has_full_description=False,
    )

    json_ld_html = """
    <html>
    <head>
    <script type="application/ld+json">
    {
        "@context": "http://schema.org",
        "@type": "JobPosting",
        "title": "AI Engineer",
        "description": "<p>We are seeking a senior AI Engineer.</p><ul><li>Build LLM pipelines</li><li>Deploy with Kubernetes</li></ul>"
    }
    </script>
    </head>
    <body></body>
    </html>
    """
    parser.enrich_with_description(job, json_ld_html)

    assert job.has_full_description is True
    assert "We are seeking a senior AI Engineer." in job.job_description
    assert "• Build LLM pipelines" in job.job_description
    assert "• Deploy with Kubernetes" in job.job_description


def test_embedded_script_json_description_enrichment():
    parser = SelectolaxParser()
    job = JobPosting(
        id=uuid4(),
        indeed_job_id="test_jk_005",
        job_title="Full Stack Engineer",
        company="TechCorp",
        location="Remote",
        job_description="Short snippet.",
        has_full_description=False,
    )

    script_json_html = """
    <html>
    <body>
    <script id="_initialData" type="application/json">
    {
        "jobInfoWrapperModel": {
            "jobDescription": "<p>Develop state of the art web applications with React and Python.</p><h3>Requirements</h3><ul><li>3+ years TypeScript</li></ul>"
        }
    }
    </script>
    </body>
    </html>
    """
    parser.enrich_with_description(job, script_json_html)

    assert job.has_full_description is True
    assert "Develop state of the art web applications" in job.job_description
    assert "### Requirements" in job.job_description
    assert "• 3+ years TypeScript" in job.job_description
