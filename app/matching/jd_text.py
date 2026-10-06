"""
Job-description preprocessing for matching.

Job posts open with company/benefits boilerplate and put the real requirements
near the bottom. Naively using the first N characters (for retrieval or for the
LLM) therefore scores the employer's pitch instead of the role's skills.
"""

from __future__ import annotations

import hashlib
import re

THIN_JD_CHARS = 300

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_HEADING_RE = re.compile(
    r"^\s*(?:#+\s*)?(?:"
    r"requirements?|qualifications?|required skills?|key skills?|skills?(?: required)?|"
    r"must[- ]haves?|what you(?:'|’)?ll need|what we(?:'|’)?re looking for|who you are|"
    r"you have|you bring|about you|responsibilities|key responsibilities|"
    r"what you(?:'|’)?ll do|the role|role overview|duties|technical skills?|"
    r"nice[- ]to[- ]haves?|preferred(?: qualifications| skills)?"
    r")\s*:?\s*$",
    re.IGNORECASE,
)
_STOP_HEADING_RE = re.compile(
    r"^\s*(?:#+\s*)?(?:about (?:us|the company)|who we are|benefits?|perks|compensation|what we offer|"
    r"why join us|equal opportunity.*|company overview|our (?:culture|values|mission))\s*:?\s*$",
    re.IGNORECASE,
)
_BOILERPLATE_RE = re.compile(
    r"equal opportunity|eeo\b|we are an? .*employer|reasonable accommodation|"
    r"benefits include|health insurance|401\(k\)|paid time off|dental|vision insurance",
    re.IGNORECASE,
)


def clean_jd(text: str) -> str:
    """Strip HTML tags and collapse whitespace while keeping line structure."""
    if not text:
        return ""
    text = _TAG_RE.sub("\n", text)
    lines = [_WS_RE.sub(" ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def prepare_jd(text: str, limit: int = 4000) -> str:
    """Return up to `limit` chars of the JD, prioritising the requirement sections.

    Layout: a short head (role context) + requirement/responsibility sections.
    With no recognisable headings, falls back to head + tail (where requirements
    usually are) instead of head only. Boilerplate lines (EEO, benefits) are dropped.
    """
    cleaned = clean_jd(text)
    if len(cleaned) <= limit:
        return cleaned

    lines = cleaned.splitlines()
    head = "\n".join(lines[:6])[:600]

    sections: list[str] = []
    capturing = False
    for ln in lines:
        if _HEADING_RE.match(ln):
            capturing = True
            sections.append(ln)
            continue
        if capturing:
            if _STOP_HEADING_RE.match(ln):
                capturing = False
                continue
            if not _BOILERPLATE_RE.search(ln):
                sections.append(ln)

    if sections:
        body = "\n".join(sections)
        return (head + "\n\n" + body)[:limit]

    tail_budget = limit - len(head) - 2
    body_lines = [ln for ln in lines[6:] if not _BOILERPLATE_RE.search(ln)]
    body = "\n".join(body_lines)
    if len(body) > tail_budget:
        body = body[-tail_budget:]
    return head + "\n\n" + body


def is_thin(text: str) -> bool:
    return len(clean_jd(text)) < THIN_JD_CHARS


def jd_hash(text: str, extra: str = "") -> str:
    norm = re.sub(r"\s+", " ", (text or "").strip().lower())
    return hashlib.sha256((norm + "|" + extra).encode("utf-8")).hexdigest()


# --- Non-LLM requirement extraction (fallback when the LLM endpoint times out) -----------------
_TECH_VOCAB = [
    "SharePoint Online", "SharePoint", "SPFx", "Power Apps", "Power Automate", "Power BI", "Power Platform",
    "Power Pages", "Dataverse", "Microsoft 365", "Office 365", "Microsoft Teams", "Microsoft Graph", "Azure Functions",
    "Azure DevOps", "Azure OpenAI", "Azure AI Foundry", "Azure AI Search", "Azure Databricks", "Azure Data Factory",
    "Azure", "Dynamics 365", "Copilot", "Copilot Studio", "OpenAI", "ChatGPT", "RAG", "LLM", "Generative AI",
    "Machine Learning", "Deep Learning", "Computer Vision", "NLP", "PyTorch", "TensorFlow", "Hugging Face",
    "scikit-learn", "Pandas", "NumPy", "MLOps", "LangChain", "Vector Database", "Fine-tuning",
    "Python", "Java", "JavaScript", "TypeScript", "C#", ".NET", ".NET Core", "ASP.NET", "C++", "Go", "Rust", "Ruby",
    "PHP", "Swift", "SwiftUI", "Kotlin", "Scala", "R", "SQL", "NoSQL", "PostgreSQL", "MySQL", "MongoDB", "Cosmos DB",
    "SQL Server", "Oracle", "Snowflake", "Databricks", "Spark", "Hadoop", "Kafka", "Airflow", "dbt",
    "React", "Angular", "Vue", "Node.js", "Next.js", "Flutter", "React Native", "HTML", "CSS", "REST API", "GraphQL",
    "Docker", "Kubernetes", "Terraform", "Jenkins", "CI/CD", "GitHub Actions", "Git", "Linux", "Bash", "PowerShell",
    "AWS", "GCP", "Google Cloud", "Salesforce", "ServiceNow", "SAP", "Workday", "Tableau", "Looker", "Excel",
    "Active Directory", "Entra ID", "Intune", "Okta", "SSO", "OAuth", "Windows Server", "VMware", "Jira", "Confluence",
    "Elasticsearch", "Kibana", "Splunk", "Selenium", "Playwright", "Cypress", "Figma", "Power Query", "DAX",
]
_VOCAB_RES = [
    (t, re.compile(r"(?<![\w.#+])" + re.escape(t) + r"(?![\w#+])", 0 if t in ("Go", "R", "RAG", "SQL", "AWS", "GCP", "SAP", "NLP", "LLM", "SSO", "CSS", "HTML", "DAX", "PHP") else re.IGNORECASE))
    for t in sorted(_TECH_VOCAB, key=len, reverse=True)
]


def heuristic_requirements(text: str, limit: int = 14) -> list[dict]:
    """Known technology names found in the JD, longest-match first (so 'Azure OpenAI' hides 'Azure')."""
    cleaned = clean_jd(text)
    found: list[dict] = []
    masked = cleaned
    for term, rx in _VOCAB_RES:
        if rx.search(masked):
            found.append({"skill": term, "importance": "must"})
            masked = rx.sub(" ", masked)
        if len(found) >= limit:
            break
    return found
