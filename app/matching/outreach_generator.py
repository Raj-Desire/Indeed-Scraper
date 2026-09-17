"""
Outreach Draft Generator
========================
Generates a structured application email (matching the BDE team's reference
format: greeting, opening line, bulleted skills, alignment paragraph, bulleted
engagement models, rate/attachment line, closing CTA) and LinkedIn outreach
message variants for a given job.

The email's STRUCTURE (bullets, section order, company facts like team size and
engagement models) is built deterministically from app.config.constants - never
left to the LLM to get consistently right. The LLM is only asked for two short,
job-specific connective sentences (why we're reaching out, why our skills fit),
plus the LinkedIn variants. This guarantees every generated email is always
properly structured, never a single unstructured paragraph blob.

Never raises - any failure yields empty drafts so callers can render a
"generation failed" state instead of crashing.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.config.constants import (
    OUTREACH_ENGAGEMENT_MODELS,
    OUTREACH_LINKEDIN_MAX_CHARS,
    OUTREACH_LINKEDIN_VARIANT_COUNT,
    OUTREACH_RATE_PLACEHOLDER,
    OUTREACH_SENDER_BLURB,
    OUTREACH_SENDER_COMPANY,
    OUTREACH_TEAM_SIZE,
    OUTREACH_TONE_GUIDELINES,
)
from app.matching.llm_matcher import LLMMatcher, get_llm_matcher
from app.utils.logger import logger


def _build_prompt(
    job_title: str,
    company: str,
    job_description: str,
    matched_skills: list[str],
    missing_skills: list[str],
    kb_context: str,
) -> tuple[str, str]:
    system_prompt = (
        f"You are a business-development copywriter for {OUTREACH_SENDER_COMPANY}, an IT "
        f"services company. You write ONLY short connective sentences that get inserted into a "
        f"pre-built email template - never a full email, never bullet lists, never a subject line "
        f"with a signature block. "
        f"TONE & STYLE RULES: {OUTREACH_TONE_GUIDELINES} "
        f"Respond strictly with a JSON object - no markdown, no commentary outside the JSON."
    )

    matched_str = ", ".join(matched_skills[:8]) or "general technical alignment"
    missing_str = ", ".join(missing_skills[:5]) or "none significant"
    cleaned_jd = (job_description or "").strip()[:2000]

    user_prompt = (
        f"JOB TITLE: {job_title or 'Not specified'}\n"
        f"COMPANY: {company or 'Not specified'}\n"
        f"JOB DESCRIPTION:\n{cleaned_jd}\n\n"
        f"OUR MATCHING CAPABILITIES: {matched_str}\n"
        f"OUR GAPS (do not mention these): {missing_str}\n"
        f"COMPANY KNOWLEDGE BASE CONTEXT:\n{kb_context}\n\n"
        f"TASK - produce exactly these 4 short fields, each 1-2 sentences, no bullet points, "
        f"no markdown, no signature:\n"
        f"1. 'email_subject': A short, specific subject line for an application/outreach email "
        f"(e.g. 'Supporting your {job_title or 'open'} requirement - {OUTREACH_SENDER_COMPANY}').\n"
        f"2. 'opening_line': One sentence saying we came across their requirement for this exact "
        f"role/company and want to explore how {OUTREACH_SENDER_COMPANY} could support their team. "
        f"Do NOT mention team size, engagement models, or rate here - those are added separately.\n"
        f"3. 'alignment_paragraph': 1-2 sentences explicitly connecting our matching capabilities "
        f"above to this specific job's stated requirements (e.g. 'This experience aligns well with "
        f"your requirements around X, Y, Z.'). Reference the job's actual technologies/requirements, "
        f"not generic filler.\n"
        f"4. 'linkedin_variants': An array of exactly {OUTREACH_LINKEDIN_VARIANT_COUNT} short, "
        f"distinct LinkedIn connection/outreach messages, each under {OUTREACH_LINKEDIN_MAX_CHARS} "
        f"characters, each with a different angle (e.g. direct interest, capability-led, "
        f"question-led, referral-style). No hashtags, no emojis, no signature.\n\n"
        f"Output MUST be valid JSON only:\n"
        f'{{\n'
        f'  "email_subject": "",\n'
        f'  "opening_line": "",\n'
        f'  "alignment_paragraph": "",\n'
        f'  "linkedin_variants": ["", "", "", ""]\n'
        f'}}'
    )
    return system_prompt, user_prompt


def _extract_json(text: str) -> dict[str, Any]:
    if not text:
        return {}
    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    json_str = code_block.group(1).strip() if code_block else text
    if not code_block:
        brace_match = re.search(r"\{[\s\S]*\}", text)
        if brace_match:
            json_str = brace_match.group(0).strip()
    try:
        return json.loads(json_str)
    except Exception:
        try:
            cleaned = re.sub(r",\s*([\]}])", r"\1", json_str)
            return json.loads(cleaned)
        except Exception:
            return {}


def build_email_body(
    contact_name: str,
    opening_line: str,
    alignment_paragraph: str,
    matched_skills: list[str],
) -> str:
    """
    Assemble the final email body from the fixed structural template + the LLM's
    short connective sentences + our own matched_skills list (used directly, not
    re-generated by the LLM, so the skills bullets are always accurate).
    """
    greeting = f"Hi {contact_name}," if contact_name else "Hi there,"

    # Bullets use '•' (not '* ' or '-') so this template is compatible with
    # app.sharepoint.graph_exporter._structured_text_to_html, which converts
    # '•'-prefixed lines into a real HTML <ul><li> list for the Rich Text column.
    skill_bullets = "\n".join(f"• {s}" for s in matched_skills[:8]) or "• Full-stack development aligned with your requirements"
    engagement_bullets = "\n".join(f"• {m}" for m in OUTREACH_ENGAGEMENT_MODELS)

    parts = [
        greeting,
        "",
        "I hope you're doing well.",
        "",
        opening_line or "I came across your requirement and wanted to reach out to explore how we could support your engineering team.",
        "",
        f"We have a team of {OUTREACH_TEAM_SIZE} skilled developers, including experienced professionals with expertise in:",
        "",
        skill_bullets,
        "",
    ]
    if alignment_paragraph:
        parts.extend([alignment_paragraph, ""])

    parts.extend([
        "We can propose an in-house resource based on your specific project requirements and offer flexible engagement models, including:",
        "",
        engagement_bullets,
        "",
        f"Our hourly rate ranges between {OUTREACH_RATE_PLACEHOLDER} based on project duration and complexity and level of expertise required. For your review I have attached the resource profile.",
        "",
        "Please let me know if you would be available for a brief discussion to understand your requirements and explore how we can support your team.",
    ])
    return "\n".join(parts)


async def generate_outreach(
    job_title: str,
    company: str,
    job_description: str,
    matched_skills: Optional[list[str]] = None,
    missing_skills: Optional[list[str]] = None,
    kb_context: str = "",
    contact_name: str = "",
    matcher: Optional[LLMMatcher] = None,
) -> dict[str, Any]:
    """
    Generate a structured outreach email (subject + body) and LinkedIn message
    variants for a job. Returns {"email_subject": str, "email_body": str,
    "linkedin_variants": list[str]}.
    Never raises - returns empty strings/list on any failure (LLM not configured, API error, etc.).

    Args:
        matcher: Optional pre-built LLMMatcher (reuses its client/deployment), for tests
            or to share a single matcher instance across calls. Defaults to the shared
            cached matcher (get_llm_matcher()), so this doesn't pay a fresh client
            cold-start on every call.
    """
    empty_result = {
        "email_subject": "", "email_body": "", "linkedin_variants": [],
        "opening_line": "", "alignment_paragraph": "",
    }

    matcher = matcher or get_llm_matcher()
    if not matcher._enabled or not matcher._client:
        logger.warning("Outreach generation skipped: LLM not configured")
        return empty_result

    matched_skills = matched_skills or []
    system_prompt, user_prompt = _build_prompt(
        job_title, company, job_description, matched_skills, missing_skills or [], kb_context
    )

    try:
        kwargs = {
            "model": matcher._deployment,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.4,
            "max_tokens": 900,
        }
        if matcher._provider == "azure" and "phi" not in str(matcher._deployment).lower():
            kwargs["response_format"] = {"type": "json_object"}

        response = await matcher._client.chat.completions.create(**kwargs)
        if not response or not response.choices:
            return empty_result

        raw_content = (getattr(response.choices[0].message, "content", "") or "").strip()
        payload = _extract_json(raw_content)

        subject = str(payload.get("email_subject", "")).strip()
        opening_line = str(payload.get("opening_line", "")).strip()
        alignment_paragraph = str(payload.get("alignment_paragraph", "")).strip()
        variants_raw = payload.get("linkedin_variants", [])
        variants = [str(v).strip() for v in variants_raw if str(v).strip()][:OUTREACH_LINKEDIN_VARIANT_COUNT]

        if not subject and not opening_line and not alignment_paragraph and not variants:
            return empty_result

        body = build_email_body(contact_name, opening_line, alignment_paragraph, matched_skills)

        return {
            "email_subject": subject or f"Supporting your {job_title or 'open role'} requirement - {OUTREACH_SENDER_COMPANY}",
            "email_body": body,
            "linkedin_variants": variants,
            # Raw connective sentences, exposed so a caller that computes matched_skills
            # concurrently (e.g. running this alongside JD extraction+scoring via
            # asyncio.gather) can rebuild email_body with the accurate final skill
            # list instead of whatever (possibly empty) matched_skills this call had.
            "opening_line": opening_line,
            "alignment_paragraph": alignment_paragraph,
        }
    except Exception as exc:
        logger.error("Outreach generation failed: {}", exc)
        return empty_result
