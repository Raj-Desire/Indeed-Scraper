"""
Job Description Intelligent Parser & Parameter Extractor
========================================================
Extracts structured Opportunity Tracker parameters from job descriptions:
- Uses dynamic LLM extraction with specialized prompt for high-accuracy parsing
- Extracts: Title, Country (ISO code), Website, Salary Range, Estimated Value, Currency,
  Experience Criteria, Owner (Meet/Sizan/Chetan), Lead Source, Industry, Priority, Status,
  Contact Name, Email, Phone, Technology pills, Matched Skills, Missing Skills, Match Score, Notes.
- Provides a robust heuristic regex fallback if LLM is offline.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional
from app.config.constants import score_to_priority
from app.utils.logger import logger


COUNTRY_NAME_TO_CODE: dict[str, str] = {
    "united states": "US", "usa": "US", "us": "US", "america": "US",
    "united kingdom": "GB", "uk": "GB", "britain": "GB", "great britain": "GB", "england": "GB",
    "germany": "DE", "deutschland": "DE", "german": "DE", "berlin": "DE", "munich": "DE", "frankfurt": "DE",
    "south africa": "ZA", "za": "ZA", "rsa": "ZA", "johannesburg": "ZA", "cape town": "ZA", "durban": "ZA",
    "canada": "CA", "ca": "CA", "toronto": "CA", "vancouver": "CA", "montreal": "CA", "ontario": "CA",
    "australia": "AU", "au": "AU", "sydney": "AU", "melbourne": "AU", "brisbane": "AU",
    "france": "FR", "fr": "FR", "french": "FR", "paris": "FR",
    "netherlands": "NL", "nl": "NL", "holland": "NL", "amsterdam": "NL",
    "ireland": "IE", "ie": "IE", "dublin": "IE",
    "united arab emirates": "AE", "uae": "AE", "dubai": "AE", "abu dhabi": "AE",
    "singapore": "SG", "sg": "SG",
    "switzerland": "CH", "ch": "CH", "swiss": "CH", "zurich": "CH", "geneva": "CH",
    "spain": "ES", "es": "ES", "madrid": "ES", "barcelona": "ES",
    "italy": "IT", "it": "IT", "rome": "IT", "milan": "IT",
    "india": "IN", "in": "IN", "bangalore": "IN", "mumbai": "IN", "delhi": "IN", "hyderabad": "IN", "pune": "IN",
}

VALID_OWNERS = ["Meet", "Sizan", "Chetan"]
VALID_INDUSTRIES = ["IT", "Construction", "Legal", "Healthcare", "Logistics"]
VALID_CURRENCIES = ["USD", "EUR", "INR", "GBP", "CAD"]
VALID_PRIORITIES = ["High", "Medium", "Low"]
VALID_STATUSES = ["New", "Contacted", "Qualified", "Meeting Scheduled", "Bid Submitted", "Won", "Lost"]
VALID_LEAD_SOURCES = ["Indeed", "LinkedIn", "Upwork", "People Per Hour", "Dice", "Referral", "Website Inquiry", "Cold Outreach", "Other"]
VALID_TECHNOLOGIES = ["AI", "SharePoint", "Power Platform", ".NET", "Dynamics", "Power BI", "Admin"]


async def parse_job_description_with_ai(text: str, kb_chunks: Optional[list] = None) -> dict[str, Any]:
    """
    Dynamically extract Opportunity fields and evaluate fit using LLM.
    Falls back gracefully to parse_job_description heuristic if LLM is unavailable.
    """
    raw = (text or "").strip()
    if not raw:
        return parse_job_description("")

    # 1. Try LLM extraction if LLMMatcher is active
    try:
        from app.matching.llm_matcher import LLMMatcher
        matcher = LLMMatcher()
        if matcher._enabled and matcher._client:
            extracted_ai = await _extract_with_llm(matcher, raw, kb_chunks)
            if extracted_ai and extracted_ai.get("title"):
                return extracted_ai
    except Exception as exc:
        logger.warning("Dynamic LLM JD parsing failed, falling back to heuristic: {}", exc)

    # 2. Fallback heuristic parsing
    return parse_job_description(raw)


async def _extract_with_llm(matcher: Any, raw_text: str, kb_chunks: Optional[list] = None) -> Optional[dict[str, Any]]:
    """Execute LLM chat completion with dynamic prompt to extract structured opportunity fields."""
    kb_context = ""
    if kb_chunks:
        snippets = []
        for c in kb_chunks:
            txt = getattr(c, "chunk", str(c)).strip()[:300].replace("\n", " ")
            if txt:
                snippets.append(f"- {txt}")
        if snippets:
            kb_context = "COMPANY CAPABILITIES & CORE STACK:\n" + "\n".join(snippets) + "\n\n"
    else:
        kb_context = (
            "COMPANY CAPABILITIES & CORE STACK:\n"
            "- Microsoft 365, SharePoint Online, SPFx, Power Apps, Power Automate, Power BI, Power Platform\n"
            "- .NET Core, C#, Azure Cloud, AI & Copilot integrations, Modern Workplace Solutions\n\n"
        )

    system_prompt = (
        "You are an expert recruitment analyst and CRM opportunity specialist. "
        "Extract structured data from the user's job description text into strict JSON format. "
        "CRITICAL INSTRUCTION: Only extract information that is explicitly stated in the job description text. "
        "Do NOT invent, assume, or hallucinate salary, budget, years of experience, contact details, or links if they are not explicitly present in the text. "
        "If a field (like salary, estimated value, or experience) is not mentioned in the job description, you MUST return an empty string \"\" or null."
    )

    user_prompt = (
        f"{kb_context}"
        f"JOB DESCRIPTION TEXT TO ANALYZE:\n"
        f"{raw_text}\n\n"
        f"EXTRACTION & MATCHING RULES:\n"
        f"1. 'title': Job role title explicitly stated (e.g. 'Senior SharePoint Consultant').\n"
        f"1b. 'company': The hiring company / employer name explicitly stated in the text (e.g. 'Fujitsu', 'Microsoft'). This is the prospect/client company, NOT the recruiting agency unless no other company is named. If no company name is mentioned, return \"\".\n"
        f"2. 'country': 2-letter ISO country code matching location stated (e.g. 'person is from germany' -> 'DE', 'London, UK' -> 'GB', 'USA' -> 'US', 'India' -> 'IN'). Default 'US' if not mentioned.\n"
        f"3. 'salary_range': Raw text compensation/salary stated in the JD (e.g. '15000', '$120k-$150k', '€15,000/mo'). If NO salary or compensation is mentioned in the JD, return \"\". Do NOT guess.\n"
        f"4. 'estimated_value': Numeric budget/value extracted ONLY if a specific salary/budget number is stated in the JD (e.g. 15000). If NO salary/budget is mentioned, return null. Do NOT guess.\n"
        f"5. 'currency_code': Inferred currency from symbols/country (one of ['USD', 'EUR', 'INR', 'GBP', 'CAD']). Default 'USD'.\n"
        f"6. 'experience': Years of experience required explicitly stated in the JD (e.g. '5+ years'). If NO experience is mentioned in the JD, return \"\". Do NOT guess.\n"
        f"7. 'owner': Assigned owner strictly from ['Meet', 'Sizan', 'Chetan']. If 'sizan' is mentioned, pick 'Sizan'. If 'chetan', pick 'Chetan'. Default 'Meet'.\n"
        f"8. 'lead_source': One of ['Indeed', 'LinkedIn', 'Upwork', 'People Per Hour', 'Dice', 'Referral', 'Website Inquiry', 'Cold Outreach', 'Other']. Default 'Indeed'.\n"
        f"9. 'industry': One of ['IT', 'Construction', 'Legal', 'Healthcare', 'Logistics']. Default 'IT'.\n"
        f"10. 'priority': 'High', 'Medium', or 'Low' (set High if match score >= 70 or senior role).\n"
        f"11. 'status': 'New', 'Contacted', 'Qualified', etc. Default 'New'.\n"
        f"12. 'contact_name': Recruiter or contact person name if mentioned, else \"\".\n"
        f"13. 'email': Email address if found, else \"\".\n"
        f"14. 'phone': Phone number if found, else \"\".\n"
        f"15. 'website': Any URL or link found, else \"\".\n"
        f"16. 'technology': Array of matching technologies strictly from ['AI', 'SharePoint', 'Power Platform', '.NET', 'Dynamics', 'Power BI', 'Admin'].\n"
        f"17. 'matched_skills': Array of technical skills required that MATCH our company capabilities.\n"
        f"18. 'missing_skills': Array of technical skills/requirements in the JD that are MISMATCHED or absent from company stack.\n"
        f"19. 'match_score': Integer 0-100 indicating company capability fit.\n"
        f"20. 'match_reason': Concise explanation of the match verdict, strengths, and missing skills.\n"
        f"21. 'notes': Summary of unmapped parameters, location remarks, working conditions, or other relevant observations.\n\n"
        f"Output MUST be valid JSON only with these exact keys (use empty string \"\" or null for missing fields):\n"
        f'{{\n'
        f'  "title": "",\n'
        f'  "company": "",\n'
        f'  "country": "US",\n'
        f'  "salary_range": "",\n'
        f'  "estimated_value": null,\n'
        f'  "currency_code": "USD",\n'
        f'  "experience": "",\n'
        f'  "owner": "Meet",\n'
        f'  "lead_source": "Indeed",\n'
        f'  "industry": "IT",\n'
        f'  "priority": "Medium",\n'
        f'  "status": "New",\n'
        f'  "contact_name": "",\n'
        f'  "email": "",\n'
        f'  "phone": "",\n'
        f'  "website": "",\n'
        f'  "technology": [],\n'
        f'  "matched_skills": [],\n'
        f'  "missing_skills": [],\n'
        f'  "match_score": null,\n'
        f'  "match_reason": "",\n'
        f'  "notes": ""\n'
        f'}}'
    )

    kwargs = {
        "model": matcher._deployment,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 1200,
    }

    resp = await matcher._client.chat.completions.create(**kwargs)
    if not resp or not resp.choices:
        return None

    content = (resp.choices[0].message.content or "").strip()
    match = re.search(r"\{[\s\S]*\}", content)
    if not match:
        return None

    data = json.loads(match.group(0))

    # Compute heuristic baseline for fallback & merging
    heuristic = parse_job_description(raw_text)

    # Clean and validate outputs
    c_code = str(data.get("country", "")).strip().upper()
    if len(c_code) != 2:
        c_code = COUNTRY_NAME_TO_CODE.get(str(data.get("country", "")).lower().strip(), heuristic.get("country", "US"))

    owner_val = str(data.get("owner", "")).strip().capitalize()
    if owner_val not in VALID_OWNERS:
        raw_lower = raw_text.lower()
        if "sizan" in raw_lower:
            owner_val = "Sizan"
        elif "chetan" in raw_lower:
            owner_val = "Chetan"
        else:
            owner_val = heuristic.get("owner", "Meet")

    currency_val = str(data.get("currency_code", "")).strip().upper()
    if currency_val not in VALID_CURRENCIES:
        if c_code == "DE":
            currency_val = "EUR"
        elif c_code == "GB":
            currency_val = "GBP"
        elif c_code == "IN":
            currency_val = "INR"
        elif c_code == "CA":
            currency_val = "CAD"
        else:
            currency_val = "USD"

    techs = [t for t in data.get("technology", []) if t in VALID_TECHNOLOGIES]
    # Union with heuristic detected technologies from text so no explicit tech in JD is missed
    all_techs = set(techs) | set(heuristic.get("technology", []))
    final_technologies = [t for t in VALID_TECHNOLOGIES if t in all_techs]
    if not final_technologies:
        final_technologies = ["SharePoint"]
    score = data.get("match_score")
    try:
        score_int = int(score) if score is not None else None
    except (ValueError, TypeError):
        score_int = None

    est_val = data.get("estimated_value")
    try:
        est_float = float(est_val) if est_val is not None and str(est_val).strip() != "" else None
    except (ValueError, TypeError):
        est_float = None

    # Merge heuristic extra parameters with AI notes so no structured metadata is omitted
    extra_params = heuristic.get("extra_parameters", [])
    ai_notes = str(data.get("notes", "")).strip()
    if extra_params:
        unmapped_str = " | ".join(extra_params)
        if ai_notes and unmapped_str not in ai_notes:
            final_notes = f"{unmapped_str} | {ai_notes}"
        else:
            final_notes = unmapped_str if unmapped_str else ai_notes
    else:
        final_notes = ai_notes

    exp_val = str(data.get("experience", "")).strip() or heuristic.get("experience", "")
    if not exp_val and heuristic.get("experience"):
        exp_val = heuristic.get("experience")

    return {
        "title": str(data.get("title", "")).strip() or heuristic.get("title", ""),
        "job_title": str(data.get("title", "")).strip() or heuristic.get("job_title", ""),
        "company": str(data.get("company", "")).strip() or heuristic.get("company", ""),
        "country": c_code,
        "salary_range": str(data.get("salary_range", "")).strip() or heuristic.get("salary_range", ""),
        "estimated_value": est_float or heuristic.get("estimated_value"),
        "currency_code": currency_val,
        "experience": exp_val,
        "owner": owner_val,
        "lead_source": data.get("lead_source") if data.get("lead_source") in VALID_LEAD_SOURCES else "Indeed",
        "industry": data.get("industry") if data.get("industry") in VALID_INDUSTRIES else "IT",
        "priority": data.get("priority") if data.get("priority") in VALID_PRIORITIES else score_to_priority(score_int),
        "status": data.get("status") if data.get("status") in VALID_STATUSES else "New",
        "contact_name": str(data.get("contact_name", "")).strip() or heuristic.get("contact_name", ""),
        "email": str(data.get("email", "")).strip() or heuristic.get("email", ""),
        "phone": str(data.get("phone", "")).strip() or heuristic.get("phone", ""),
        "website": str(data.get("website", "")).strip() or heuristic.get("website", ""),
        "job_url": str(data.get("website", "")).strip() or heuristic.get("job_url", ""),
        "technology": final_technologies,
        "technologies": final_technologies,
        "matched_skills": [str(s).strip() for s in data.get("matched_skills", []) if s],
        "missing_skills": [str(s).strip() for s in data.get("missing_skills", []) if s],
        "match_score": score_int,
        "match_reason": str(data.get("match_reason", "")).strip(),
        "extra_parameters": extra_params,
        "notes": final_notes,
        "job_description": raw_text,
    }


def parse_job_description(text: str) -> dict[str, Any]:
    """
    Heuristic regex parser for fallback or fast offline extraction.
    """
    if not text or not text.strip():
        return {
            "title": "",
            "job_title": "",
            "company": "",
            "country": "US",
            "job_url": "",
            "website": "",
            "salary_range": "",
            "estimated_value": None,
            "currency_code": "USD",
            "experience": "",
            "owner": "Meet",
            "lead_source": "Indeed",
            "industry": "IT",
            "priority": "Medium",
            "status": "New",
            "email": "",
            "phone": "",
            "contact_name": "",
            "technology": ["SharePoint"],
            "technologies": ["SharePoint"],
            "matched_skills": [],
            "missing_skills": [],
            "match_score": None,
            "match_reason": "",
            "extra_parameters": [],
            "notes": "",
            "job_description": "",
        }

    raw = text.strip()
    raw_lower = raw.lower()
    lines = [line.strip() for line in raw.splitlines() if line.strip()]

    extracted: dict[str, Any] = {
        "title": "",
        "job_title": "",
        "company": "",
        "country": "US",
        "job_url": "",
        "website": "",
        "salary_range": "",
        "estimated_value": None,
        "currency_code": "USD",
        "experience": "",
        "owner": "Meet",
        "lead_source": "Indeed",
        "industry": "IT",
        "priority": "Medium",
        "status": "New",
        "email": "",
        "phone": "",
        "contact_name": "",
        "technology": [],
        "technologies": [],
        "matched_skills": [],
        "missing_skills": [],
        "match_score": None,
        "match_reason": "",
        "extra_parameters": [],
        "notes": "",
        "job_description": raw,
    }

    known_keys = {
        "job title": "job_title", "title": "job_title", "role": "job_title", "position": "job_title", "job role": "job_title",
        "preferred experience": "experience", "experience": "experience", "experience required": "experience", "experience criteria": "experience",
        "email": "email", "email address": "email", "contact email": "email", "mail": "email",
        "contact": "phone", "phone": "phone", "mobile": "phone", "contact number": "phone",
        "contact name": "contact_name", "recruiter": "contact_name", "hiring manager": "contact_name", "contact person": "contact_name",
        "salary": "salary_range", "salry": "salary_range", "salary range": "salary_range", "salary amount": "salary_range", "salry amount": "salary_range",
        "compensation": "salary_range", "pay": "salary_range", "budget": "salary_range",
        "job url": "job_url", "website": "job_url", "url": "job_url", "link": "job_url",
        "owner": "owner", "industry": "industry", "country": "country",
        "company": "company", "company name": "company", "employer": "company", "hiring company": "company", "client": "company",
    }

    extra_key_patterns = [
        "job location", "location", "job type", "employment type", "work type",
        "no. of positions", "positions", "date posted", "posted date",
        "shift", "notice period", "skills"
    ]

    found_extra_params: list[str] = []
    section_stops = ["job description", "job requirements", "responsibilities", "requirements", "qualifications", "about the role", "overview"]
    idx = 0

    while idx < len(lines):
        line_clean = lines[idx].strip()
        lower_line = line_clean.lower().rstrip(":")

        if lower_line in section_stops:
            idx += 1
            continue

        # Case A: "Key: Value" on the same line
        if ":" in line_clean and not line_clean.lower().startswith("http"):
            k, v = line_clean.split(":", 1)
            k_clean = k.strip()
            k_lower = k_clean.lower()
            val = v.strip()
            if k_lower in known_keys and val:
                extracted[known_keys[k_lower]] = val
                idx += 1
                continue
            elif any(k_lower == ep or k_lower.startswith(ep) for ep in extra_key_patterns) and val:
                found_extra_params.append(f"{k_clean}: {val}")
                idx += 1
                continue

        # Case B: "Key" on line idx and "Value" on line idx + 1
        if lower_line in known_keys and (idx + 1) < len(lines):
            next_val = lines[idx + 1].strip()
            if not any(next_val.lower().rstrip(":") == k for k in list(known_keys.keys()) + extra_key_patterns + section_stops):
                extracted[known_keys[lower_line]] = next_val
                idx += 2
                continue
        elif any(lower_line == ep or lower_line.startswith(ep) for ep in extra_key_patterns) and (idx + 1) < len(lines):
            next_val = lines[idx + 1].strip()
            if not any(next_val.lower().rstrip(":") == k for k in list(known_keys.keys()) + extra_key_patterns + section_stops):
                found_extra_params.append(f"{line_clean}: {next_val}")
                idx += 2
                continue

        idx += 1

    # Detect Owner
    if "sizan" in raw_lower:
        extracted["owner"] = "Sizan"
    elif "chetan" in raw_lower:
        extracted["owner"] = "Chetan"
    elif "meet" in raw_lower:
        extracted["owner"] = "Meet"

    # Detect Country
    detected_country = None
    for c_name, c_code in COUNTRY_NAME_TO_CODE.items():
        if re.search(r"\b" + re.escape(c_name) + r"\b", raw_lower):
            detected_country = c_code
            break
    if detected_country:
        extracted["country"] = detected_country

    # Set Currency based on country
    if extracted["country"] == "DE":
        extracted["currency_code"] = "EUR"
    elif extracted["country"] == "GB":
        extracted["currency_code"] = "GBP"
    elif extracted["country"] == "IN":
        extracted["currency_code"] = "INR"
    elif extracted["country"] == "CA":
        extracted["currency_code"] = "CAD"

    # Regex Salary & Estimated Value
    if not extracted["salary_range"]:
        sal_m = re.search(r"(?:sal(?:a)?ry|compensation|budget|rate)(?:\s+amount)?[:\s]+([$€£₹]?\s*\d[\d,.]*(?:\s*k|\s*thousand|\s*(?:-|to)\s*[$€£₹]?\s*\d[\d,.]*)?(?:\s*(?:/|per)\s*(?:yr|year|mo|month|hr|hour))?)", raw_lower)
        if sal_m:
            extracted["salary_range"] = sal_m.group(1).strip()

    if extracted["salary_range"]:
        num_m = re.search(r"(\d[\d,]*)", extracted["salary_range"])
        if num_m:
            try:
                extracted["estimated_value"] = float(num_m.group(1).replace(",", ""))
            except Exception:
                pass

    # Regex Email & Phone & URL
    if not extracted["email"]:
        em = re.findall(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", raw)
        if em:
            extracted["email"] = em[0]

    if not extracted["phone"]:
        ph = re.findall(r"(?:Phone|Contact|Mobile|Tel|Cell)?[:\s\n]*((?:\+?\d{1,4}[-.\s]?)?\(?\d{2,5}\)?[-.\s]?\d{3,5}[-.\s]?\d{3,5})", raw)
        valid_phones = [p.strip() for p in ph if 7 <= len(re.sub(r"\D", "", p)) <= 15]
        if valid_phones:
            extracted["phone"] = valid_phones[0]

    if not extracted["job_url"]:
        um = re.findall(r"https?://[^\s<>\"'()]+", raw)
        if um:
            extracted["job_url"] = um[0]
            extracted["website"] = um[0]

    # Regex Experience
    if not extracted["experience"]:
        exp_match = re.search(r"(\b\d+\+?\s*(?:to|-)\s*\d+\+?\s*(?:years?|yrs?)(?:\s+of)?(?:\s+experience)?|\b\d+\+\s*(?:years?|yrs?)(?:\s+of)?(?:\s+experience)?)", raw, re.IGNORECASE)
        if exp_match:
            extracted["experience"] = exp_match.group(1).strip()

    # Job title fallback
    if not extracted["job_title"] and lines:
        first_line = lines[0]
        if len(first_line) <= 120 and not any(first_line.lower().startswith(p) for p in ["http", "dear", "we are", "salry", "salary", "person", "owner"]):
            extracted["job_title"] = first_line

    extracted["title"] = extracted["job_title"]

    # Company name fallback: common corporate JD opener "At <Company>, our purpose is..."
    if not extracted["company"]:
        at_m = re.search(r"\bAt\s+([A-Z][A-Za-z0-9&.'\- ]{1,60}?),", raw)
        if at_m:
            extracted["company"] = at_m.group(1).strip()

    # Technology tagging
    tech_tags: list[str] = []
    if any(k in raw_lower for k in ["sharepoint", "spfx", "sp online", "microsoft 365", "m365"]):
        tech_tags.append("SharePoint")
    if any(k in raw_lower for k in ["power platform", "power apps", "powerapps", "power automate", "powerportal", "power portals", "power pages", "dataverse"]):
        tech_tags.append("Power Platform")
    if any(k in raw_lower for k in [".net", "c#", "asp.net", "dotnet"]):
        tech_tags.append(".NET")
    if any(k in raw_lower for k in ["ai", "openai", "azure openai", "llm", "machine learning"]):
        tech_tags.append("AI")
    if any(k in raw_lower for k in ["dynamics", "d365", "crm"]):
        tech_tags.append("Dynamics")
    if any(k in raw_lower for k in ["power bi", "powerbi", "dax"]):
        tech_tags.append("Power BI")
    if any(k in raw_lower for k in ["admin", "system administrator", "m365 admin"]):
        tech_tags.append("Admin")
    if not tech_tags:
        tech_tags.append("SharePoint")

    extracted["technology"] = tech_tags
    extracted["technologies"] = tech_tags

    extracted["extra_parameters"] = found_extra_params
    if found_extra_params:
        extracted["notes"] = " | ".join(found_extra_params)

    return extracted
