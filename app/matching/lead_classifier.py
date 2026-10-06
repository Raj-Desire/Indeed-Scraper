"""
Lead Classifier - is this posting a B2B opportunity for an IT services company?

We sell software development, project implementation, integration and dedicated developers /
staff augmentation. An ordinary job vacancy (one in-house hire) is NOT a lead; a company or
staffing firm looking for an external team, implementation partner, contract resource or project
delivery IS.

Pipeline (cheap -> expensive):
  1. Title rules      - obviously non-technical titles (sales, HR, admin...) are rejected without an LLM call.
  2. LLM judgement    - full title + description -> engagement type, category, fit score, confidence, reason.
  3. Deterministic    - B2B evidence (contract/C2C/our client/outsourcing...) and vacancy evidence (permanent,
     adjustment         in-house, benefits...) adjust and CAP the score so one fluent LLM answer cannot promote
                        an internal hire. Low confidence -> "Needs Review".

Never raises. With the LLM unavailable it falls back to rules only and marks leads "Needs Review"
rather than guessing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.config.settings import get_settings
from app.matching.jd_text import jd_hash, prepare_jd
from app.utils.logger import logger

HIGH, RELEVANT, REVIEW, REJECTED = "High Priority", "Relevant", "Needs Review", "Rejected"
CLASS_RANK = {HIGH: 0, RELEVANT: 1, REVIEW: 2, "": 3, REJECTED: 4}

POSITIVE_ENGAGEMENTS = {"external_project", "dedicated_resource", "staff_augmentation", "implementation_partner"}
PROMPT_VERSION = "lead-v1"
THIN_LEAD_DESC_CHARS = 200

_DEFAULT_RULES = {
    "title_reject": ["sales", "marketing", "recruiter", "human resources", "account manager", "administrative"],
    "title_tech": ["developer", "engineer", "architect", "programmer", "devops", "software", "consultant"],
    "positive_signals": ["outsourc", "staff augmentation", "\\bc2c\\b", "\\bcontract\\b", "our client"],
    "negative_signals": ["in-house", "full[- ]time permanent", "benefits (?:include|package)"],
    "title_reject_always": ["vice president", "vp", "director", "head of", "chief", "manager"],
    "gig_signals": ["per (?:completed )?task", "data annotation"],
}


def _load_rules() -> dict:
    rules = {k: list(v) for k, v in _DEFAULT_RULES.items()}
    path = Path(__file__).resolve().parent.parent.parent / "config" / "lead_rules.json"
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            for k in rules:
                if isinstance(data.get(k), list) and data[k]:
                    rules[k] = [str(x) for x in data[k]]
    except Exception as exc:  # bad config must never break scraping
        logger.warning("lead_rules.json unreadable, using defaults: {}", exc)
    return rules


@dataclass
class LeadVerdict:
    lead_class: str = REVIEW
    lead_score: int = 0
    category: str = ""
    engagement: str = "unclear"
    reason: str = ""
    positive_signals: list[str] = field(default_factory=list)
    negative_signals: list[str] = field(default_factory=list)
    used_llm: bool = False
    short_reason: str = ""  # one short plain-language line, set when the lead is Rejected
    tech_fit: int = 0  # how well the role's tech stack matches our service lines (0-100), independent of hire type


_SYSTEM = "You qualify job postings as B2B sales leads for an IT services company. Respond with strict JSON only."
_USER = (
    "OUR BUSINESS: IT services - custom software development, web/mobile apps, AI/ML and GenAI projects (LLM apps, RAG, "
    "chatbots, computer vision), SharePoint/Microsoft 365, Power Platform, .NET/Azure, ERP/CRM implementation, system "
    "integration, project outsourcing, dedicated developers, contract resources and staff augmentation. We work OFFSHORE "
    "(from India), so work that must be done by someone located in one specific country is not open to us.\n\n"
    "GOAL: find postings where a company (or a staffing/consulting firm on behalf of a client) needs EXTERNAL technical "
    "delivery capacity that an offshore IT-services team can supply. Ordinary employee vacancies are NOT leads.\n\n"
    "Classify 'engagement':\n"
    "- external_project: a specific project/product build, migration or implementation that could be outsourced\n"
    "- dedicated_resource: a software/IT contractor, C2C/1099 or contract-to-hire developer, or dedicated team member, "
    "supplied to a business client\n"
    "- staff_augmentation: staffing/consulting firm or MSP supplying technical resources to its client(s)\n"
    "- implementation_partner: wants a partner/vendor to implement or integrate a platform (ERP, CRM, M365, etc.)\n"
    "- internal_hire: one permanent/full-time employee for the employer's own internal team\n"
    "- gig_work: an individual freelancer/expert paid per task or per hour for crowd-style work such as AI training data, "
    "data annotation, model evaluation/grading, content review or writing tasks - NOT a software delivery engagement, "
    "even when it says 'contract' or 'contractor'\n"
    "- non_technical: sales, marketing, HR, recruiting, account management, admin, support, operations, AND any "
    "leadership or management role (VP, Director, Head of, Manager, practice/P&L owner, leader of people) - even "
    "when the employer is a technology or AI company\n"
    "- unclear: cannot tell\n\n"
    "IMPORTANT RULES:\n"
    "- The word 'contract' alone does not make a lead. It must be IT/software delivery for a business client.\n"
    "- A role that builds the employer's own product or internal platform is internal_hire.\n"
    "- Set 'location_locked' true when the work/contract is restricted to people located or based in one specific country "
    "(e.g. 'US-based contractor', 'must be located in the UK', 'based in the United States'); otherwise false.\n"
    "- The employer being an AI/IT company does not make a leadership or sales role a lead.\n\n"
    "'fit_score' 0-100 = how valuable this is as a lead for us: 85+ clear outsourcing/contract/implementation opportunity "
    "in our tech areas; 60-84 relevant technical opportunity; 35-59 ambiguous; below 35 not a lead.\n"
    "'tech_fit' 0-100 = how closely the TECHNICAL work (stack and tasks) matches our service lines above, regardless of "
    "whether it is a vacancy or a contract (e.g. an LLM/RAG/agent engineer using Python and AWS = 85; a data scientist "
    "building risk models = 40; mechanical engineering = 5).\n"
    "'confidence' 0-1 = how sure you are. Use low confidence when the text is thin or contradictory.\n"
    "'category' = short label such as 'Software Development', 'AI/ML', 'ERP/CRM Implementation', "
    "'System Integration', 'Staff Augmentation', 'Cloud/DevOps', 'Data Engineering', 'AI Training/Gig Work', "
    "'Sales/Marketing', 'HR/Recruitment', 'Leadership/Management', 'Administrative', 'Other'.\n"
    "'reason' = ONE sentence citing the decisive evidence from the posting.\n\n"
    "POSTING\nTitle: {title}\nCompany: {company}\nLocation: {location}\nDescription:\n{jd}\n\n"
    'JSON: {{"engagement": "", "category": "", "fit_score": 0, "tech_fit": 0, "location_locked": false, '
    '"confidence": 0.0, "reason": ""}}'
)


_ENGAGEMENT_REJECT_TEXT = {
    "internal_hire": "Single in-house hire - not outsourcing, contract or project work",
    "non_technical": "Not an IT delivery role",
    "unclear": "Unclear whether this is outsourcing or an internal hire",
    "gig_work": "Individual freelance / AI-training task work - not a software delivery engagement",
    "location_locked": "Contract limited to people based in one country - not open to an offshore team",
}


def _short_title(title: str, n: int = 48) -> str:
    title = (title or "").strip()
    return title if len(title) <= n else title[:n].rsplit(" ", 1)[0] + "..."


def short_reject_reason(engagement: str, category: str, title: str, score: int, by_title: bool = False) -> str:
    """One short, plain-language reason shown in the dashboard's Reject Reason column."""
    if by_title:
        return f"Non-technical role ({_short_title(title)})"
    text = _ENGAGEMENT_REJECT_TEXT.get(engagement)
    if engagement == "non_technical" and category and category.lower() not in ("other", "non-technical role"):
        text = f"Not an IT delivery role ({category})"
    return text or f"Low fit as an IT-services opportunity (score {score})"


class LeadClassifier:
    def __init__(self, matcher=None) -> None:
        self._matcher = matcher
        self._rules = _load_rules()
        self._reject_re = self._compile(self._rules["title_reject"], word=True)
        self._tech_re = self._compile(self._rules["title_tech"], word=True)
        self._always_re = self._compile(self._rules["title_reject_always"], word=True)
        self._gig_res = [re.compile(p, re.IGNORECASE) for p in self._rules["gig_signals"]]
        self._pos_res = [re.compile(p, re.IGNORECASE) for p in self._rules["positive_signals"]]
        self._neg_res = [re.compile(p, re.IGNORECASE) for p in self._rules["negative_signals"]]
        self._cache: dict[str, LeadVerdict] = {}

    @staticmethod
    def _compile(terms: list[str], word: bool) -> re.Pattern:
        body = "|".join(re.escape(t.strip()) for t in terms if t.strip())
        return re.compile(rf"(?<![\w]){'(?:' + body + ')'}(?![\w])" if word else body, re.IGNORECASE)

    # ----------------------------------------------------------------- public API
    async def classify(self, title: str, company: str, description: str, location: str = "") -> LeadVerdict:
        key = jd_hash(f"{title}|{company}|{(description or '')[:3000]}", PROMPT_VERSION)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        try:
            verdict = await self._classify(title or "", company or "", description or "", location or "")
        except Exception as exc:
            logger.error("LeadClassifier failed for '{}': {}", title, exc)
            verdict = LeadVerdict(lead_class=REVIEW, lead_score=40, reason=f"Classification error - manual review ({exc})")
        if verdict.used_llm or verdict.lead_class == REJECTED:
            self._cache[key] = verdict  # don't pin a transient LLM-down fallback
        return verdict

    async def apply(self, job) -> LeadVerdict:
        """Classify a JobPosting and write the verdict onto it."""
        v = await self.classify(job.job_title, job.company, job.job_description, getattr(job, "location", ""))
        job.lead_class, job.lead_score = v.lead_class, v.lead_score
        job.lead_category, job.lead_reason, job.engagement_type = v.category, v.reason, v.engagement
        job.reject_reason = v.short_reason if v.lead_class == REJECTED else ""
        job.lead_tech_fit = v.tech_fit
        return v

    # ------------------------------------------------------------------ internals
    def _signals(self, text: str) -> tuple[list[str], list[str]]:
        pos = [rx.pattern for rx in self._pos_res if rx.search(text)]
        neg = [rx.pattern for rx in self._neg_res if rx.search(text)]
        return pos, neg

    async def _classify(self, title: str, company: str, description: str, location: str) -> LeadVerdict:
        text = f"{title}\n{description}"
        pos, neg = self._signals(text)
        title_rejected = bool(self._reject_re.search(title))
        title_tech = bool(self._tech_re.search(title))

        # 0. Leadership / management titles are never delivery leads, even at tech companies and even when
        #    the title also contains tech words ("Manager, Data Science"): no LLM call needed.
        if self._always_re.search(title):
            return LeadVerdict(
                lead_class=REJECTED, lead_score=5, category="Leadership / management", engagement="non_technical",
                reason=f"Leadership / management role by title ('{title[:60]}') - not an IT delivery opportunity.",
                positive_signals=pos, negative_signals=neg,
                short_reason=f"Management / leadership role ({_short_title(title)})",
            )

        # 1. Obviously non-technical title: no LLM call needed.
        if title_rejected and not title_tech:
            return LeadVerdict(
                lead_class=REJECTED, lead_score=5, category="Non-technical role", engagement="non_technical",
                reason=f"Non-technical role by title ('{title[:60]}') - not an IT delivery opportunity.",
                positive_signals=pos, negative_signals=neg,
                short_reason=short_reject_reason("non_technical", "", title, 5, by_title=True),
            )

        llm = await self._ask_llm(title, company, location, description)
        if llm is None:
            return self._rules_only(title_tech, pos, neg)

        engagement = str(llm.get("engagement", "unclear")).strip().lower()
        category = str(llm.get("category", "")).strip() or "Other"
        reason = str(llm.get("reason", "")).strip()
        try:
            score = int(round(float(llm.get("fit_score", 0))))
        except (TypeError, ValueError):
            score = 0
        try:
            confidence = float(llm.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        score = max(0, min(100, score))
        try:
            tech_fit = max(0, min(100, int(round(float(llm.get("tech_fit", 0))))))
        except (TypeError, ValueError):
            tech_fit = 0
        location_locked = str(llm.get("location_locked", "")).strip().lower() in ("true", "1", "yes")

        # 2b. "Contract" is not enough: per-task gig work and country-locked contracts are not offshore leads.
        gig_hits = [rx.pattern for rx in self._gig_res if rx.search(text)]
        if engagement in POSITIVE_ENGAGEMENTS and gig_hits and engagement != "staff_augmentation":
            engagement = "gig_work"
        if engagement in POSITIVE_ENGAGEMENTS and location_locked:
            engagement = "location_locked"
        if engagement in ("gig_work", "location_locked"):
            score = min(score, 20)

        # 3. Deterministic adjustment: B2B evidence lifts, vacancy evidence caps.
        notes: list[str] = []
        if engagement in POSITIVE_ENGAGEMENTS and pos:
            score = min(100, score + min(10, 5 * len(pos)))
        if engagement == "internal_hire":
            cap = 54 if len(pos) >= 2 else 30
            if score > cap:
                score = cap
                notes.append("capped: single internal hire")
        elif engagement == "non_technical":
            score = min(score, 15)
        elif engagement == "unclear":
            score = min(score, 54)
        if title_rejected and engagement not in POSITIVE_ENGAGEMENTS:
            score = min(score, 34)
        if len(neg) >= 2 and not pos and engagement != "internal_hire":
            score = max(0, score - 10)
            notes.append("vacancy-style wording")

        cls = self._class_for(score)
        if len(description.strip()) < THIN_LEAD_DESC_CHARS and not pos and cls in (HIGH, RELEVANT):
            cls = REVIEW  # little text and no B2B evidence: don't auto-accept
            notes.append("very short description")
        if confidence < 0.55 and cls in (HIGH, RELEVANT):
            cls = REVIEW
            notes.append("low confidence")
        if cls == REJECTED and confidence < 0.4 and score >= 25:
            cls = REVIEW
            notes.append("low confidence")

        if notes:
            reason = f"{reason} ({'; '.join(notes)})".strip()
        return LeadVerdict(
            lead_class=cls, lead_score=score, category=category, engagement=engagement, reason=reason,
            positive_signals=pos, negative_signals=neg, used_llm=True, tech_fit=tech_fit,
            short_reason=short_reject_reason(engagement, category, title, score) if cls == REJECTED else "",
        )

    def _rules_only(self, title_tech: bool, pos: list[str], neg: list[str]) -> LeadVerdict:
        """LLM unavailable: never auto-accept; technical + B2B evidence -> manual review, else reject."""
        score = (40 if title_tech else 15) + 15 * min(2, len(pos)) - 15 * min(1, len(neg))
        score = max(0, min(69, score))
        cls = REVIEW if score >= self._thr("lead_review_threshold", 35) else REJECTED
        return LeadVerdict(
            lead_class=cls, lead_score=score, category="Unverified", engagement="unclear",
            reason="LLM unavailable - classified by rules only; please review manually.",
            positive_signals=pos, negative_signals=neg, used_llm=False,
            short_reason="Not technical enough (rules only, LLM unavailable)" if cls == REJECTED else "",
        )

    async def _ask_llm(self, title: str, company: str, location: str, description: str) -> Optional[dict]:
        matcher = self._matcher
        if matcher is None or not getattr(matcher, "available", False):
            return None
        prompt = _USER.format(
            title=title[:200], company=company[:120], location=location[:100], jd=prepare_jd(description, 3500)
        )
        return await matcher.complete_json(_SYSTEM, prompt, max_tokens=300, attempts=2)

    @staticmethod
    def _thr(name: str, default: int) -> int:
        try:
            return int(getattr(get_settings(), name, default))
        except Exception:
            return default

    def _class_for(self, score: int) -> str:
        if score >= self._thr("lead_high_threshold", 75):
            return HIGH
        if score >= self._thr("lead_relevant_threshold", 55):
            return RELEVANT
        if score >= self._thr("lead_review_threshold", 35):
            return REVIEW
        return REJECTED


_classifier: Optional[LeadClassifier] = None


def get_lead_classifier() -> LeadClassifier:
    """Shared classifier (shared cache) using the shared LLM client."""
    global _classifier
    if _classifier is None:
        from app.matching.llm_matcher import get_llm_matcher

        _classifier = LeadClassifier(get_llm_matcher())
    return _classifier
