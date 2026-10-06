"""
Match Engine v2 - one scoring path for Manual, Auto (Indeed) and Dice.

  JD -> prepare (requirements-first) -> LLM extracts weighted requirements
     -> KB retrieval PER requirement (+ one role-level query)
     -> LLM judges each requirement against its evidence, quoting the KB
     -> quotes verified in code, score computed deterministically (scoring.py)

Never raises. KB/LLM failure yields match_status="unscored" with score None,
not a made-up default score.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import OrderedDict
from typing import Optional

from app.config.settings import get_settings
from app.knowledge_base.models import RetrievedChunk
from app.matching.jd_text import heuristic_requirements, is_thin, jd_hash, prepare_jd
from app.matching.models import MatchResult
from app.matching.scoring import RequirementVerdict, compute_score, ground_verdict, has_signal
from app.utils.logger import logger

PROMPT_VERSION = "v2.1"
_RESULT_TTL_SECONDS = 6 * 3600
_CACHE_MAX = 512
_EVIDENCE_CHARS = 450
_CHUNKS_PER_REQUIREMENT = 3
_SOFT_SKILL_RE = re.compile(
    r"leadership|communicat|collaborat|teamwork|team player|aptitude|talent|problem[- ]solving|stakeholder|"
    r"proactive|reliable|hands-on approach|ability to|fluent|english|german|spanish|detail[- ]oriented|"
    r"self[- ]motivated|work ethic|time management|multi-?task|customer service skills|interpersonal",
    re.IGNORECASE,
)

_EXTRACT_SYSTEM = (
    "You extract the technical requirements of a job description. Respond with strict JSON only."
)
_EXTRACT_USER = (
    "From the JOB DESCRIPTION, list the concrete skills/tools/technologies/platforms the role requires.\n"
    "Rules:\n"
    "- Only things the text itself states. Never invent.\n"
    "- One requirement per item, e.g. 'RAG and enterprise search' or 'Tableau or Power BI' are fine; keep alternatives ('A, B or C') in ONE item.\n"
    "- 'skill': short canonical name (e.g. 'SharePoint Online', 'Power Automate', '.NET', 'Azure OpenAI'), no sentences.\n"
    "- 'importance': 'must' if required / core to daily responsibilities, 'nice' if preferred / bonus / incidental mention.\n"
    "- Skip soft skills (leadership, communication, collaboration), languages spoken, degrees, years of experience, and generic words.\n"
    "- At most {max_req} items, most important first.\n"
    "- 'role_title' and 'domain' (3-6 words describing the core technical domain of the role).\n"
    'JSON: {{"role_title": "", "domain": "", "requirements": [{{"skill": "", "importance": "must"}}]}}\n\n'
    "JOB DESCRIPTION:\n{jd}"
)

NL = chr(10)
_ROLE_SYSTEM = "You judge fit between a company's capabilities and a job role. Respond with strict JSON only."
_ROLE_USER = (
    "ROLE: {role_title} | DOMAIN: {domain}" + NL +
    "REQUIREMENT COVERAGE (from company knowledge): {coverage}" + NL +
    "COMPANY KNOWLEDGE MOST RELEVANT TO THE ROLE:" + NL + "{role_evidence}" + NL + NL +
    "JOB (excerpt):" + NL + "{jd}" + NL + NL +
    "Question: is the CORE of this role's work (its main domain, not incidental tools) something the company does? "
    "'role_fit' = 'strong' (core domain is ours), 'partial' (adjacent / some overlap) or 'weak' (different domain). "
    "'job_summary' = ONE short sentence on the role's responsibilities." + NL +
    'JSON: {{"role_fit": "partial", "job_summary": ""}}'
)


class _TTLCache:
    def __init__(self, ttl: Optional[float] = None, maxsize: int = _CACHE_MAX) -> None:
        self._d: OrderedDict[str, tuple[float, object]] = OrderedDict()
        self._ttl = ttl
        self._max = maxsize

    def get(self, key: str):
        item = self._d.get(key)
        if not item:
            return None
        ts, val = item
        if self._ttl is not None and time.time() - ts > self._ttl:
            self._d.pop(key, None)
            return None
        self._d.move_to_end(key)
        return val

    def set(self, key: str, val) -> None:
        self._d[key] = (time.time(), val)
        self._d.move_to_end(key)
        while len(self._d) > self._max:
            self._d.popitem(last=False)


class MatchEngine:
    def __init__(self, kb, matcher) -> None:
        self._kb = kb
        self._matcher = matcher
        self._extract_cache = _TTLCache()
        self._result_cache = _TTLCache(ttl=_RESULT_TTL_SECONDS)
        self._sem = asyncio.Semaphore(4)

    def available(self) -> bool:
        return bool(getattr(self._matcher, "available", False)) and bool(getattr(self._kb, "enabled", False))

    async def evaluate(self, job_description: str, job_title: str = "") -> MatchResult:
        if not job_description or not job_description.strip():
            return MatchResult(match_status="unscored", match_reason="No job description")
        key = jd_hash(job_description, PROMPT_VERSION)
        cached = self._result_cache.get(key)
        if cached is not None:
            return cached.model_copy(deep=True)
        try:
            result = await self._evaluate(job_description, job_title, key)
        except Exception as exc:
            logger.error("MatchEngine v2 failed: {}", exc)
            return MatchResult(match_status="unscored", match_reason=f"Evaluation failed: {exc}")
        if result.match_status != "unscored":
            self._result_cache.set(key, result.model_copy(deep=True))
        return result

    async def _evaluate(self, job_description: str, job_title: str, key: str) -> MatchResult:
        settings = get_settings()
        max_req = max(3, int(getattr(settings, "match_max_requirements", 12)))
        t0 = time.time()
        jd = prepare_jd(job_description)

        # 1. Requirement extraction (cached per JD)
        extracted = self._extract_cache.get(key)
        if extracted is None:
            extracted = await self._matcher.complete_json(
                _EXTRACT_SYSTEM, _EXTRACT_USER.format(max_req=max_req, jd=jd), max_tokens=500
            )
            if extracted:
                self._extract_cache.set(key, extracted)
        used_fallback = False
        if not extracted:
            # LLM endpoint timed out / throttled: fall back to vocabulary-based extraction so the job still
            # gets a KB-grounded score (flagged low_confidence) instead of being left blank.
            fallback = heuristic_requirements(jd)
            if not fallback:
                return MatchResult(match_status="unscored", match_reason="Requirement extraction failed")
            extracted = {"role_title": job_title, "domain": "", "requirements": fallback}
            used_fallback = True
            logger.warning("MatchEngine: LLM extraction failed for '{}', using vocabulary fallback ({} terms)", job_title, len(fallback))

        t1 = time.time()
        requirements = self._clean_requirements(extracted.get("requirements"), max_req)
        role_title = str(extracted.get("role_title") or job_title or "").strip()
        domain = str(extracted.get("domain") or "").strip()
        if not requirements:
            return MatchResult(match_status="unscored", match_reason="No technical requirements found in the job description")

        # 2. Retrieval per requirement + one role-level query. Any KB error -> unscored.
        queries = [r["skill"] for r in requirements] + [f"{role_title} {domain}".strip() or jd[:300]]
        try:
            retrieved = await asyncio.gather(*(self._search(q) for q in queries))
        except Exception as exc:
            logger.error("MatchEngine KB retrieval failed: {}", exc)
            return MatchResult(match_status="unscored", match_reason="Knowledge base retrieval failed")

        evidence: dict[str, str] = {}
        full_evidence: dict[str, str] = {}
        ids_by_key: dict[str, str] = {}

        def eid(c: RetrievedChunk) -> str:
            k = c.chunk_id or c.chunk[:60]
            if k not in ids_by_key:
                ids_by_key[k] = f"E{len(ids_by_key) + 1}"
                full_evidence[ids_by_key[k]] = f"{c.title} {c.chunk}"
                evidence[ids_by_key[k]] = f"[{c.title}] {c.chunk.strip()[:_EVIDENCE_CHARS]}".replace("\n", " ")
            return ids_by_key[k]

        req_ids: list[list[str]] = []
        for chunks in retrieved[:-1]:
            req_ids.append([eid(c) for c in chunks[:_CHUNKS_PER_REQUIREMENT]])
        role_ids = [eid(c) for c in retrieved[-1][:_CHUNKS_PER_REQUIREMENT]]

        if not evidence:
            # KB reachable but nothing relevant for any requirement: that is a real, low fit.
            return self._all_missing(requirements, role_title)

        # 3. Decide each requirement from the retrieved KB text itself (deterministic, see scoring.py).
        verdicts: list[RequirementVerdict] = []
        for r, ids in zip(requirements, req_ids):
            v = RequirementVerdict(skill=r["skill"], importance=r["importance"])
            v.share = r.get("share", 1.0)
            v.group, v.any_of = r.get("group", ""), r.get("any_of", False)
            own = " ".join(full_evidence[i] for i in dict.fromkeys(ids))
            verdicts.append(ground_verdict(v, own, own))

        # 4. One small LLM call for what code cannot judge: is the role's CORE domain ours, plus a summary.
        t2 = time.time()
        coverage = "; ".join(
            f"{v.skill}: {v.verdict}" for v in verdicts
        )
        role_evidence = "\n".join(f"- {evidence[i]}" for i in role_ids) or "- (none retrieved)"
        judged = await self._matcher.complete_json(
            _ROLE_SYSTEM,
            _ROLE_USER.format(
                role_title=role_title or "n/a", domain=domain or "n/a", coverage=coverage,
                role_evidence=role_evidence, jd=jd[:1200],
            ),
            max_tokens=200,
            attempts=1,
        ) or {}
        logger.info(
            "MatchEngine timing: extract={:.1f}s retrieve={:.1f}s role-fit={:.1f}s ({} reqs)",
            t1 - t0, t2 - t1, time.time() - t2, len(requirements),
        )

        role_fit = str(judged.get("role_fit", "partial")).lower()
        outcome = compute_score(verdicts, role_fit)

        status = "low_confidence" if (used_fallback or is_thin(job_description) or len(requirements) < 3) else "scored"
        n_hit, n_gap = len(outcome.matched), len(outcome.missing)
        reason = f"{n_hit} requirement(s) supported by company knowledge, {n_gap} without evidence."
        if outcome.matched:
            reason += f" Strengths: {', '.join(outcome.matched[:3])}."
        if outcome.missing:
            reason += f" No evidence for: {', '.join(outcome.missing[:3])}."
        if outcome.cap < outcome.base:
            reason += f" Score capped at {outcome.cap} (role fit: {role_fit})."

        return MatchResult(
            match_score=outcome.score,
            matched_skills=outcome.matched,
            missing_skills=outcome.missing,
            match_reason=reason,
            job_summary=str(judged.get("job_summary", "")).strip(),
            match_status=status,
        )

    async def _search(self, query: str) -> list[RetrievedChunk]:
        async with self._sem:
            return await self._kb.search(query, top_k=_CHUNKS_PER_REQUIREMENT, raise_on_error=True)

    @staticmethod
    def _split_compound(skill: str) -> tuple[list[str], bool]:
        """'RAG and enterprise search' -> (['RAG', 'enterprise search'], any_of=False).
        'Tableau or Power BI' -> (['Tableau', 'Power BI'], any_of=True). '(...)' details are dropped
        and short acronym pairs like TCP/IP or CI/CD stay whole."""
        if re.search(r"\(.*\)", skill):
            skill = re.sub(r"\s*\(.*?\)", "", skill).strip() or skill
        if re.fullmatch(r"[A-Za-z0-9+#.]{1,6}/[A-Za-z0-9+#.]{1,6}", skill.strip()):
            return [skill.strip()], False
        any_of = bool(re.search(r"\bor\b", skill, re.IGNORECASE))
        parts = re.split(r"\s*(?:,|/|;|&|\band\b|\bor\b)\s*", skill, flags=re.IGNORECASE)
        parts = [p.strip(" .-") for p in parts if p and len(p.strip(" .-")) >= 2]
        if len(parts) <= 1:
            return [skill.strip()], False
        return parts, any_of

    @staticmethod
    def _clean_requirements(items, max_req: int) -> list[dict]:
        out: list[dict] = []
        seen: set[str] = set()
        n_items = 0
        for gi, it in enumerate(items or []):
            if not isinstance(it, dict):
                continue
            raw = str(it.get("skill", "")).strip()
            if not raw or len(raw) > 80 or _SOFT_SKILL_RE.search(raw):
                continue
            imp = "nice" if str(it.get("importance", "must")).lower() == "nice" else "must"
            parts, any_of = MatchEngine._split_compound(raw)
            parts = [p for p in parts if not _SOFT_SKILL_RE.search(p) and has_signal(p) and p.lower() not in seen]
            for p in parts:
                seen.add(p.lower())
                # split parts share the original requirement's weight, so wordy JDs don't dominate;
                # alternatives ("A or B") are satisfied by their best member
                out.append({"skill": p, "importance": imp, "share": 1.0 / max(1, len(parts)),
                            "group": f"g{gi}" if len(parts) > 1 else "", "any_of": any_of and len(parts) > 1})
            n_items += 1
            if n_items >= max_req:
                break
        return out

    @staticmethod
    def _all_missing(requirements: list[dict], role_title: str) -> MatchResult:
        return MatchResult(
            match_score=0,
            matched_skills=[],
            missing_skills=[r["skill"] for r in requirements],
            match_reason=f"No company knowledge found relevant to this role ({role_title or 'unknown role'}).",
            match_status="scored",
        )


_engine: Optional[MatchEngine] = None


def get_match_engine() -> MatchEngine:
    """Shared engine (and therefore shared caches) for Manual, Auto and Dice."""
    global _engine
    if _engine is None:
        from app.knowledge_base.azure_search import get_knowledge_base
        from app.matching.llm_matcher import get_llm_matcher

        _engine = MatchEngine(get_knowledge_base(), get_llm_matcher())
    return _engine
