"""
Outreach Draft Generator
========================
Generates a structured application email (matching the BDE team's reference
format: greeting, personalized opening line, bulleted skills, alignment
paragraph, a "What we can offer" section with bulleted engagement models and
rate per model, attachment line, low-friction call-to-action, and a warm
closing) and LinkedIn outreach message variants for a given job.

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
        f"2. 'opening_line': ONE natural sentence in this style: 'I saw your job post for a "
        f"{job_title or '[role]'} to help with <a short, specific paraphrase of what this role is "
        f"actually trying to accomplish, based on the job description>, and thought our team could "
        f"be a great fit.' Do not just restate the job title - name the underlying goal/project so it "
        f"reads like you actually read the posting. Do NOT mention team size, engagement models, or "
        f"rate here - those are added separately.\n"
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
        opening_line or "I saw your job post and thought our team could be a great fit.",
        "",
        f"{OUTREACH_SENDER_COMPANY} is a team of {OUTREACH_TEAM_SIZE} highly skilled, certified "
        f"developers and engineers specializing in Microsoft and AI technologies. As per your job "
        f"post, our team has expertise in:",
        "",
        skill_bullets,
        "",
    ]
    if alignment_paragraph:
        parts.extend([alignment_paragraph, ""])

    parts.extend([
        "What we can offer:",
        "We can provide one skilled engineer or a small team, depending on what you need. "
        "You can choose how you'd like to work with us:",
        "",
        engagement_bullets,
        "",
        "The exact rate depends on the engineer's experience level and how complex the work is - "
        "happy to explain more on a call.",
        "I've attached a profile with our relevant experience for you to review.",
        "",
        "Would you have 15 minutes this week for a quick call? We'd love to understand your needs "
        "better and see how we can help.",
        "",
        "Thanks, looking forward to hearing from you.",
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
